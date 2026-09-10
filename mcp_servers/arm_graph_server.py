"""
MCP server: the Arab Risk Monitor knowledge graph (the `graph.*` namespace).

The graph links the Pathways for Peace prevention framework (pathway
elements, arenas of contestation, risk factors, policy levers, actors) to the
ESCWA indicators and to supporting passages in the papers. Read-only,
offline; needs data/graph/knowledge_graph.json (built by
`python etl/build_graph.py`).

    python -m mcp_servers.arm_graph_server
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from backend.tools import dispatch  # noqa: E402

server = MCPServer(
    "arm-graph",
    instructions="Traverse the Arab Risk Monitor knowledge graph to connect risk factors, "
    "policy levers, arenas of contestation and indicators.",
)


@server.tool(
    name="graph.search",
    description="Search the knowledge graph for nodes (risk factors, policy levers, arenas, "
    "actors, indicators) matching a topic.",
)
def graph_search(query: str, types: list[str] | None = None, limit: int = 8) -> dict:
    """
    Args:
        query: Topic or phrase.
        types: Optional filter — concept, pathway_element, arena, risk_factor, policy_lever,
            actor, indicator, paper.
        limit: Max nodes to return.
    """
    return dispatch("graph.search", {"query": query, "types": types, "limit": limit})


@server.tool(
    name="graph.node",
    description="Get one node in full: summary, grouped neighbours, linked indicators, and "
    "supporting passages from the papers with page citations.",
)
def graph_node(node_id: str) -> dict:
    """Args: node_id: Node id or label, e.g. 'water-stress' or 'Water stress'."""
    return dispatch("graph.node", {"node_id": node_id})


@server.tool(
    name="graph.neighbors",
    description="Get the neighbourhood subgraph around a node (nodes + edges), optionally "
    "filtered by relation and expanded to a given depth (1 or 2).",
)
def graph_neighbors(node_id: str, rels: list[str] | None = None, depth: int = 1) -> dict:
    return dispatch("graph.neighbors", {"node_id": node_id, "rels": rels, "depth": depth})


@server.tool(
    name="graph.path",
    description="Find the shortest chain of relationships between two nodes.",
)
def graph_path(source: str, target: str) -> dict:
    return dispatch("graph.path", {"source": source, "target": target})


if __name__ == "__main__":
    server.run()
