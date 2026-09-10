"""
Fetch climate adaptation-related development finance from the OECD and write
data/processed/parts/oecd_climate.csv  (climate_adaptation_finance_usd, by
country-year; build_dataset.py turns it into "% of GDP").

Source: OECD Climate-Related Development Finance / DAC Rio Markers.

Reality check: the OECD SDMX API (sdmx.oecd.org) requires an exact dataflow
version and dimension key that the OECD changes between releases, and the
open "all-key" query is frequently rejected. This fetcher is parameterised so
it can be pointed at a working query without code changes:

    OECD_CLIMATE_DATA_URL   full SDMX data URL returning CSV (overrides everything)
    OECD_CLIMATE_DATAFLOW   e.g. "OECD.DCD.FSD,DSD_RIOMRKR@DF_RIOMARKERS,1.6"
    OECD_CLIMATE_KEY        SDMX key segment (default "all")

If the request fails or returns nothing, an empty part is written and the
`climate_adaptation_finance` indicator stays `status="planned"`.

    python etl/fetch_oecd_climate.py
"""

from __future__ import annotations

import csv
import io
import os
import sys
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import RAW_DIR, now_iso, write_part  # noqa: E402
from indicators import ARAB_COUNTRIES  # noqa: E402

MIN_YEAR = 2000
DEFAULT_DATAFLOW = os.environ.get(
    "OECD_CLIMATE_DATAFLOW", "OECD.DCD.FSD,DSD_RIOMRKR@DF_RIOMARKERS,1.6"
)


def _url() -> str:
    if os.environ.get("OECD_CLIMATE_DATA_URL"):
        return os.environ["OECD_CLIMATE_DATA_URL"]
    key = os.environ.get("OECD_CLIMATE_KEY", "all")
    return (
        f"https://sdmx.oecd.org/public/rest/data/{DEFAULT_DATAFLOW}/{key}"
        f"?startPeriod={MIN_YEAR}&format=csvfilewithlabels"
    )


def main() -> None:
    url = _url()
    try:
        resp = requests.get(url, timeout=120, headers={"Accept": "text/csv"})
        resp.raise_for_status()
        text = resp.text
        if not text.strip() or text.lstrip().startswith("<") or "not set to an instance" in text:
            raise ValueError("OECD returned no usable CSV")
    except (requests.RequestException, ValueError) as exc:
        print(f"OECD climate finance not fetched ({exc}).")
        print("  Set OECD_CLIMATE_DATA_URL to a working SDMX CSV query to wire this up; "
              "the indicator stays 'planned' meanwhile.")
        write_part("oecd_climate", [])
        return

    (RAW_DIR / "oecd").mkdir(parents=True, exist_ok=True)
    (RAW_DIR / "oecd" / "climate_finance.csv").write_text(text)

    reader = csv.DictReader(io.StringIO(text))
    # column names vary by OECD release; probe for recipient ISO, year, value,
    # and an adaptation marker column.
    rows_in = list(reader)
    cols = reader.fieldnames or []
    iso_col = _pick(cols, ["Recipient", "RECIPIENT", "REF_AREA", "Recipient code"])
    year_col = _pick(cols, ["TIME_PERIOD", "Year", "TIME"])
    val_col = _pick(cols, ["OBS_VALUE", "Value"])
    marker_col = _pick(cols, ["Climate", "Rio marker", "MARKER", "TYPE_AID"])
    if not (iso_col and year_col and val_col):
        print("OECD CSV columns not recognised; raw saved to data/raw/oecd/. Writing empty part.")
        write_part("oecd_climate", [])
        return

    totals: dict[tuple[str, int], float] = defaultdict(float)
    name_to_iso = {v.lower(): k for k, v in ARAB_COUNTRIES.items()}
    for r in rows_in:
        if marker_col and "adapt" not in str(r.get(marker_col, "")).lower():
            continue
        raw_iso = str(r.get(iso_col, "")).strip()
        iso3 = raw_iso.upper() if raw_iso.upper() in ARAB_COUNTRIES else name_to_iso.get(raw_iso.lower())
        if not iso3:
            continue
        try:
            year = int(str(r[year_col])[:4])
            val = float(r[val_col])
        except (ValueError, TypeError):
            continue
        if year >= MIN_YEAR:
            totals[(iso3, year)] += val

    retrieved_at = now_iso()
    out = [
        {
            "country_iso3": iso3,
            "country_name": ARAB_COUNTRIES[iso3],
            "indicator_id": "climate_adaptation_finance_usd",
            "indicator_label": "Adaptation finance (USD)",
            "pathway": "Context",
            "theme": "Climate Hazards",
            "risk_measure": "Context",
            "variable": "Climate adaptation-related development finance received (USD, current)",
            "unit": "current US$ (millions)",
            "higher_is_worse": False,
            "year": year,
            "value": v,
            "source_name": "OECD",
            "source_dataset": "OECD Climate-Related Development Finance",
            "source_url": "https://www.oecd.org/dac/",
            "retrieved_at": retrieved_at,
        }
        for (iso3, year), v in sorted(totals.items())
    ]
    write_part("oecd_climate", out)


def _pick(cols: list[str], candidates: list[str]) -> str | None:
    lower = {c.lower(): c for c in cols}
    for cand in candidates:
        if cand.lower() in lower:
            return lower[cand.lower()]
    for c in cols:
        if any(cand.lower() in c.lower() for cand in candidates):
            return c
    return None


if __name__ == "__main__":
    main()
