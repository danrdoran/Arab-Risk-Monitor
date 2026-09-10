"""
Fetch UCDP battle-related deaths and write:
  - data/processed/parts/ucdp.csv         (conflict_ucdp_battle_deaths_total,
                                            for the 22 Arab countries)
  - data/raw/ucdp/battle_deaths_by_country_year.json  (ALL countries we track,
                                            incl. non-Arab neighbours — used by
                                            build_dataset.py for the derived
                                            "conflict intensity" and
                                            "neighbouring conflict" indicators)

Source: UCDP Battle-Related Deaths Dataset v24.1, a static CSV download that
needs no API key (the live UCDP API now requires a token).
https://ucdp.uu.se/downloads/

Method: each conflict-year record carries `bd_best` (best estimate of battle
deaths) and `gwno_loc` (one or more Gleditsch-Ward country numbers for where
the fighting took place). We attribute the full `bd_best` to every listed
location country and sum by country-year. Cross-border wars are therefore
counted for each country they touch — conservative for a risk indicator and
consistent with how the fighting affects each location.

    python etl/fetch_ucdp.py
"""

from __future__ import annotations

import io
import json
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAW_DIR, now_iso, row_for, write_part  # noqa: E402
from indicators import ARAB_COUNTRIES, GW_TO_ISO3, INDICATORS  # noqa: E402

BRD_URL = "https://ucdp.uu.se/downloads/brd/ucdp-brd-conf-241-csv.zip"
UCDP_RAW = RAW_DIR / "ucdp"
MIN_YEAR = 2000

_BY_ID = {i.id: i for i in INDICATORS}


def download_brd() -> list[dict]:
    UCDP_RAW.mkdir(parents=True, exist_ok=True)
    print(f"downloading {BRD_URL} ...")
    resp = requests.get(BRD_URL, timeout=120)
    resp.raise_for_status()
    (UCDP_RAW / "ucdp-brd-conf-241-csv.zip").write_bytes(resp.content)

    zf = zipfile.ZipFile(io.BytesIO(resp.content))
    name = next(n for n in zf.namelist() if n.lower().endswith(".csv"))
    import csv as _csv

    text = zf.read(name).decode("utf-8-sig")
    rows = list(_csv.DictReader(io.StringIO(text)))
    (UCDP_RAW / name).write_text(text)
    print(f"  {len(rows)} conflict-year records")
    return rows


def battle_deaths_by_country_year(records: list[dict]) -> dict[str, dict[int, int]]:
    """{iso3: {year: total_bd_best}} for every country in GW_TO_ISO3."""
    out: dict[str, dict[int, int]] = defaultdict(lambda: defaultdict(int))
    for r in records:
        try:
            year = int(r["year"])
            bd = int(float(r.get("bd_best") or 0))
        except (ValueError, TypeError):
            continue
        if year < MIN_YEAR or bd <= 0:
            continue
        locs = str(r.get("gwno_loc") or "").replace(" ", "")
        for tok in locs.split(","):
            if not tok:
                continue
            iso3 = GW_TO_ISO3.get(int(tok)) if tok.isdigit() else None
            if iso3:
                out[iso3][year] += bd
    return {k: dict(v) for k, v in out.items()}


def main() -> None:
    records = download_brd()
    table = battle_deaths_by_country_year(records)

    (UCDP_RAW / "battle_deaths_by_country_year.json").write_text(
        json.dumps({"retrieved_at": now_iso(), "source": BRD_URL, "table": table}, indent=2)
    )

    retrieved_at = now_iso()
    ind = _BY_ID["conflict_ucdp_battle_deaths_total"]
    rows: list[dict] = []
    for iso3, name in ARAB_COUNTRIES.items():
        for year, bd in sorted(table.get(iso3, {}).items()):
            rows.append(row_for(ind, iso3, name, year, bd, retrieved_at))
    write_part("ucdp", rows)
    print(f"  battle-death table for {len(table)} countries saved under {UCDP_RAW.relative_to(RAW_DIR.parent.parent)}")


if __name__ == "__main__":
    main()
