"""
Assemble the Arab Risk Monitor knowledge graph.

Inputs
  - etl/graph_seed.py      curated nodes + edges + indicator links
  - etl/indicators.py      the indicator registry (one graph node each)
  - data/papers/*          the paper corpus + manifest (evidence + citations)

Output
  - data/graph/knowledge_graph.json

For every conceptual node the script searches the papers corpus for the two
or three passages that best support it and attaches them as `evidence`, plus
an `evidence_in` edge to the source-paper node. This is what lets the graph
view (and the policy advisor) show "here is where the report says this",
with a page number, for any concept the user clicks on.

    python etl/build_graph.py           # requires the papers corpus to exist

Build artifact — regenerate, never hand-edit.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "etl"))

from etl import graph_seed  # noqa: E402
from etl.indicators import INDICATORS  # noqa: E402
from backend import papers_store  # noqa: E402

OUT_PATH = ROOT / "data" / "graph" / "knowledge_graph.json"

EVIDENCE_PER_NODE = 3
EVIDENCE_MIN_SCORE = 0.05


def build() -> dict:
    nodes: dict[str, dict] = {}
    edges: list[dict] = []

    # 1. curated conceptual nodes
    for n in graph_seed.NODES:
        nodes[n["id"]] = {
            "id": n["id"],
            "type": n["type"],
            "label": n["label"],
            "summary": n.get("summary", ""),
            "aliases": n.get("aliases", []),
            "evidence": [],
            "indicator_ids": [],
        }

    # 2. source-paper nodes (from the corpus manifest)
    docs = papers_store.list_documents()
    for d in docs:
        nodes[f"paper:{d['doc_id']}"] = {
            "id": f"paper:{d['doc_id']}",
            "type": "paper",
            "label": d["short_title"],
            "summary": f"{d['title']}. {d['authors']}, {d['year']}. {d['publisher']}.",
            "aliases": [],
            "url": d["url"],
            "evidence": [],
            "indicator_ids": [],
        }

    # 3. indicator nodes from the registry
    reg = {i.id: i for i in INDICATORS}
    for ind in INDICATORS:
        nid = f"indicator:{ind.id}"
        nodes[nid] = {
            "id": nid,
            "type": "indicator",
            "label": ind.label,
            "summary": f"{ind.variable} — {ind.pathway} pathway, {ind.risk_measure}. "
            f"Unit: {ind.unit}. Source: {ind.source_name} ({ind.source_dataset}). "
            f"Status: {ind.status}.",
            "aliases": [ind.id],
            "pathway": ind.pathway,
            "risk_measure": ind.risk_measure,
            "status": ind.status,
            "unit": ind.unit,
            "source_name": ind.source_name,
            "indicator_id": ind.id,
            "evidence": [],
            "indicator_ids": [],
        }

    # 4. curated edges
    known = set(nodes)
    for e in graph_seed.EDGES:
        if e["source"] not in known or e["target"] not in known:
            raise ValueError(f"edge references unknown node: {e}")
        edges.append({"source": e["source"], "target": e["target"], "rel": e["rel"], "note": e.get("note", "")})

    # 5. indicator -> concept links
    for ind_id, node_id in graph_seed.INDICATOR_LINKS.items():
        if ind_id not in reg:
            raise ValueError(f"INDICATOR_LINKS references unknown indicator {ind_id}")
        if node_id not in nodes:
            raise ValueError(f"INDICATOR_LINKS references unknown node {node_id}")
        nid = f"indicator:{ind_id}"
        edges.append({"source": node_id, "target": nid, "rel": "measured_by", "note": ""})
        nodes[node_id]["indicator_ids"].append(ind_id)

    # 6. attach paper evidence to every conceptual node
    for n in graph_seed.NODES:
        query = n.get("query") or n["label"]
        hits = papers_store.search(query, k=EVIDENCE_PER_NODE + 2)
        seen_docs: set[str] = set()
        kept = 0
        for h in hits:
            if h["score"] < EVIDENCE_MIN_SCORE:
                continue
            nodes[n["id"]]["evidence"].append(
                {
                    "doc_id": h["doc_id"],
                    "doc_short_title": h["doc_short_title"],
                    "page": h["page"],
                    "section": h["section"],
                    "citation": h["citation"],
                    "url": h["doc_url"],
                    "snippet": h["text"][:320].rsplit(" ", 1)[0] + "…",
                    "score": h["score"],
                }
            )
            if h["doc_id"] not in seen_docs:
                seen_docs.add(h["doc_id"])
                edges.append(
                    {
                        "source": n["id"],
                        "target": f"paper:{h['doc_id']}",
                        "rel": "recommended_in" if n["type"] == "policy_lever" else "evidence_in",
                        "note": f"p. {h['page']}",
                    }
                )
            kept += 1
            if kept >= EVIDENCE_PER_NODE:
                break

    # 7. degree, for the viz
    deg: dict[str, int] = {nid: 0 for nid in nodes}
    for e in edges:
        deg[e["source"]] += 1
        deg[e["target"]] += 1
    for nid, d in deg.items():
        nodes[nid]["degree"] = d

    type_counts: dict[str, int] = {}
    for n in nodes.values():
        type_counts[n["type"]] = type_counts.get(n["type"], 0) + 1

    return {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "node_count": len(nodes),
            "edge_count": len(edges),
            "type_counts": type_counts,
            "description": "Arab Risk Monitor knowledge graph: Pathways for Peace prevention "
            "framework cross-linked to ESCWA risk factors and live indicator data.",
        },
        "nodes": list(nodes.values()),
        "edges": edges,
    }


def main() -> None:
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    graph = build()
    OUT_PATH.write_text(json.dumps(graph, indent=2, ensure_ascii=False))
    m = graph["meta"]
    print(f"Wrote {OUT_PATH}")
    print(f"  {m['node_count']} nodes, {m['edge_count']} edges")
    print(f"  types: {m['type_counts']}")


if __name__ == "__main__":
    main()
