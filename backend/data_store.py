"""
Loads the processed, provenance-tagged indicator table and exposes small,
well-typed query functions the chat tool-caller and the REST API build on.

This module never talks to the network -- it only reads the CSV that
etl/fetch_worldbank.py produced, so the running app is fast and works
offline once the data has been fetched once.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
DATA_PATH = ROOT / "data" / "processed" / "indicators.csv"


@lru_cache(maxsize=1)
def load_data() -> pd.DataFrame:
    if not DATA_PATH.exists():
        raise FileNotFoundError(
            f"{DATA_PATH} not found. Run `python etl/fetch_worldbank.py` first."
        )
    df = pd.read_csv(DATA_PATH)
    return df


def list_countries() -> list[dict]:
    df = load_data()
    return (
        df[["country_iso3", "country_name"]]
        .drop_duplicates()
        .sort_values("country_name")
        .to_dict(orient="records")
    )


def list_indicators() -> list[dict]:
    df = load_data()
    cols = [
        "indicator_id",
        "indicator_label",
        "pathway",
        "theme",
        "risk_measure",
        "variable",
        "unit",
        "higher_is_worse",
        "source_name",
        "source_dataset",
        "source_url",
    ]
    return df[cols].drop_duplicates().to_dict(orient="records")


def query(
    countries: list[str] | None = None,
    indicator_ids: list[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    latest_only: bool = False,
) -> pd.DataFrame:
    """Filter the indicator table. `countries` may be ISO3 codes or country
    names (case-insensitive, matched against either column)."""
    df = load_data()

    if countries:
        wanted = {c.strip().lower() for c in countries}
        mask = df["country_iso3"].str.lower().isin(wanted) | df[
            "country_name"
        ].str.lower().isin(wanted)
        df = df[mask]

    if indicator_ids:
        wanted_ids = {i.strip().lower() for i in indicator_ids}
        mask = df["indicator_id"].str.lower().isin(wanted_ids) | df[
            "indicator_label"
        ].str.lower().isin(wanted_ids)
        df = df[mask]

    if year_min is not None:
        df = df[df["year"] >= year_min]
    if year_max is not None:
        df = df[df["year"] <= year_max]

    if latest_only and not df.empty:
        df = df.sort_values("year").groupby(
            ["country_iso3", "indicator_id"], as_index=False
        ).tail(1)

    return df.sort_values(["indicator_label", "country_name", "year"])


def find_indicator(text: str) -> dict | None:
    """Fuzzy-ish lookup: exact id match first, then substring match on label
    or variable text. Used by the chat tool so the model can pass loose
    natural-language indicator names."""
    df = load_data()
    text_l = text.strip().lower()

    exact = df[df["indicator_id"].str.lower() == text_l]
    if not exact.empty:
        row = exact.iloc[0]
    else:
        contains = df[
            df["indicator_label"].str.lower().str.contains(text_l, na=False)
            | df["variable"].str.lower().str.contains(text_l, na=False)
        ]
        if contains.empty:
            return None
        row = contains.iloc[0]

    return {
        "indicator_id": row["indicator_id"],
        "indicator_label": row["indicator_label"],
        "pathway": row["pathway"],
        "theme": row["theme"],
        "risk_measure": row["risk_measure"],
        "variable": row["variable"],
        "unit": row["unit"],
    }
