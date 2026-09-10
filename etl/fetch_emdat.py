"""
Fetch natural-disaster impact from EM-DAT and write
data/processed/parts/emdat.csv  (climate_disaster_impact_affected — total
people affected by disasters, by country-year; build_dataset.py turns it into
the "% of population" indicator).

EM-DAT no longer offers an open, no-auth feed: you need a free account and an
API token from https://public.emdat.be/ . Set it in .env:

    EMDAT_API_TOKEN=...

Without the token this script writes an empty part and the
`climate_disaster_impact` indicator stays `status="planned"` — the advisor
already handles planned indicators by naming the intended source instead of
guessing a number.

    python etl/fetch_emdat.py
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAW_DIR, now_iso, write_part  # noqa: E402
from indicators import ARAB_COUNTRIES  # noqa: E402

EMDAT_GRAPHQL = os.environ.get("EMDAT_API_URL", "https://api.emdat.be/v1")
MIN_YEAR = 2000

_QUERY = """
query monitorDisasters($iso: [String!], $from: Int!) {
  api_version
  public_emdat(
    filters: { classif: ["nat-*"], from: $from, iso: $iso }
    limit: 10000
  ) {
    data { iso start_year total_affected }
  }
}
"""


def main() -> None:
    token = os.environ.get("EMDAT_API_TOKEN")
    if not token:
        print("EMDAT_API_TOKEN not set — skipping. Register free at https://public.emdat.be/ "
              "and add EMDAT_API_TOKEN to .env to wire this indicator up.")
        write_part("emdat", [])
        return

    iso_list = list(ARAB_COUNTRIES)
    try:
        resp = requests.post(
            EMDAT_GRAPHQL,
            json={"query": _QUERY, "variables": {"iso": iso_list, "from": MIN_YEAR}},
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
            timeout=90,
        )
        resp.raise_for_status()
        payload = resp.json()
    except (requests.RequestException, ValueError) as exc:
        print(f"EM-DAT request failed ({exc}); writing empty part. "
              "Check EMDAT_API_TOKEN / EMDAT_API_URL, or the query shape against the current API docs.")
        write_part("emdat", [])
        return

    (RAW_DIR / "emdat").mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "emdat" / "response.json").write_text(resp.text)

    try:
        records = payload["data"]["public_emdat"]["data"]
    except (KeyError, TypeError):
        print("EM-DAT response shape unexpected; writing empty part. Raw saved to data/raw/emdat/.")
        write_part("emdat", [])
        return

    affected: dict[tuple[str, int], int] = defaultdict(int)
    for r in records:
        iso3 = (r.get("iso") or "").upper()
        yr = r.get("start_year")
        n = r.get("total_affected") or 0
        if iso3 in ARAB_COUNTRIES and yr:
            affected[(iso3, int(yr))] += int(n)

    retrieved_at = now_iso()
    rows = [
        {
            "country_iso3": iso3,
            "country_name": ARAB_COUNTRIES[iso3],
            "indicator_id": "climate_disaster_impact_affected",
            "indicator_label": "People affected by disasters",
            "pathway": "Context",
            "theme": "Climate Hazards",
            "risk_measure": "Context",
            "variable": "Total people affected by natural disasters in the year",
            "unit": "people",
            "higher_is_worse": True,
            "year": year,
            "value": n,
            "source_name": "EM-DAT (CRED)",
            "source_dataset": "EM-DAT International Disaster Database",
            "source_url": "https://www.emdat.be/",
            "retrieved_at": retrieved_at,
        }
        for (iso3, year), n in sorted(affected.items())
    ]
    write_part("emdat", rows)


if __name__ == "__main__":
    main()
