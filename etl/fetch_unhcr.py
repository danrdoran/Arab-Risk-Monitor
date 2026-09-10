"""
Fetch UNHCR forced-displacement figures and write:
  - data/processed/parts/unhcr.csv   (displacement_refugees_origin, displacement_idps)
  - data/raw/unhcr/<ISO3>.json       (raw API responses)

Source: UNHCR Refugee Population Statistics API (no key).
https://api.unhcr.org/docs/  —  https://www.unhcr.org/refugee-statistics/

For each country we query by country of origin (`coo`), which returns one
row per year with:
  - refugees        : refugees under UNHCR's mandate originating from the country
  - idps            : internally displaced persons of concern to UNHCR in the country

build_dataset.py combines these with population into the derived
"forced_displacement" (% of population) indicator.

    python etl/fetch_unhcr.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAW_DIR, now_iso, row_for, write_part  # noqa: E402
from indicators import ARAB_COUNTRIES, INDICATORS  # noqa: E402

API = "https://api.unhcr.org/population/v1/population/"
COUNTRIES_API = "https://api.unhcr.org/population/v1/countries/"
UNHCR_RAW = RAW_DIR / "unhcr"
YEAR_FROM, YEAR_TO = 2000, 2024

_BY_ID = {i.id: i for i in INDICATORS}


def unhcr_codes() -> dict[str, str]:
    """UNHCR's population API filters by its own 3-letter `code` (e.g. Lebanon
    is LEB, not LBN). Map ISO3 -> UNHCR code."""
    resp = requests.get(COUNTRIES_API, params={"limit": 1000}, timeout=45)
    resp.raise_for_status()
    items = resp.json().get("items", [])
    return {c["iso"]: c["code"] for c in items if c.get("iso") and c.get("code")}


def fetch_country(code: str, by: str, iso3: str) -> list[dict]:
    """by = 'coo' (country of origin) or 'coa' (country of asylum / hosting)."""
    resp = requests.get(
        API,
        params={"yearFrom": YEAR_FROM, "yearTo": YEAR_TO, by: code, "limit": 2000},
        timeout=45,
    )
    resp.raise_for_status()
    payload = resp.json()
    UNHCR_RAW.mkdir(parents=True, exist_ok=True)
    (UNHCR_RAW / f"{iso3}_{by}.json").write_text(json.dumps(payload, indent=2))
    return payload.get("items", [])


def main() -> None:
    retrieved_at = now_iso()
    ref_ind = _BY_ID["displacement_refugees_origin"]
    hosted_ind = _BY_ID["displacement_refugees_hosted"]
    idp_ind = _BY_ID["displacement_idps"]
    rows: list[dict] = []

    codes = unhcr_codes()
    for i, (iso3, name) in enumerate(ARAB_COUNTRIES.items(), 1):
        code = codes.get(iso3, iso3)
        print(f"[{i}/{len(ARAB_COUNTRIES)}] UNHCR {iso3} ({code})...", end=" ")
        try:
            origin = fetch_country(code, "coo", iso3)
            hosted = fetch_country(code, "coa", iso3)
        except requests.RequestException as exc:
            print(f"FAILED: {exc}")
            continue
        kept = 0
        for it in origin:
            year = int(it["year"])
            if (r := _to_int(it.get("refugees"))) is not None:
                rows.append(row_for(ref_ind, iso3, name, year, r, retrieved_at))
                kept += 1
            if (d := _to_int(it.get("idps"))) is not None:
                rows.append(row_for(idp_ind, iso3, name, year, d, retrieved_at))
                kept += 1
        for it in hosted:
            year = int(it["year"])
            if (r := _to_int(it.get("refugees"))) is not None:
                rows.append(row_for(hosted_ind, iso3, name, year, r, retrieved_at))
                kept += 1
        print(f"{kept} obs")
        time.sleep(0.1)

    write_part("unhcr", rows)


def _to_int(v) -> int | None:
    try:
        n = int(float(v))
        return n
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    main()
