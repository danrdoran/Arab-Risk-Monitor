"""Model Context Protocol servers for the Arab Risk Monitor.

Three standalone stdio MCP servers, each a thin wrapper over one namespace of
backend.tools:

    arm_data_server     data.*    — provenance-tagged indicator dataset
    arm_papers_server   papers.*  — retrieval over the source papers
    arm_graph_server    graph.*   — the knowledge graph

Run one directly with e.g. `python -m mcp_servers.arm_data_server`, point any
MCP client (Claude Desktop, the MCP Inspector, or backend/mcp_client.py) at
it. The FastAPI orchestrator launches all three and routes subagent tool
calls through them.
"""
