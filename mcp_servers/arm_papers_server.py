"""
MCP server: retrieval over the source papers (the `papers.*` namespace).

Corpus = "Pathways for Peace" (World Bank / UN, 2018) plus the three ESCWA
Arab Risk Monitor papers, chunked with page-level citations. Offline TF-IDF;
needs data/papers/corpus.jsonl (built by `python etl/extract_papers.py`).

    python -m mcp_servers.arm_papers_server
"""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from mcp.server.mcpserver import MCPServer  # noqa: E402

from backend.tools import dispatch  # noqa: E402

server = MCPServer(
    "arm-papers",
    instructions="Search the conflict-prevention evidence base. Ground every policy "
    "recommendation in a retrieved passage and cite its page.",
)


@server.tool(
    name="papers.search",
    description="Search the source papers for passages relevant to a policy question. Returns "
    "text plus a page-level citation for each hit.",
)
def search(query: str, k: int = 5, doc_id: str | None = None) -> dict:
    """
    Args:
        query: A natural-language policy question or topic.
        k: Number of passages to return (default 5).
        doc_id: Optional single document — 'pathways-for-peace', 'arm-conceptual-framework',
            'arm-drivers-of-conflict', 'arm-vulnerability-resilience'.
    """
    return dispatch("papers.search", {"query": query, "k": k, "doc_id": doc_id})


@server.tool(
    name="papers.list_documents",
    description="List the source documents in the corpus with their bibliographic details.",
)
def list_documents() -> dict:
    return dispatch("papers.list_documents")


if __name__ == "__main__":
    server.run()
