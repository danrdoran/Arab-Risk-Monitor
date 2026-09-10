"""
Merge the source "parts" into data/processed/indicators.csv and compute the
derived indicators.

    python etl/build_dataset.py            # merge existing parts + derive
    python etl/build_dataset.py --refresh  # run every fetcher first, then merge

Parts (data/processed/parts/*.csv) are produced by:
    fetch_worldbank.py   worldbank.csv     World Bank / WGI / SIPRI
    fetch_ucdp.py        ucdp.csv          UCDP battle-related deaths (+ raw table)
    fetch_unhcr.py       unhcr.csv         UNHCR refugees / IDPs
    fetch_emdat.py       emdat.csv         EM-DAT disaster impact  (needs a token)
    fetch_oecd_climate.py oecd_climate.csv OECD adaptation finance (best effort)

Derived here:
    conflict_ucdp_battle_deaths     UCDP battle deaths / population * 100,000
    conflict_neighbor              # neighbours with >= 25 battle deaths that year
    forced_displacement           (refugees-from-country + IDPs) / population * 100
    climate_disaster_impact       people affected / population * 100   (if EM-DAT part present)
    climate_adaptation_finance    adaptation finance / GDP * 100       (if OECD part present)

indicators.csv is a build artifact — never hand-edit it.
"""

from __future__ import annotations

import csv
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "etl"))

from common import COLUMNS, PROCESSED_DIR, RAW_DIR, now_iso, read_part, row_for  # noqa: E402
from indicators import ARAB_COUNTRIES, INDICATORS, NEIGHBOURS  # noqa: E402

_BY_ID = {i.id: i for i in INDICATORS}
FETCHERS = [
    "fetch_worldbank.py",
    "fetch_ucdp.py",
    "fetch_unhcr.py",
    "fetch_emdat.py",
    "fetch_oecd_climate.py",
]
NEIGHBOUR_CONFLICT_THRESHOLD = 25


def run_fetchers() -> None:
    for script in FETCHERS:
        print(f"\n=== {script} ===")
        subprocess.run([sys.executable, str(ROOT / "etl" / script)], check=False)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _index(rows: list[dict], indicator_id: str) -> dict[tuple[str, int], float]:
    out: dict[tuple[str, int], float] = {}
    for r in rows:
        if r["indicator_id"] != indicator_id:
            continue
        v = _num(r["value"])
        if v is not None:
            out[(r["country_iso3"], int(r["year"]))] = v
    return out


def build() -> list[dict]:
    parts = {
        name: read_part(name)
        for name in ["worldbank", "ucdp", "unhcr", "emdat", "oecd_climate"]
    }
    merged: list[dict] = []
    for rows in parts.values():
        merged.extend(rows)

    wb = parts["worldbank"]
    pop = _index(wb, "SP.POP.TOTL")
    gdp_pc = _index(wb, "NY.GDP.PCAP.CD")
    gdp = {k: gdp_pc[k] * pop[k] for k in gdp_pc if k in pop}

    retrieved = now_iso()
    derived: list[dict] = []

    # --- battle-death table (all countries incl. non-Arab neighbours) --------
    brd_path = RAW_DIR / "ucdp" / "battle_deaths_by_country_year.json"
    brd_table: dict[str, dict[str, int]] = {}
    if brd_path.exists():
        brd_table = json.loads(brd_path.read_text()).get("table", {})

    def bd(iso3: str, year: int) -> int:
        return int(brd_table.get(iso3, {}).get(str(year), 0))

    # conflict intensity (per 100k) + neighbouring conflict
    years = sorted({int(r["year"]) for r in wb} | {int(y) for c in brd_table.values() for y in c})
    ci = _BY_ID["conflict_ucdp_battle_deaths"]
    nc = _BY_ID["conflict_neighbor"]
    for iso3, name in ARAB_COUNTRIES.items():
        for year in years:
            if not brd_table:  # no UCDP data at all -> emit nothing
                continue
            p = pop.get((iso3, year))
            if p:
                derived.append(row_for(ci, iso3, name, year, round(bd(iso3, year) / p * 100_000, 4), retrieved))
            n_neigh = sum(1 for nb in NEIGHBOURS.get(iso3, ()) if bd(nb, year) >= NEIGHBOUR_CONFLICT_THRESHOLD)
            derived.append(row_for(nc, iso3, name, year, n_neigh, retrieved))

    # forced displacement (% of population): origin + hosted refugees + IDPs
    ref = _index(parts["unhcr"], "displacement_refugees_origin")
    hosted = _index(parts["unhcr"], "displacement_refugees_hosted")
    idp = _index(parts["unhcr"], "displacement_idps")
    fd = _BY_ID["forced_displacement"]
    keys = set(ref) | set(hosted) | set(idp)
    for (iso3, year) in sorted(keys):
        p = pop.get((iso3, year))
        if not p or iso3 not in ARAB_COUNTRIES:
            continue
        total = ref.get((iso3, year), 0.0) + hosted.get((iso3, year), 0.0) + idp.get((iso3, year), 0.0)
        derived.append(row_for(fd, iso3, ARAB_COUNTRIES[iso3], year, round(total / p * 100, 4), retrieved))

    # EM-DAT disaster impact (% of population) -- only if the part has data
    affected = _index(parts["emdat"], "climate_disaster_impact_affected")
    if affected:
        di = _BY_ID["climate_disaster_impact"]
        for (iso3, year), n in affected.items():
            p = pop.get((iso3, year))
            if p:
                derived.append(row_for(di, iso3, ARAB_COUNTRIES[iso3], year, round(n / p * 100, 4), retrieved))

    # OECD adaptation finance (% of GDP) -- only if the part has data
    adapt = _index(parts["oecd_climate"], "climate_adaptation_finance_usd")
    if adapt:
        af = _BY_ID["climate_adaptation_finance"]
        for (iso3, year), usd_m in adapt.items():
            g = gdp.get((iso3, year))
            if g:
                derived.append(row_for(af, iso3, ARAB_COUNTRIES[iso3], year, round(usd_m * 1e6 / g * 100, 4), retrieved))

    merged.extend(derived)
    merged = [r for r in merged if _num(r["value"]) is not None]
    merged.sort(key=lambda r: (r["indicator_label"], r["country_name"], int(r["year"])))
    print(f"\nmerged {len(merged)} rows ({len(derived)} derived)")
    return merged


def main() -> None:
    if "--refresh" in sys.argv:
        run_fetchers()
    rows = build()
    out = PROCESSED_DIR / "indicators.csv"
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLUMNS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in COLUMNS})
    ids = sorted({r["indicator_id"] for r in rows})
    print(f"wrote {out}")
    print(f"{len(ids)} indicators: {', '.join(ids)}")


if __name__ == "__main__":
    main()
