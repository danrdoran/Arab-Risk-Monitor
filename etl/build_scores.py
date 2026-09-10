"""
Composite vulnerability / resilience / risk scores, following the ESCWA
Arab Risk Monitor methodology (Annex 1 of "Quantifying the drivers of risk
of conflict", E/ESCWA/CL6.GCP/2023/TP.1).

Method
------
1. Normalization: min-max to [0, 1] per indicator, across the 22-country ×
   all-years panel. Where the registry sets `norm_min` / `norm_max` (a
   literature threshold), those bounds are used instead of the empirical
   range (the paper does this for some natural-resource indicators).
2. Direction: each normalized value is turned into a 0-1 "risk-increasing"
   value `bad` (0 = best, 1 = worst) using the registry `higher_is_worse`
   flag.  vulnerability contribution = bad;  resilience contribution = 1 - bad.
3. Aggregation: equal weights, two steps — indicators -> theme, themes ->
   pathway — for the vulnerability and resilience dimensions separately.
4. Pathway scores are averaged into an "Overall" row.
5. Risk (our synthesis, not in the paper): (vulnerability + (1 - resilience)) / 2.
6. Levels use the paper's bands: 0.0-0.2 very low, 0.2-0.4 low, 0.4-0.6
   moderate, 0.6-0.8 high, 0.8-1.0 very high (Table A1.1).

Missing data is carried forward per country up to `LOCF_MAX_GAP` years, then
themes with no data are simply dropped from that country-year's average.

    python etl/build_scores.py

Output: data/processed/scores.csv  +  data/processed/scores_meta.json
Build artifact — regenerate, never hand-edit.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "etl"))

from indicators import ARAB_COUNTRIES, INDICATORS  # noqa: E402

DATA = ROOT / "data" / "processed" / "indicators.csv"
OUT_CSV = ROOT / "data" / "processed" / "scores.csv"
OUT_META = ROOT / "data" / "processed" / "scores_meta.json"

MIN_YEAR = 2005
MAX_YEAR = 2024  # most upstream series stop here; beyond this is all LOCF
LOCF_MAX_GAP = 5

_SCORING = [
    i for i in INDICATORS
    if i.risk_measure in ("Vulnerability", "Resilience") and i.status == "live"
]
_BY_ID = {i.id: i for i in _SCORING}

LEVEL_BANDS = [
    (0.8, "very high"),
    (0.6, "high"),
    (0.4, "moderate"),
    (0.2, "low"),
    (0.0, "very low"),
]


def level(score: float) -> str:
    for lo, name in LEVEL_BANDS:
        if score >= lo:
            return name
    return "very low"


def load() -> pd.DataFrame:
    df = pd.read_csv(DATA)
    df = df[df["indicator_id"].isin(_BY_ID)].copy()
    df = df[df["country_iso3"].isin(ARAB_COUNTRIES)]
    df["year"] = df["year"].astype(int)
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    return df.dropna(subset=["value"])


def normalize(df: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Add a `bad` column in [0,1] (0 best, 1 worst) and return the bounds used."""
    meta: dict[str, dict] = {}
    out = []
    for iid, grp in df.groupby("indicator_id"):
        ind = _BY_ID[iid]
        lo = ind.norm_min if ind.norm_min is not None else float(grp["value"].min())
        hi = ind.norm_max if ind.norm_max is not None else float(grp["value"].max())
        span = hi - lo or 1.0
        norm = ((grp["value"] - lo) / span).clip(0, 1)
        grp = grp.assign(bad=norm if ind.higher_is_worse else (1 - norm))
        out.append(grp)
        meta[iid] = {
            "label": ind.label,
            "pathway": ind.pathway,
            "theme": ind.theme,
            "risk_measure": ind.risk_measure,
            "higher_is_worse": ind.higher_is_worse,
            "norm_min": round(lo, 4),
            "norm_max": round(hi, 4),
            "bounds_source": "registry threshold" if ind.norm_min is not None else "empirical (panel min/max)",
        }
    return pd.concat(out, ignore_index=True), meta


def densify(df: pd.DataFrame) -> pd.DataFrame:
    """One row per country × indicator × year (MIN_YEAR..max), LOCF-filled up
    to LOCF_MAX_GAP years."""
    years = list(range(MIN_YEAR, min(int(df["year"].max()), MAX_YEAR) + 1))
    frames = []
    for (iso3, iid), grp in df.groupby(["country_iso3", "indicator_id"]):
        s = grp.set_index("year")["bad"].reindex(years)
        s = s.ffill(limit=LOCF_MAX_GAP)
        frames.append(
            pd.DataFrame(
                {"country_iso3": iso3, "indicator_id": iid, "year": years, "bad": s.values}
            )
        )
    dense = pd.concat(frames, ignore_index=True).dropna(subset=["bad"])
    meta = {i.id: (i.pathway, i.theme, i.risk_measure) for i in _SCORING}
    dense["pathway"] = dense["indicator_id"].map(lambda x: meta[x][0])
    dense["theme"] = dense["indicator_id"].map(lambda x: meta[x][1])
    dense["risk_measure"] = dense["indicator_id"].map(lambda x: meta[x][2])
    return dense


def aggregate(dense: pd.DataFrame) -> pd.DataFrame:
    # indicator -> theme (equal weight)
    theme = (
        dense.groupby(["country_iso3", "year", "pathway", "risk_measure", "theme"])["bad"]
        .mean()
        .reset_index()
    )
    # theme -> pathway (equal weight)
    pathway = (
        theme.groupby(["country_iso3", "year", "pathway", "risk_measure"])["bad"]
        .mean()
        .reset_index()
    )
    # vulnerability dimension = mean bad;  resilience dimension = 1 - mean bad
    rows = []
    for (iso3, year, pw), grp in pathway.groupby(["country_iso3", "year", "pathway"]):
        v = grp.loc[grp["risk_measure"] == "Vulnerability", "bad"]
        r = grp.loc[grp["risk_measure"] == "Resilience", "bad"]
        vuln = float(v.mean()) if len(v) else np.nan
        resil = float(1 - r.mean()) if len(r) else np.nan
        n = int(
            dense[(dense.country_iso3 == iso3) & (dense.year == year) & (dense.pathway == pw)][
                "indicator_id"
            ].nunique()
        )
        rows.append({"country_iso3": iso3, "year": year, "pathway": pw, "vulnerability": vuln, "resilience": resil, "n_indicators": n})
    pw_df = pd.DataFrame(rows)

    # Overall = mean across pathways
    overall = (
        pw_df.groupby(["country_iso3", "year"])[["vulnerability", "resilience", "n_indicators"]]
        .agg({"vulnerability": "mean", "resilience": "mean", "n_indicators": "sum"})
        .reset_index()
    )
    overall["pathway"] = "Overall"
    final = pd.concat([pw_df, overall], ignore_index=True)

    # risk = mean of [vulnerability, 1 - resilience] over whichever dimensions
    # we actually have (rather than injecting a neutral 0.5 for a missing one).
    def _risk(row):
        parts = []
        if pd.notna(row["vulnerability"]):
            parts.append(row["vulnerability"])
        if pd.notna(row["resilience"]):
            parts.append(1 - row["resilience"])
        return float(np.mean(parts)) if parts else np.nan

    final["risk"] = final.apply(_risk, axis=1)
    final["vulnerability"] = final["vulnerability"].round(4)
    final["resilience"] = final["resilience"].round(4)
    final["risk"] = final["risk"].round(4)
    final["vulnerability_level"] = final["vulnerability"].apply(lambda x: level(x) if pd.notna(x) else None)
    final["resilience_level"] = final["resilience"].apply(lambda x: level(x) if pd.notna(x) else None)
    final["risk_level"] = final["risk"].apply(level)
    final["country_name"] = final["country_iso3"].map(ARAB_COUNTRIES)
    return final[
        [
            "country_iso3", "country_name", "year", "pathway",
            "vulnerability", "resilience", "risk",
            "vulnerability_level", "resilience_level", "risk_level", "n_indicators",
        ]
    ].sort_values(["country_name", "pathway", "year"])


def main() -> None:
    df = load()
    normed, bounds = normalize(df)
    dense = densify(normed)
    scores = aggregate(dense)
    scores.to_csv(OUT_CSV, index=False)

    OUT_META.write_text(
        json.dumps(
            {
                "method": "ESCWA Arab Risk Monitor Annex 1: min-max normalization, equal weights, "
                "two-step aggregation (indicator->theme->pathway). risk = (vulnerability + "
                "(1 - resilience)) / 2 is this project's synthesis, not from the paper.",
                "level_bands": {name: lo for lo, name in LEVEL_BANDS},
                "min_year": MIN_YEAR,
                "locf_max_gap_years": LOCF_MAX_GAP,
                "indicators": bounds,
            },
            indent=2,
        )
    )
    latest = int(scores["year"].max())
    print(f"wrote {OUT_CSV}  ({len(scores)} rows, through {latest})")
    print(scores[(scores.year == latest) & (scores.pathway == "Overall")][
        ["country_name", "vulnerability", "resilience", "risk", "risk_level"]
    ].to_string(index=False))


if __name__ == "__main__":
    main()
