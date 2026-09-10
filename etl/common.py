"""
Shared helpers for the ETL fetchers.

Each fetcher (World Bank, UCDP, UNHCR, EM-DAT, OECD) writes a tidy,
long-format CSV "part" to data/processed/parts/<source>.csv with an
identical column set. etl/build_dataset.py concatenates the parts, computes
the derived indicators, and writes data/processed/indicators.csv.

Keeping one schema here means data_store.py never has to care which source a
row came from.
"""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
PARTS_DIR = PROCESSED_DIR / "parts"

COLUMNS = [
    "country_iso3",
    "country_name",
    "indicator_id",
    "indicator_label",
    "pathway",
    "theme",
    "risk_measure",
    "variable",
    "unit",
    "higher_is_worse",
    "year",
    "value",
    "source_name",
    "source_dataset",
    "source_url",
    "retrieved_at",
]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def row_for(indicator, iso3: str, country_name: str, year: int, value, retrieved_at: str) -> dict:
    """Build one standard row from an etl.indicators.Indicator."""
    return {
        "country_iso3": iso3,
        "country_name": country_name,
        "indicator_id": indicator.id,
        "indicator_label": indicator.label,
        "pathway": indicator.pathway,
        "theme": indicator.theme,
        "risk_measure": indicator.risk_measure,
        "variable": indicator.variable,
        "unit": indicator.unit,
        "higher_is_worse": indicator.higher_is_worse,
        "year": int(year),
        "value": value,
        "source_name": indicator.source_name,
        "source_dataset": indicator.source_dataset,
        "source_url": indicator.source_url.format(id=indicator.id),
        "retrieved_at": retrieved_at,
    }


def write_part(name: str, rows: list[dict]) -> Path:
    PARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = PARTS_DIR / f"{name}.csv"
    with path.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in COLUMNS})
    print(f"  wrote {len(rows)} rows -> {path.relative_to(ROOT)}")
    return path


def read_part(name: str) -> list[dict]:
    path = PARTS_DIR / f"{name}.csv"
    if not path.exists():
        return []
    with path.open(newline="") as f:
        return list(csv.DictReader(f))
