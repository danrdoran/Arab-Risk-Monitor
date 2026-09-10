"""
Indicator registry for the Arab Risk Monitor.

Every indicator here is taken from Annex 4 ("List of Indicators") of the
ESCWA paper "Arab Risk Monitor: Quantifying the drivers of risk of conflict,
version 1.0" (E/ESCWA/CL6.GCP/2023/TP.1). Each entry records the
pathway/theme/risk-measure taxonomy from that paper alongside the concrete,
machine-fetchable source used for live data.

`source` field is one of:
  "worldbank"  -> etl/fetch_worldbank.py   (World Bank / WGI, no key)
  "ucdp"       -> etl/fetch_ucdp.py         (UCDP static dataset, no key)
  "unhcr"      -> etl/fetch_unhcr.py        (UNHCR population API, no key)
  "emdat"      -> etl/fetch_emdat.py        (EM-DAT public API, needs a free token)
  "oecd"       -> etl/fetch_oecd_climate.py (OECD climate finance, best effort)
  "derived"    -> computed by etl/build_dataset.py from other indicators
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Indicator:
    id: str  # stable machine key (World Bank code where applicable)
    pathway: str  # Conflict | Climate | Development | Context
    theme: str
    risk_measure: str  # Vulnerability | Resilience | Context
    label: str
    variable: str  # precise definition, Annex 4 "Variable" column
    unit: str
    higher_is_worse: bool  # does a higher raw value mean MORE risk?
    source: str = "worldbank"
    source_name: str = "World Bank"
    source_dataset: str = "World Development Indicators"
    source_url: str = "https://data.worldbank.org/indicator/{id}"
    status: str = "live"  # live | planned
    # optional fixed bounds for min-max normalization (etl/build_scores.py);
    # used where the literature sets a threshold instead of an empirical range.
    norm_min: float | None = None
    norm_max: float | None = None
    notes: str = ""


INDICATORS: list[Indicator] = [
    # ---------------------------------------------------------------- Conflict
    Indicator(
        id="GOV_WGI_PV.EST",
        pathway="Conflict",
        theme="Historical Grievances",
        risk_measure="Vulnerability",
        label="Political stability",
        variable="Political Stability and Absence of Violence/Terrorism (governance estimate, -2.5 to 2.5)",
        unit="index (-2.5 to 2.5)",
        higher_is_worse=False,
        source_dataset="Worldwide Governance Indicators",
        norm_min=-2.5,
        norm_max=2.5,
    ),
    Indicator(
        id="MS.MIL.TOTL.TF.ZS",
        pathway="Conflict",
        theme="Enabling Environment",
        risk_measure="Resilience",
        label="Military size (personnel)",
        variable="Armed forces personnel as a share of total labor force",
        unit="% of labor force",
        higher_is_worse=False,
        notes="Annex 4 'Military size' variable 1 of 2.",
    ),
    Indicator(
        id="MS.MIL.XPND.GD.ZS",
        pathway="Conflict",
        theme="Enabling Environment",
        risk_measure="Resilience",
        label="Military expenditure",
        variable="Military expenditure as a share of GDP (SIPRI)",
        unit="% of GDP",
        higher_is_worse=False,
        source_name="World Bank / SIPRI",
        source_dataset="SIPRI Military Expenditure Database (via World Development Indicators)",
        notes="Annex 4 'Military size' variable 2 of 2 — now wired via the World Bank mirror of SIPRI.",
    ),
    Indicator(
        id="conflict_ucdp_battle_deaths",
        pathway="Conflict",
        theme="Historical Grievances",
        risk_measure="Vulnerability",
        label="Conflict intensity",
        variable="Battle-related deaths per 100,000 people (best estimate)",
        unit="deaths per 100,000",
        higher_is_worse=True,
        source="derived",
        source_name="Uppsala Conflict Data Program (UCDP) & UN DESA",
        source_dataset="UCDP Battle-Related Deaths Dataset v24.1",
        source_url="https://ucdp.uu.se/downloads/",
        norm_min=0.0,
        norm_max=50.0,
        notes="Derived by build_dataset.py: UCDP battle deaths by country-year / population * 100000.",
    ),
    Indicator(
        id="conflict_ucdp_battle_deaths_total",
        pathway="Context",
        theme="Conflict",
        risk_measure="Context",
        label="Battle-related deaths (count)",
        variable="Battle-related deaths in the country in the year (best estimate)",
        unit="deaths",
        higher_is_worse=True,
        source="ucdp",
        source_name="Uppsala Conflict Data Program (UCDP)",
        source_dataset="UCDP Battle-Related Deaths Dataset v24.1",
        source_url="https://ucdp.uu.se/downloads/",
    ),
    Indicator(
        id="conflict_neighbor",
        pathway="Conflict",
        theme="Historical Grievances",
        risk_measure="Vulnerability",
        label="Neighbouring conflict",
        variable="Number of neighbouring countries with at least 25 battle-related deaths in the year",
        unit="count",
        higher_is_worse=True,
        source="derived",
        source_name="UCDP & land-border adjacency",
        source_dataset="UCDP Battle-Related Deaths Dataset v24.1",
        source_url="https://ucdp.uu.se/downloads/",
        norm_min=0.0,
        norm_max=4.0,
        notes="Derived by build_dataset.py from UCDP battle deaths and the NEIGHBOURS adjacency map.",
    ),
    Indicator(
        id="forced_displacement",
        pathway="Conflict",
        theme="Enabling Environment",
        risk_measure="Resilience",
        label="Forced displacement",
        variable="Refugees connected to the country (originating + hosted) plus internally displaced persons, as a share of population",
        unit="% of population",
        higher_is_worse=True,
        source="derived",
        source_name="UNHCR & UN DESA",
        source_dataset="UNHCR Refugee Population Statistics",
        source_url="https://www.unhcr.org/refugee-statistics/",
        norm_min=0.0,
        norm_max=30.0,
        notes="Derived by build_dataset.py: (UNHCR refugees by origin + refugees hosted + IDPs) / population * 100. "
        "Captures both a country's own displacement crisis (origin) and its hosting burden (e.g. Jordan, Lebanon).",
    ),
    Indicator(
        id="displacement_refugees_origin",
        pathway="Context",
        theme="Displacement",
        risk_measure="Context",
        label="Refugees (from country)",
        variable="Refugees under UNHCR's mandate originating from the country",
        unit="people",
        higher_is_worse=True,
        source="unhcr",
        source_name="UNHCR",
        source_dataset="UNHCR Refugee Population Statistics",
        source_url="https://www.unhcr.org/refugee-statistics/",
    ),
    Indicator(
        id="displacement_refugees_hosted",
        pathway="Context",
        theme="Displacement",
        risk_measure="Context",
        label="Refugees (hosted)",
        variable="Refugees under UNHCR's mandate hosted in the country (by country of asylum)",
        unit="people",
        higher_is_worse=True,
        source="unhcr",
        source_name="UNHCR",
        source_dataset="UNHCR Refugee Population Statistics",
        source_url="https://www.unhcr.org/refugee-statistics/",
    ),
    Indicator(
        id="displacement_idps",
        pathway="Context",
        theme="Displacement",
        risk_measure="Context",
        label="Internally displaced persons",
        variable="Internally displaced persons of concern to UNHCR in the country",
        unit="people",
        higher_is_worse=True,
        source="unhcr",
        source_name="UNHCR",
        source_dataset="UNHCR Refugee Population Statistics",
        source_url="https://www.unhcr.org/refugee-statistics/",
    ),
    Indicator(
        id="GOV_WGI_VA.EST",
        pathway="Conflict",
        theme="Enabling Environment",
        risk_measure="Resilience",
        label="Voice and accountability",
        variable="Voice and Accountability (governance estimate, -2.5 to 2.5)",
        unit="index (-2.5 to 2.5)",
        higher_is_worse=False,
        source_dataset="Worldwide Governance Indicators",
        norm_min=-2.5,
        norm_max=2.5,
    ),
    # ---------------------------------------------------------------- Climate
    Indicator(
        id="NV.AGR.TOTL.ZS",
        pathway="Climate",
        theme="Natural Resources",
        risk_measure="Vulnerability",
        label="Reliance on agriculture",
        variable="Agriculture, forestry, and fishing, value added (% of GDP)",
        unit="% of GDP",
        higher_is_worse=True,
    ),
    Indicator(
        id="ER.H2O.FWST.ZS",
        pathway="Climate",
        theme="Natural Resources",
        risk_measure="Resilience",
        label="Water stress",
        variable="Freshwater withdrawal as a proportion of available freshwater resources "
        "(SDG 6.4.2)",
        unit="% of total renewable resources",
        higher_is_worse=True,
        norm_min=0.0,
        norm_max=100.0,
        notes="SDG indicator 6.4.2 (FAO AQUASTAT), mirrored by the World Bank as "
        "ER.H2O.FWST.ZS. This is the series the ARM 'drivers of conflict' paper "
        "(Natural Resource Resilience, eq. 9) actually specifies: total freshwater "
        "withdrawn by all sectors over total renewable resources, after deducting "
        "environmental water requirements. It supersedes ER.H2O.FWTL.ZS (withdrawals "
        "as a share of *internal* resources), which ignores external inflows and the "
        "environmental reserve and so is not the FAO water-stress measure. "
        "FAO/UN-Water stress classes: <25% none, 25-50% low, 50-75% medium, "
        "75-100% high, >100% critical. Scoring assumption (see build_scores.normalize): "
        "min-max on [0, 100] with the normalized value clipped to [0, 1], so 0% "
        "withdrawal maps to full natural-resource resilience and >=100% (critical, and "
        "common across the Arab region) saturates at zero resilience. The ARM paper "
        "adopts and documents this same caveat: it cannot distinguish between countries "
        "that are all above the 100% threshold. Raw percentages above 100 are kept "
        "as reported in indicators.csv; only the normalized score saturates.",
    ),
    Indicator(
        id="climate_disaster_impact",
        pathway="Climate",
        theme="Climate Hazards",
        risk_measure="Vulnerability",
        label="Human impact of natural disasters",
        variable="Total people affected by natural disasters in the year, as a share of population",
        unit="% of population",
        higher_is_worse=True,
        source="emdat",
        source_name="EM-DAT (CRED) & UN DESA",
        source_dataset="EM-DAT International Disaster Database",
        source_url="https://www.emdat.be/",
        status="planned",
        norm_min=0.0,
        norm_max=20.0,
        notes="Fetcher etl/fetch_emdat.py is wired but EM-DAT now needs a free API token "
        "(set EMDAT_API_TOKEN). Without it this indicator stays 'planned'.",
    ),
    Indicator(
        id="climate_adaptation_finance",
        pathway="Climate",
        theme="Climate Hazards",
        risk_measure="Resilience",
        label="Adaptation finance",
        variable="Climate adaptation-related development finance, as a share of GDP",
        unit="% of GDP",
        higher_is_worse=False,
        source="oecd",
        source_name="OECD",
        source_dataset="OECD Climate-Related Development Finance",
        source_url="https://www.oecd.org/dac/financing-sustainable-development/development-finance-topics/climate-change.htm",
        status="planned",
        notes="Fetcher etl/fetch_oecd_climate.py is wired (best effort against the OECD SDMX API). "
        "Set OECD_CLIMATE_DATAFLOW to pin the dataflow if the default stops resolving.",
    ),
    # ------------------------------------------------------------ Development
    Indicator(
        id="BX.TRF.PWKR.DT.GD.ZS",
        pathway="Development",
        theme="Economy",
        risk_measure="Vulnerability",
        label="Financial dependence (remittances)",
        variable="Personal remittances received (% of GDP)",
        unit="% of GDP",
        higher_is_worse=True,
    ),
    Indicator(
        id="DT.ODA.ODAT.GN.ZS",
        pathway="Development",
        theme="Economy",
        risk_measure="Vulnerability",
        label="Financial dependence (aid)",
        variable="Net ODA received (% of GNI)",
        unit="% of GNI",
        higher_is_worse=True,
    ),
    Indicator(
        id="NY.GDP.PCAP.CD",
        pathway="Development",
        theme="Economy",
        risk_measure="Resilience",
        label="Economic development",
        variable="GDP per capita (current US$)",
        unit="current US$",
        higher_is_worse=False,
    ),
    Indicator(
        id="NY.GDP.MKTP.KD.ZG",
        pathway="Development",
        theme="Economy",
        risk_measure="Resilience",
        label="Economic growth",
        variable="GDP growth (annual %)",
        unit="% annual",
        higher_is_worse=False,
        norm_min=-10.0,
        norm_max=10.0,
    ),
    Indicator(
        id="GC.TAX.TOTL.GD.ZS",
        pathway="Development",
        theme="Economy",
        risk_measure="Resilience",
        label="State capacity",
        variable="Tax revenue (% of GDP)",
        unit="% of GDP",
        higher_is_worse=False,
    ),
    Indicator(
        id="SL.UEM.TOTL.ZS",
        pathway="Development",
        theme="Society",
        risk_measure="Vulnerability",
        label="Unemployment",
        variable="Unemployment, total (% of total labor force) (modeled ILO estimate)",
        unit="% of labor force",
        higher_is_worse=True,
        source_dataset="World Development Indicators (ILO modeled estimate)",
    ),
    Indicator(
        id="SH.DYN.MORT",
        pathway="Development",
        theme="Society",
        risk_measure="Vulnerability",
        label="Infant mortality",
        variable="Mortality rate, under-5 (per 1,000 live births)",
        unit="per 1,000 live births",
        higher_is_worse=True,
    ),
    Indicator(
        id="GOV_WGI_CC.EST",
        pathway="Development",
        theme="Institutions",
        risk_measure="Vulnerability",
        label="Corruption",
        variable="Control of Corruption (governance estimate, -2.5 to 2.5)",
        unit="index (-2.5 to 2.5)",
        higher_is_worse=False,
        source_dataset="Worldwide Governance Indicators",
        norm_min=-2.5,
        norm_max=2.5,
        notes="Annex 4 measure is inverted here: a LOW control-of-corruption score means HIGH vulnerability.",
    ),
    Indicator(
        id="GOV_WGI_RL.EST",
        pathway="Development",
        theme="Institutions",
        risk_measure="Resilience",
        label="Rule of Law",
        variable="Rule of Law (governance estimate, -2.5 to 2.5)",
        unit="index (-2.5 to 2.5)",
        higher_is_worse=False,
        source_dataset="Worldwide Governance Indicators",
        norm_min=-2.5,
        norm_max=2.5,
    ),
    Indicator(
        id="SP.POP.TOTL",
        pathway="Context",
        theme="Population",
        risk_measure="Context",
        label="Population",
        variable="Population, total",
        unit="people",
        higher_is_worse=False,
    ),
]

LIVE_INDICATORS = [i for i in INDICATORS if i.status == "live"]
WORLDBANK_INDICATORS = [i for i in INDICATORS if i.source == "worldbank"]
SCORING_INDICATORS = [
    i for i in INDICATORS if i.risk_measure in ("Vulnerability", "Resilience") and i.status == "live"
]

# The 22 League of Arab States members covered by the Arab Risk Monitor,
# with ISO3 codes as used by the World Bank API.
ARAB_COUNTRIES: dict[str, str] = {
    "DZA": "Algeria",
    "BHR": "Bahrain",
    "COM": "Comoros",
    "DJI": "Djibouti",
    "EGY": "Egypt",
    "IRQ": "Iraq",
    "JOR": "Jordan",
    "KWT": "Kuwait",
    "LBN": "Lebanon",
    "LBY": "Libya",
    "MRT": "Mauritania",
    "MAR": "Morocco",
    "OMN": "Oman",
    "PSE": "State of Palestine",
    "QAT": "Qatar",
    "SAU": "Saudi Arabia",
    "SOM": "Somalia",
    "SDN": "Sudan",
    "SYR": "Syrian Arab Republic",
    "TUN": "Tunisia",
    "ARE": "United Arab Emirates",
    "YEM": "Yemen",
}

# Gleditsch-Ward / Correlates of War country numbers -> ISO3, for the 22 Arab
# states plus every land neighbour we need for the "neighbouring conflict"
# indicator. UCDP's battle-deaths dataset keys location by these numbers.
GW_TO_ISO3: dict[int, str] = {
    615: "DZA", 692: "BHR", 581: "COM", 522: "DJI", 651: "EGY", 645: "IRQ",
    663: "JOR", 690: "KWT", 660: "LBN", 620: "LBY", 435: "MRT", 600: "MAR",
    698: "OMN", 694: "QAT", 670: "SAU", 520: "SOM", 625: "SDN", 652: "SYR",
    616: "TUN", 696: "ARE", 679: "YEM", 678: "YEM", 680: "YEM",
    # non-Arab neighbours
    666: "ISR", 630: "IRN", 640: "TUR", 483: "TCD", 436: "NER", 432: "MLI",
    530: "ETH", 531: "ERI", 626: "SSD", 501: "KEN", 433: "SEN", 482: "CAF",
    616616: "PSE",  # sentinel, unused
}

# Land-border adjacency (ISO3 -> neighbours, ISO3). Mixes Arab and non-Arab
# neighbours; used only to count neighbours in conflict.
NEIGHBOURS: dict[str, tuple[str, ...]] = {
    "DZA": ("MAR", "TUN", "LBY", "MRT", "MLI", "NER"),
    "BHR": ("SAU",),
    "COM": (),
    "DJI": ("ERI", "ETH", "SOM"),
    "EGY": ("LBY", "SDN", "ISR", "PSE"),
    "IRQ": ("SYR", "JOR", "SAU", "KWT", "IRN", "TUR"),
    "JOR": ("SYR", "IRQ", "SAU", "ISR", "PSE"),
    "KWT": ("IRQ", "SAU"),
    "LBN": ("SYR", "ISR"),
    "LBY": ("TUN", "DZA", "NER", "TCD", "SDN", "EGY"),
    "MRT": ("MAR", "DZA", "MLI", "SEN"),
    "MAR": ("DZA", "MRT"),
    "OMN": ("SAU", "ARE", "YEM"),
    "PSE": ("ISR", "EGY", "JOR"),
    "QAT": ("SAU",),
    "SAU": ("JOR", "IRQ", "KWT", "QAT", "ARE", "OMN", "YEM"),
    "SOM": ("DJI", "ETH", "KEN"),
    "SDN": ("EGY", "LBY", "TCD", "CAF", "SSD", "ETH", "ERI"),
    "SYR": ("TUR", "IRQ", "JOR", "LBN", "ISR"),
    "TUN": ("DZA", "LBY"),
    "ARE": ("SAU", "OMN"),
    "YEM": ("SAU", "OMN"),
}
