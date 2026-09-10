"""
Query layer over data/graph/knowledge_graph.json.

The graph connects the Pathways for Peace prevention framework (pathway
elements, arenas of contestation, risk factors, policy levers, actors) to the
Arab Risk Monitor indicators and to supporting passages in the source papers.
This module exposes the small set of read operations the API, the MCP graph
server and the policy-advisor subagent need: search, neighbourhood,
shortest path, and induced subgraph.

Read-only, no network. Regenerate the graph with `python etl/build_graph.py`.
"""

from __future__ import annotations

import json
import re
from collections import deque
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GRAPH_PATH = ROOT / "data" / "graph" / "knowledge_graph.json"

_TOKEN = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_TOKEN.findall(text.lower()))


class _Graph:
    def __init__(self) -> None:
        if not GRAPH_PATH.exists():
            raise FileNotFoundError(
                f"{GRAPH_PATH} not found. Run `python etl/build_graph.py` first."
            )
        data = json.loads(GRAPH_PATH.read_text())
        self.meta: dict = data["meta"]
        self.nodes: dict[str, dict] = {n["id"]: n for n in data["nodes"]}
        self.edges: list[dict] = data["edges"]
        self.adj: dict[str, list[dict]] = {nid: [] for nid in self.nodes}
        for e in self.edges:
            self.adj[e["source"]].append({"dir": "out", "rel": e["rel"], "other": e["target"], "note": e.get("note", "")})
            self.adj[e["target"]].append({"dir": "in", "rel": e["rel"], "other": e["source"], "note": e.get("note", "")})

    # ----------------------------------------------------------------
    def search(self, query: str, types: list[str] | str | None = None, limit: int = 8) -> list[dict]:
        if isinstance(types, str):
            types = [t.strip() for t in re.split(r"[,\s]+", types) if t.strip()]
        q = _tokens(query)
        if not q:
            return []
        scored: list[tuple[float, dict]] = []
        for node in self.nodes.values():
            if types and node["type"] not in types:
                continue
            hay = _tokens(node["label"]) | _tokens(" ".join(node.get("aliases", [])))
            summ = _tokens(node.get("summary", ""))
            score = 2.0 * len(q & hay) + 0.5 * len(q & summ)
            if node["label"].lower() == query.strip().lower():
                score += 5
            if score > 0:
                scored.append((score + node.get("degree", 0) * 0.01, node))
        scored.sort(key=lambda t: t[0], reverse=True)
        return [self._brief(n) for _, n in scored[:limit]]

    def node(self, node_id: str) -> dict | None:
        n = self.nodes.get(node_id) or self._resolve(node_id)
        if not n:
            return None
        grouped: dict[str, list[dict]] = {}
        for link in self.adj[n["id"]]:
            other = self.nodes[link["other"]]
            key = f"{link['rel']}:{link['dir']}"
            grouped.setdefault(key, []).append(
                {"id": other["id"], "label": other["label"], "type": other["type"], "note": link["note"]}
            )
        return {
            **n,
            "neighbors": grouped,
            "indicators": [self._brief(self.nodes[f"indicator:{i}"]) for i in n.get("indicator_ids", []) if f"indicator:{i}" in self.nodes],
        }

    def neighbors(self, node_id: str, rels: list[str] | str | None = None, depth: int = 1) -> dict:
        if isinstance(rels, str):
            rels = [r.strip() for r in re.split(r"[,\s]+", rels) if r.strip()]
        start = self._resolve(node_id)
        if not start:
            return {"nodes": [], "edges": []}
        keep_nodes = {start["id"]}
        frontier = {start["id"]}
        for _ in range(max(1, depth)):
            nxt: set[str] = set()
            for nid in frontier:
                for link in self.adj[nid]:
                    if rels and link["rel"] not in rels:
                        continue
                    nxt.add(link["other"])
            nxt -= keep_nodes
            keep_nodes |= nxt
            frontier = nxt
            if not frontier:
                break
        return self._induced(keep_nodes)

    def path(self, source: str, target: str) -> dict:
        a, b = self._resolve(source), self._resolve(target)
        if not a or not b:
            return {"found": False, "reason": "unknown node", "steps": []}
        prev: dict[str, tuple[str, str, str]] = {a["id"]: None}  # node -> (from, rel, dir)
        dq = deque([a["id"]])
        while dq:
            cur = dq.popleft()
            if cur == b["id"]:
                break
            for link in self.adj[cur]:
                if link["other"] not in prev:
                    prev[link["other"]] = (cur, link["rel"], link["dir"])
                    dq.append(link["other"])
        if b["id"] not in prev:
            return {"found": False, "reason": "no path", "steps": []}
        chain: list[str] = []
        cur = b["id"]
        while cur is not None:
            chain.append(cur)
            cur = prev[cur][0] if prev[cur] else None
        chain.reverse()
        steps = []
        for i in range(len(chain) - 1):
            frm, rel, direction = prev[chain[i + 1]]
            steps.append(
                {
                    "from": self.nodes[chain[i]]["label"],
                    "to": self.nodes[chain[i + 1]]["label"],
                    "rel": rel,
                    "phrase": self._phrase(chain[i], rel, chain[i + 1], direction),
                }
            )
        return {"found": True, "length": len(steps), "nodes": [self._brief(self.nodes[c]) for c in chain], "steps": steps}

    def subgraph(self, node_ids: list[str]) -> dict:
        resolved = {n["id"] for nid in node_ids if (n := self._resolve(nid))}
        return self._induced(resolved)

    def stats(self) -> dict:
        return self.meta

    # ----------------------------------------------------------------
    def _resolve(self, node_id: str) -> dict | None:
        if node_id in self.nodes:
            return self.nodes[node_id]
        for prefix in ("indicator:", "paper:"):
            if prefix + node_id in self.nodes:
                return self.nodes[prefix + node_id]
        low = node_id.strip().lower()
        for n in self.nodes.values():
            if n["label"].lower() == low or low in [a.lower() for a in n.get("aliases", [])]:
                return n
        return None

    def _brief(self, n: dict) -> dict:
        return {
            "id": n["id"],
            "label": n["label"],
            "type": n["type"],
            "summary": n.get("summary", ""),
            "degree": n.get("degree", 0),
        }

    def _induced(self, ids: set[str]) -> dict:
        ids = {i for i in ids if i in self.nodes}
        sub_edges = [
            {"source": e["source"], "target": e["target"], "rel": e["rel"], "note": e.get("note", "")}
            for e in self.edges
            if e["source"] in ids and e["target"] in ids
        ]
        return {
            "nodes": [
                {**self.nodes[i], "evidence": self.nodes[i].get("evidence", [])[:2]} for i in ids
            ],
            "edges": sub_edges,
        }

    def _phrase(self, a: str, rel: str, b: str, direction: str) -> str:
        la, lb = self.nodes[a]["label"], self.nodes[b]["label"]
        verb = {
            "drives": "drives", "mitigates": "mitigates", "strengthens": "strengthens",
            "undermines": "undermines", "contested_in": "is contested in",
            "measured_by": "is measured by", "monitored_by": "is monitored by",
            "part_of": "is part of", "intersects": "intersects with",
            "evidence_in": "is evidenced in", "recommended_in": "is recommended in",
        }.get(rel, rel)
        return f"{la} {verb} {lb}" if direction == "out" else f"{lb} {verb} {la}"


@lru_cache(maxsize=1)
def _graph() -> _Graph:
    return _Graph()


def search(query: str, types: list[str] | None = None, limit: int = 8) -> list[dict]:
    return _graph().search(query, types=types, limit=limit)


def node(node_id: str) -> dict | None:
    return _graph().node(node_id)


def neighbors(node_id: str, rels: list[str] | None = None, depth: int = 1) -> dict:
    return _graph().neighbors(node_id, rels=rels, depth=depth)


def path(source: str, target: str) -> dict:
    return _graph().path(source, target)


def subgraph(node_ids: list[str]) -> dict:
    return _graph().subgraph(node_ids)


def full() -> dict:
    g = _graph()
    return {"meta": g.meta, "nodes": list(g.nodes.values()), "edges": g.edges}


def stats() -> dict:
    return _graph().stats()


def loaded() -> bool:
    try:
        _graph()
        return True
    except FileNotFoundError:
        return False


if __name__ == "__main__":
    import sys

    if len(sys.argv) >= 3 and sys.argv[1] == "path":
        print(json.dumps(path(sys.argv[2], sys.argv[3]), indent=2, ensure_ascii=False))
    else:
        q = " ".join(sys.argv[1:]) or "youth unemployment"
        for hit in search(q):
            print(f"{hit['type']:16} {hit['id']:32} {hit['label']}")
