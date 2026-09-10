"""
Query layer over data/processed/scores.csv (built by etl/build_scores.py):
composite vulnerability / resilience / risk scores per country, per pathway,
per year, following the ESCWA Arab Risk Monitor Annex 1 methodology.

Read-only, no network. Regenerate with `python etl/build_scores.py`.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
SCORES_PATH = ROOT / "data" / "processed" / "scores.csv"
META_PATH = ROOT / "data" / "processed" / "scores_meta.json"

PATHWAYS = ("Conflict", "Climate", "Development", "Overall")
DIMENSIONS = ("vulnerability", "resilience", "risk")


@lru_cache(maxsize=1)
def _df() -> pd.DataFrame:
    if not SCORES_PATH.exists():
        raise FileNotFoundError(
            f"{SCORES_PATH} not found. Run `python etl/build_scores.py` first."
        )
    df = pd.read_csv(SCORES_PATH)
    df["year"] = df["year"].astype(int)
    return df


@lru_cache(maxsize=1)
def meta() -> dict:
    if META_PATH.exists():
        return json.loads(META_PATH.read_text())
    return {}


def loaded() -> bool:
    try:
        _df()
        return True
    except FileNotFoundError:
        return False


def latest_year() -> int:
    return int(_df()["year"].max())


def _match_countries(df: pd.DataFrame, countries: list[str] | None) -> pd.DataFrame:
    if not countries:
        return df
    wanted = {c.strip().lower() for c in countries}
    return df[
        df["country_iso3"].str.lower().isin(wanted)
        | df["country_name"].str.lower().isin(wanted)
    ]


def query(
    countries: list[str] | None = None,
    pathways: list[str] | None = None,
    year: int | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    latest_only: bool = False,
) -> list[dict]:
    df = _match_countries(_df(), countries)
    if pathways:
        pw = {p.strip().lower() for p in pathways}
        df = df[df["pathway"].str.lower().isin(pw)]
    if year is not None:
        df = df[df["year"] == year]
    if year_min is not None:
        df = df[df["year"] >= year_min]
    if year_max is not None:
        df = df[df["year"] <= year_max]
    if latest_only and not df.empty:
        df = df.sort_values("year").groupby(["country_iso3", "pathway"], as_index=False).tail(1)
    df = df.sort_values(["country_name", "pathway", "year"])
    return [
        {k: (None if (isinstance(v, float) and pd.isna(v)) else v) for k, v in row.items()}
        for row in df.to_dict(orient="records")
    ]


def country_profile(iso3: str) -> dict | None:
    df = _match_countries(_df(), [iso3])
    if df.empty:
        return None
    name = df["country_name"].iloc[0]
    ly = int(df["year"].max())
    latest = df[df["year"] == ly].set_index("pathway")
    pathways = {}
    for pw in PATHWAYS:
        if pw in latest.index:
            row = latest.loc[pw]
            trend = [
                {"year": int(tr["year"]), "vulnerability": _f(tr["vulnerability"]), "resilience": _f(tr["resilience"]), "risk": _f(tr["risk"])}
                for tr in df[df["pathway"] == pw].sort_values("year").to_dict(orient="records")
            ]
            pathways[pw] = {
                "vulnerability": _f(row["vulnerability"]),
                "resilience": _f(row["resilience"]),
                "risk": _f(row["risk"]),
                "vulnerability_level": _s(row["vulnerability_level"]),
                "resilience_level": _s(row["resilience_level"]),
                "risk_level": _s(row["risk_level"]),
                "n_indicators": int(row["n_indicators"]) if pd.notna(row["n_indicators"]) else 0,
                "trend": trend,
            }
    return {"country_iso3": df["country_iso3"].iloc[0], "country_name": name, "latest_year": ly, "pathways": pathways}


def ranking(pathway: str = "Overall", dimension: str = "risk", year: int | None = None) -> list[dict]:
    df = _df()
    df = df[df["pathway"].str.lower() == pathway.lower()]
    y = year if year is not None else int(df["year"].max())
    df = df[df["year"] == y].dropna(subset=[dimension])
    ascending = dimension == "resilience"
    df = df.sort_values(dimension, ascending=ascending)
    return [
        {
            "rank": i + 1,
            "country_iso3": r["country_iso3"],
            "country_name": r["country_name"],
            "year": y,
            "pathway": pathway,
            "value": _f(r[dimension]),
            "level": _s(r.get(f"{dimension}_level")),
        }
        for i, r in enumerate(df.to_dict(orient="records"))
    ]


def _f(v):
    return None if v is None or pd.isna(v) else round(float(v), 4)


def _s(v):
    return None if v is None or (isinstance(v, float) and pd.isna(v)) else str(v)


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1:
        print(json.dumps(country_profile(sys.argv[1]), indent=2, default=str))
    else:
        for r in ranking("Overall", "risk"):
            print(f"{r['rank']:2}. {r['country_name']:22} {r['value']}  ({r['level']})")
