"""
Fetch every World Bank / WGI-sourced indicator for the 22 Arab League
countries and write data/processed/parts/worldbank.csv.

The public World Bank API needs no key. The raw JSON response for every
call is saved verbatim under data/raw/ for a full provenance trail. This is
a build artifact — re-run any time; etl/build_dataset.py merges the parts.

    python etl/fetch_worldbank.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAW_DIR, now_iso, row_for, write_part  # noqa: E402
from indicators import ARAB_COUNTRIES, WORLDBANK_INDICATORS  # noqa: E402

API_BASE = "https://api.worldbank.org/v2/country/{country}/indicator/{indicator}"
MIN_YEAR = 2000


def fetch_indicator(country_iso3: str, indicator_id: str) -> list[dict]:
    url = API_BASE.format(country=country_iso3, indicator=indicator_id)
    params = {"format": "json", "per_page": 200, "date": f"{MIN_YEAR}:2025"}
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    payload = resp.json()

    raw_path = RAW_DIR / f"{indicator_id.replace('.', '_')}__{country_iso3}.json"
    raw_path.write_text(json.dumps(payload, indent=2))

    if not isinstance(payload, list) or len(payload) < 2 or not payload[1]:
        return []
    return payload[1]


def main() -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    retrieved_at = now_iso()
    rows: list[dict] = []

    indicators = [i for i in WORLDBANK_INDICATORS if i.status == "live"]
    total = len(indicators) * len(ARAB_COUNTRIES)
    done = 0
    for indicator in indicators:
        for iso3, country_name in ARAB_COUNTRIES.items():
            done += 1
            print(f"[{done}/{total}] {indicator.id} x {iso3}...", end=" ")
            try:
                observations = fetch_indicator(iso3, indicator.id)
            except requests.RequestException as exc:
                print(f"FAILED: {exc}")
                continue
            kept = 0
            for obs in observations:
                if obs.get("value") is None:
                    continue
                rows.append(row_for(indicator, iso3, country_name, int(obs["date"]), obs["value"], retrieved_at))
                kept += 1
            print(f"{kept} obs")
            time.sleep(0.05)

    write_part("worldbank", rows)
    print(f"Raw API responses saved under {RAW_DIR}")


if __name__ == "__main__":
    main()
