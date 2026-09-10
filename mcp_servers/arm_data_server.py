"""
MCP server: Arab Risk Monitor indicator data (the `data.*` namespace).

Every value returned carries its full provenance (source name, dataset, URL,
retrieval date) — the same guarantee the REST API gives. Read-only, offline;
needs data/processed/indicators.csv (built by `python etl/fetch_worldbank.py`).

    python -m mcp_servers.arm_data_server
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from backend.tools import dispatch  # noqa: E402

server = MCPServer(
    "arm-data",
    instructions="Provenance-tagged Arab Risk Monitor indicator data for the 22 League of "
    "Arab States countries. Use query_indicators for any statistic; never invent numbers.",
)


@server.tool(
    name="data.list_indicators",
    description="List every Arab Risk Monitor indicator: pathway, theme, risk measure "
    "(vulnerability/resilience), unit, data source and whether it is live or planned.",
)
def list_indicators() -> dict:
    return dispatch("data.list_indicators")


@server.tool(
    name="data.list_countries",
    description="List the 22 League of Arab States countries covered, with ISO3 codes.",
)
def list_countries() -> dict:
    return dispatch("data.list_countries")


@server.tool(
    name="data.query_indicators",
    description="Fetch indicator values with full source provenance (source name, dataset, URL, "
    "retrieval date). Use this for ANY number — never state a statistic from memory.",
)
def query_indicators(
    countries: list[str] | None = None,
    indicator_ids: list[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    latest_only: bool = False,
) -> dict:
    """
    Args:
        countries: Country names or ISO3 codes, e.g. ["Jordan", "YEM"]. Omit for all 22.
        indicator_ids: Indicator ids or labels, e.g. ["NY.GDP.PCAP.CD", "Unemployment"]. Omit for all.
        year_min: Earliest year to include.
        year_max: Latest year to include.
        latest_only: If true, only the most recent year per country/indicator.
    """
    return dispatch(
        "data.query_indicators",
        {
            "countries": countries,
            "indicator_ids": indicator_ids,
            "year_min": year_min,
            "year_max": year_max,
            "latest_only": latest_only,
        },
    )


@server.tool(
    name="data.risk_scores",
    description="Composite vulnerability / resilience / risk scores (0-1, ESCWA Annex 1 method) "
    "by country, pathway (Conflict / Climate / Development / Overall) and year.",
)
def risk_scores(
    countries: list[str] | None = None,
    pathways: list[str] | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    latest_only: bool = False,
) -> dict:
    """Args: pathways: Conflict / Climate / Development / Overall. latest_only: newest year per country/pathway."""
    return dispatch(
        "data.risk_scores",
        {
            "countries": countries,
            "pathways": pathways,
            "year_min": year_min,
            "year_max": year_max,
            "latest_only": latest_only,
        },
    )


@server.tool(
    name="data.risk_ranking",
    description="Rank the 22 Arab States on a composite score for one pathway and dimension.",
)
def risk_ranking(pathway: str = "Overall", dimension: str = "risk", year: int | None = None) -> dict:
    """Args: pathway: Conflict/Climate/Development/Overall. dimension: risk/vulnerability/resilience."""
    return dispatch("data.risk_ranking", {"pathway": pathway, "dimension": dimension, "year": year})


if __name__ == "__main__":
    server.run()
