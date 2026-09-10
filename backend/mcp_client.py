"""
Client pool for the three Arab Risk Monitor MCP servers.

The FastAPI app opens one `MCPPool` at startup (lifespan) and keeps the three
stdio sessions alive for the process. The orchestrator's subagents call
`pool.call("graph.path", {...})` and the pool routes to the right server by
the tool-name namespace.

Each server runs in its own long-lived asyncio task that owns the
`stdio_client` + `ClientSession` context managers for their whole lifetime
(entering and exiting them in the same task — anyio requires this). Other
tasks may safely call `session.call_tool` on the live session.

Set ARM_MCP=0 to skip the subprocesses entirely and run the same tools
in-process (backend.tools.dispatch) — handy for tests and constrained envs.
The agent sees an identical tool surface either way.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from . import tools as tools_mod

ROOT = Path(__file__).resolve().parent.parent

SERVERS = {
    "data": "mcp_servers.arm_data_server",
    "papers": "mcp_servers.arm_papers_server",
    "graph": "mcp_servers.arm_graph_server",
}


def mcp_enabled() -> bool:
    return os.environ.get("ARM_MCP", "1").strip().lower() not in ("0", "false", "no")


def _tool_specs(namespaces: list[str] | None = None) -> list[dict]:
    return [s for s in tools_mod.TOOL_SPECS if not namespaces or s["namespace"] in namespaces]


class _LocalPool:
    """Fallback: same tools, run in-process. No subprocesses."""

    transport = "in-process"

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None

    async def call(self, name: str, args: dict | None = None) -> dict:
        return tools_mod.dispatch(name, args or {})

    def tool_specs(self, namespaces: list[str] | None = None) -> list[dict]:
        return _tool_specs(namespaces)


def _result_to_dict(result) -> dict:
    if getattr(result, "structured_content", None) is not None:
        return result.structured_content
    if result.content:
        text = getattr(result.content[0], "text", "") or ""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return {"result": text, "is_error": result.is_error}
    return {"is_error": result.is_error}


class MCPPool:
    """Holds one live stdio ClientSession per MCP server, each in its own task."""

    transport = "mcp-stdio"

    def __init__(self) -> None:
        self._sessions: dict[str, ClientSession] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._tasks: list[asyncio.Task] = []
        self._stop = asyncio.Event()
        self._tool_index: dict[str, str] = {}
        self.started = False

    async def _serve(self, ns: str, module: str, ready: asyncio.Future) -> None:
        params = StdioServerParameters(
            command=sys.executable,
            args=["-m", module],
            cwd=str(ROOT),
            env={**os.environ},
        )
        try:
            async with stdio_client(params) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    listing = await session.list_tools()
                    tool_names = [t.name for t in listing.tools]
                    if not ready.done():
                        ready.set_result((session, tool_names))
                    await self._stop.wait()
        except Exception as exc:  # noqa: BLE001
            if not ready.done():
                ready.set_exception(exc)

    async def start(self) -> None:
        loop = asyncio.get_running_loop()
        readies: list[asyncio.Future] = []
        for ns, module in SERVERS.items():
            fut: asyncio.Future = loop.create_future()
            readies.append(fut)
            self._tasks.append(asyncio.create_task(self._serve(ns, module, fut), name=f"mcp-{ns}"))
        for ns, fut in zip(SERVERS, readies):
            session, tool_names = await asyncio.wait_for(fut, timeout=25)
            self._sessions[ns] = session
            self._locks[ns] = asyncio.Lock()
            for tn in tool_names:
                self._tool_index[tn] = ns
        self.started = True

    async def stop(self) -> None:
        self._stop.set()
        if self._tasks:
            await asyncio.wait(self._tasks, timeout=10)
        self.started = False

    async def call(self, name: str, args: dict | None = None) -> dict:
        ns = self._tool_index.get(name) or name.split(".", 1)[0]
        session = self._sessions.get(ns)
        if session is None:
            raise RuntimeError(f"no MCP server for tool '{name}'")
        async with self._locks[ns]:
            result = await session.call_tool(name, args or {})
        return _result_to_dict(result)

    def tool_specs(self, namespaces: list[str] | None = None) -> list[dict]:
        return _tool_specs(namespaces)


async def build_pool() -> "MCPPool | _LocalPool":
    """Bring up the MCP subprocesses; fall back to in-process tools on any failure."""
    if not mcp_enabled():
        pool = _LocalPool()
        await pool.start()
        return pool
    pool = MCPPool()
    try:
        await pool.start()
        return pool
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"[mcp] could not start MCP servers ({exc!r}); using in-process tools\n")
        try:
            await pool.stop()
        except Exception:
            pass
        local = _LocalPool()
        await local.start()
        return local
