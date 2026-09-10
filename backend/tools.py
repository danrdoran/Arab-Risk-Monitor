"""
The tool surface shared by the MCP servers and the in-process fallback.

Three namespaces, each backed by one MCP server (see mcp_servers/):

  data.*    the provenance-tagged indicator dataset   (backend.data_store)
  papers.*  retrieval over the source-paper corpus    (backend.papers_store)
  graph.*   the Arab Risk Monitor knowledge graph     (backend.graph_store)

`TOOL_SPECS` is the single definition of every tool (name, description, JSON
schema). `dispatch(name, args)` runs one. The MCP servers wrap `dispatch`;
the orchestrator's in-process backend calls it directly. Keeping one
definition means the agent sees exactly the same tools whether or not it is
going through MCP.
"""

from __future__ import annotations

from typing import Any

from . import data_store, graph_store, papers_store, scores_store

TOOL_SPECS: list[dict] = [
    # ---- data ---------------------------------------------------------
    {
        "namespace": "data",
        "name": "data.list_indicators",
        "description": "List every Arab Risk Monitor indicator: pathway, theme, risk measure "
        "(vulnerability/resilience), unit, data source and whether it is live or planned.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "namespace": "data",
        "name": "data.list_countries",
        "description": "List the 22 League of Arab States countries covered, with ISO3 codes.",
        "parameters": {"type": "object", "properties": {}},
    },
    {
        "namespace": "data",
        "name": "data.query_indicators",
        "description": "Fetch indicator values with full source provenance (source name, dataset, "
        "URL, retrieval date). Use this for ANY number — never state a statistic from memory.",
        "parameters": {
            "type": "object",
            "properties": {
                "countries": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Country names or ISO3 codes, e.g. ['Jordan','YEM']. Omit for all 22.",
                },
                "indicator_ids": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Indicator ids or labels, e.g. ['NY.GDP.PCAP.CD','Unemployment']. Omit for all.",
                },
                "year_min": {"type": "integer"},
                "year_max": {"type": "integer"},
                "latest_only": {"type": "boolean", "description": "Only the most recent year per country/indicator."},
            },
        },
    },
    {
        "namespace": "data",
        "name": "data.risk_scores",
        "description": "Composite vulnerability / resilience / risk scores (0-1, ESCWA Arab Risk "
        "Monitor Annex 1 methodology: min-max normalization, equal weights) by country, pathway "
        "(Conflict / Climate / Development / Overall) and year. Use for 'how at risk is country X', "
        "score trends, and where a country's vulnerability comes from.",
        "parameters": {
            "type": "object",
            "properties": {
                "countries": {"type": "array", "items": {"type": "string"}},
                "pathways": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Conflict, Climate, Development, Overall. Omit for all.",
                },
                "year_min": {"type": "integer"},
                "year_max": {"type": "integer"},
                "latest_only": {"type": "boolean"},
            },
        },
    },
    {
        "namespace": "data",
        "name": "data.risk_ranking",
        "description": "Rank the 22 Arab States on a composite score for one pathway and dimension.",
        "parameters": {
            "type": "object",
            "properties": {
                "pathway": {"type": "string", "description": "Conflict / Climate / Development / Overall (default Overall)."},
                "dimension": {"type": "string", "description": "risk / vulnerability / resilience (default risk)."},
                "year": {"type": "integer", "description": "Omit for the latest year."},
            },
        },
    },
    # ---- papers ------------------------------------------------------
    {
        "namespace": "papers",
        "name": "papers.search",
        "description": "Search the source papers (Pathways for Peace 2018, and the three ESCWA "
        "Arab Risk Monitor papers) for passages relevant to a policy question. Returns text plus "
        "a page-level citation for each hit. Use this to ground conflict-prevention guidance.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "A natural-language policy question or topic."},
                "k": {"type": "integer", "description": "Number of passages (default 5)."},
                "doc_id": {
                    "type": "string",
                    "description": "Optional: restrict to one document — 'pathways-for-peace', "
                    "'arm-conceptual-framework', 'arm-drivers-of-conflict', 'arm-vulnerability-resilience'.",
                },
            },
            "required": ["query"],
        },
    },
    {
        "namespace": "papers",
        "name": "papers.list_documents",
        "description": "List the source documents in the corpus with their bibliographic details.",
        "parameters": {"type": "object", "properties": {}},
    },
    # ---- graph -----------------------------------------------------
    {
        "namespace": "graph",
        "name": "graph.search",
        "description": "Search the knowledge graph for nodes (risk factors, policy levers, arenas "
        "of contestation, actors, indicators) matching a topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "types": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional filter: concept, pathway_element, arena, risk_factor, "
                    "policy_lever, actor, indicator, paper.",
                },
                "limit": {"type": "integer"},
            },
            "required": ["query"],
        },
    },
    {
        "namespace": "graph",
        "name": "graph.node",
        "description": "Get one knowledge-graph node in full: summary, grouped neighbours, linked "
        "Arab Risk Monitor indicators, and supporting passages from the papers with page citations.",
        "parameters": {
            "type": "object",
            "properties": {"node_id": {"type": "string", "description": "Node id or label, e.g. 'water-stress' or 'Water stress'."}},
            "required": ["node_id"],
        },
    },
    {
        "namespace": "graph",
        "name": "graph.neighbors",
        "description": "Get the neighbourhood subgraph around a node (nodes + edges), optionally "
        "filtered by relation and expanded to a given depth.",
        "parameters": {
            "type": "object",
            "properties": {
                "node_id": {"type": "string"},
                "rels": {"type": "array", "items": {"type": "string"}},
                "depth": {"type": "integer", "description": "1 or 2 (default 1)."},
            },
            "required": ["node_id"],
        },
    },
    {
        "namespace": "graph",
        "name": "graph.path",
        "description": "Find the shortest chain of relationships between two nodes — e.g. from a "
        "risk factor to a policy lever, or from an indicator to 'violent-conflict'.",
        "parameters": {
            "type": "object",
            "properties": {"source": {"type": "string"}, "target": {"type": "string"}},
            "required": ["source", "target"],
        },
    },
]

SPEC_BY_NAME = {s["name"]: s for s in TOOL_SPECS}


def specs_for(namespace: str) -> list[dict]:
    return [s for s in TOOL_SPECS if s["namespace"] == namespace]


def _cap_rows(rows: list[dict], limit: int = 400) -> list[dict]:
    return rows[:limit]


def dispatch(name: str, args: dict[str, Any] | None = None) -> dict:
    """Run one tool by fully-qualified name. Pure/local: no network, no LLM."""
    args = args or {}
    try:
        if name == "data.list_indicators":
            return {"indicators": data_store.list_indicators()}
        if name == "data.list_countries":
            return {"countries": data_store.list_countries()}
        if name == "data.query_indicators":
            df = data_store.query(
                countries=args.get("countries"),
                indicator_ids=args.get("indicator_ids"),
                year_min=args.get("year_min"),
                year_max=args.get("year_max"),
                latest_only=bool(args.get("latest_only", False)),
            )
            if df.empty:
                return {"rows": [], "row_count": 0, "note": "No matching data. Try data.list_indicators to check ids, or the indicator may be 'planned' (not yet wired to live data)."}
            rows = _cap_rows(df.to_dict(orient="records"))
            return {"rows": rows, "row_count": len(rows)}
        if name == "data.risk_scores":
            rows = scores_store.query(
                countries=args.get("countries"),
                pathways=args.get("pathways"),
                year_min=args.get("year_min"),
                year_max=args.get("year_max"),
                latest_only=bool(args.get("latest_only", False)),
            )
            return {"scores": _cap_rows(rows), "row_count": len(rows), "method": scores_store.meta().get("method")}
        if name == "data.risk_ranking":
            return {
                "ranking": scores_store.ranking(
                    pathway=args.get("pathway", "Overall"),
                    dimension=args.get("dimension", "risk"),
                    year=args.get("year"),
                )
            }

        if name == "papers.search":
            hits = papers_store.search(args["query"], k=int(args.get("k", 5)), doc_id=args.get("doc_id"))
            return {"passages": hits, "count": len(hits)}
        if name == "papers.list_documents":
            return {"documents": papers_store.list_documents()}

        if name == "graph.search":
            return {"nodes": graph_store.search(args["query"], types=args.get("types"), limit=int(args.get("limit", 8)))}
        if name == "graph.node":
            n = graph_store.node(args["node_id"])
            return n or {"error": f"no node matching '{args['node_id']}'"}
        if name == "graph.neighbors":
            return graph_store.neighbors(args["node_id"], rels=args.get("rels"), depth=int(args.get("depth", 1)))
        if name == "graph.path":
            return graph_store.path(args["source"], args["target"])
    except FileNotFoundError as exc:
        return {"error": f"data not built: {exc}"}
    except Exception as exc:  # keep the agent loop alive on a bad tool call
        return {"error": f"{type(exc).__name__}: {exc}"}

    return {"error": f"unknown tool '{name}'"}
