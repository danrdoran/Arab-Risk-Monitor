"""
The conflict-prevention advisor: a small orchestration / subagent loop.

    ┌─────────────────────────────────────────────────────────────┐
    │  LEAD AGENT  (gpt-4o)                                         │
    │  Plans the answer, delegates, synthesises cited guidance.    │
    │        │ consult_data_analyst        │ consult_policy_advisor │
    ▼        ▼                              ▼                        ▼
  DATA ANALYST  (gpt-4o-mini)            POLICY ADVISOR  (gpt-4o-mini)
  tools: data.*  via MCP                 tools: papers.* + graph.*  via MCP
  → indicator values + provenance        → Pathways for Peace passages (p. …)
                                         → knowledge-graph risk↔lever links

Each subagent runs its own bounded tool-calling loop against the MCP servers
(backend/mcp_client.py). The lead never touches raw tools — it reads the
subagents' briefs and writes the final answer, in the user's language
(English, French or Arabic), with every number and recommendation cited.

Needs OPENAI_API_KEY. Model ids are configurable:
    ARM_LEAD_MODEL      (default gpt-4o)
    ARM_SUBAGENT_MODEL  (default gpt-4o-mini)
"""

from __future__ import annotations

import json
import os

from openai import AsyncOpenAI

from . import graph_store
from .i18n import language_directive
from .tools import TOOL_SPECS

LEAD_MODEL = os.environ.get("ARM_LEAD_MODEL", "gpt-4o")
SUBAGENT_MODEL = os.environ.get("ARM_SUBAGENT_MODEL", "gpt-4o-mini")

MAX_LEAD_STEPS = 5
MAX_SUBAGENT_STEPS = 5
MAX_ROWS_TO_MODEL = 120


# --------------------------------------------------------------------- prompts
LEAD_SYSTEM = """You are the Arab Risk Monitor **conflict-prevention advisor**.

You help national policy makers and multilateral staff turn a question into \
concrete, evidence-based conflict-prevention guidance for the 22 League of \
Arab States countries. Your evidence base:
- **Pathways for Peace** (World Bank / United Nations, 2018) — the framework \
and evidence on preventing violent conflict (actors, institutions, structural \
factors; the four arenas of contestation; sustained/inclusive/targeted \
prevention).
- **ESCWA's Arab Risk Monitor** three-paper series — the regional risk \
taxonomy of vulnerability vs. resilience across the Conflict, Climate and \
Development pathways, and the indicator dataset.

You have two specialists. Delegate to them; do not answer substantive \
questions from your own knowledge:
- `consult_policy_advisor` — retrieves passages from Pathways for Peace and \
the ESCWA papers and traverses the knowledge graph (risk factors → policy \
levers → indicators). Use for "what should we do", framework, and \
cause/mechanism questions.
- `consult_data_analyst` — queries the provenance-tagged indicator dataset. \
Use for any number, trend or country comparison.

Workflow:
1. Decide which specialist(s) you need. For a typical policy question, \
consult the policy advisor first, then the data analyst to ground it in the \
country's actual indicators.
2. You may call them more than once to go deeper.
3. Synthesise a single answer with this shape:
   • **Read of the situation** (1–2 sentences)
   • **What the evidence says** — mechanisms, each tied to a citation
   • **Recommended levers** — 2–4 concrete measures, each linked to the risk \
factor it addresses and a Pathways for Peace citation
   • **Caveats & data gaps** — planned/missing indicators, uncertainty
4. Cite inline. Papers: "(Pathways for Peace, 2018, p. 277)". Data: "(World \
Bank WGI, retrieved 2026-09-09)". Never invent a number or a page.
5. Be concise and skimmable. Use short bullets.

{language_directive}
"""

POLICY_ADVISOR_SYSTEM = """You are the policy-advisor specialist for the Arab Risk Monitor.

Given a question, assemble the conflict-prevention evidence for it:
- Call `papers.search` (2–4 times with varied phrasings) to pull the most \
relevant passages, primarily from "Pathways for Peace" (2018). Prefer \
`doc_id='pathways-for-peace'` for prevention guidance; use the ESCWA papers \
for the regional risk taxonomy.
- Use `graph.search` then `graph.node` / `graph.path` to map the relevant \
risk factors to the policy levers that mitigate them and the indicators that \
measure them.

Return a tight brief (≤ 250 words) that the lead advisor will build on:
- the mechanism(s) linking the issue to conflict risk,
- 2–4 candidate policy levers, each with the risk factor it addresses,
- for every claim, the exact citation string "(short title, year, p. N)",
- the knowledge-graph node ids you found most central (list them).
Do not write the final user-facing answer; hand up findings + citations."""

DATA_ANALYST_SYSTEM = """You are the data-analyst specialist for the Arab Risk Monitor.

Answer only from the dataset tools:
- `data.query_indicators` for raw indicator values (use `data.list_indicators` \
if unsure of an id). Never state a number you did not get from a tool.
- `data.risk_scores` / `data.risk_ranking` for the composite vulnerability, \
resilience and risk scores (0-1, ESCWA Annex 1 method) by pathway. Use these \
for "how at risk is X", rankings and score trends.
- If an indicator is 'planned' (not yet wired to live data), say so and name \
the intended source instead of guessing.

Return a short brief (≤ 200 words):
- the key values / scores / trend / ranking, with units,
- the provenance for each (source name + retrieval date; for scores, note the \
number of indicators behind the score),
- one line on data limitations (coverage, latest year, planned indicators).
Do not write the final user-facing answer."""


# --------------------------------------------------------------- OpenAI helpers
def _client() -> AsyncOpenAI:
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError(
            "OPENAI_API_KEY is not set. Add it to your .env at the repo root "
            "(the Advisor and Explore-data tabs still work without it)."
        )
    return AsyncOpenAI(api_key=key)


def _fn_name(tool_name: str) -> str:
    return tool_name.replace(".", "__")


def _tool_name(fn_name: str) -> str:
    return fn_name.replace("__", ".")


def _openai_tools(namespaces: list[str]) -> list[dict]:
    out = []
    for spec in TOOL_SPECS:
        if spec["namespace"] not in namespaces:
            continue
        out.append(
            {
                "type": "function",
                "function": {
                    "name": _fn_name(spec["name"]),
                    "description": spec["description"],
                    "parameters": spec["parameters"],
                },
            }
        )
    return out


# --------------------------------------------------------------------- subagent
async def _run_subagent(
    *,
    role: str,
    system_prompt: str,
    question: str,
    namespaces: list[str],
    pool,
) -> dict:
    client = _client()
    tools = _openai_tools(namespaces)
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": question},
    ]

    data_citations: list[dict] = []
    paper_citations: list[dict] = []
    graph_node_ids: list[str] = []
    chart_rows: list[dict] = []
    score_rows: list[dict] = []
    tool_log: list[str] = []

    for _ in range(MAX_SUBAGENT_STEPS):
        resp = await client.chat.completions.create(
            model=SUBAGENT_MODEL,
            messages=messages,
            tools=tools,
            tool_choice="auto",
            temperature=0.1,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            return {
                "role": role,
                "brief": msg.content or "",
                "data_citations": data_citations,
                "paper_citations": paper_citations,
                "graph_node_ids": _dedupe(graph_node_ids),
                "chart_rows": chart_rows,
                "score_rows": score_rows,
                "tool_log": tool_log,
            }

        messages.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            }
        )
        for tc in msg.tool_calls:
            name = _tool_name(tc.function.name)
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            result = await pool.call(name, args)
            tool_log.append(f"{role}:{name}({_short_args(args)})")
            _harvest(name, result, data_citations, paper_citations, graph_node_ids, chart_rows, score_rows)
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(_trim_for_model(name, result), default=str)[:12000],
                }
            )

    return {
        "role": role,
        "brief": "(the specialist ran out of steps before concluding)",
        "data_citations": data_citations,
        "paper_citations": paper_citations,
        "graph_node_ids": _dedupe(graph_node_ids),
        "chart_rows": chart_rows,
        "score_rows": score_rows,
        "tool_log": tool_log,
    }


# --------------------------------------------------------------------- lead loop
async def run(messages: list[dict], lang: str = "en") -> dict:
    client = _client()
    pool = _ambient_pool()

    lead_tools = [
        {
            "type": "function",
            "function": {
                "name": "consult_policy_advisor",
                "description": "Ask the policy-advisor specialist for the conflict-prevention "
                "evidence on a question: relevant Pathways for Peace / ESCWA passages (with "
                "page citations) and the risk-factor → policy-lever → indicator links from the "
                "knowledge graph.",
                "parameters": {
                    "type": "object",
                    "properties": {"question": {"type": "string", "description": "A focused sub-question."}},
                    "required": ["question"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "consult_data_analyst",
                "description": "Ask the data-analyst specialist for indicator values, trends or "
                "country comparisons from the provenance-tagged Arab Risk Monitor dataset.",
                "parameters": {
                    "type": "object",
                    "properties": {"question": {"type": "string", "description": "A focused data question, naming countries/indicators/years."}},
                    "required": ["question"],
                },
            },
        },
    ]

    convo = [
        {"role": "system", "content": LEAD_SYSTEM.replace("{language_directive}", language_directive(lang))}
    ] + messages

    all_data_citations: list[dict] = []
    all_paper_citations: list[dict] = []
    all_graph_nodes: list[str] = []
    all_chart_rows: list[dict] = []
    all_score_rows: list[dict] = []
    trace: list[dict] = []

    final_reply = ""
    for _ in range(MAX_LEAD_STEPS):
        resp = await client.chat.completions.create(
            model=LEAD_MODEL,
            messages=convo,
            tools=lead_tools,
            tool_choice="auto",
            temperature=0.25,
        )
        msg = resp.choices[0].message
        if not msg.tool_calls:
            final_reply = msg.content or ""
            break

        convo.append(
            {
                "role": "assistant",
                "content": msg.content,
                "tool_calls": [tc.model_dump() for tc in msg.tool_calls],
            }
        )
        for tc in msg.tool_calls:
            try:
                args = json.loads(tc.function.arguments or "{}")
            except json.JSONDecodeError:
                args = {}
            question = args.get("question", "")

            if tc.function.name == "consult_policy_advisor":
                sub = await _run_subagent(
                    role="policy_advisor",
                    system_prompt=POLICY_ADVISOR_SYSTEM,
                    question=question,
                    namespaces=["papers", "graph"],
                    pool=pool,
                )
            elif tc.function.name == "consult_data_analyst":
                sub = await _run_subagent(
                    role="data_analyst",
                    system_prompt=DATA_ANALYST_SYSTEM,
                    question=question,
                    namespaces=["data"],
                    pool=pool,
                )
            else:
                sub = {"role": "unknown", "brief": f"no such specialist: {tc.function.name}"}

            all_data_citations.extend(sub.get("data_citations", []))
            all_paper_citations.extend(sub.get("paper_citations", []))
            all_graph_nodes.extend(sub.get("graph_node_ids", []))
            all_chart_rows.extend(sub.get("chart_rows", []))
            all_score_rows.extend(sub.get("score_rows", []))
            trace.append(
                {
                    "specialist": sub["role"],
                    "question": question,
                    "tools_used": sub.get("tool_log", []),
                }
            )

            convo.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "content": json.dumps(
                        {
                            "brief": sub["brief"],
                            "paper_citations": sub.get("paper_citations", [])[:8],
                            "data_points": _brief_data(sub.get("data_citations", [])),
                            "graph_nodes": sub.get("graph_node_ids", []),
                        },
                        default=str,
                    )[:12000],
                }
            )
    else:
        final_reply = final_reply or "I wasn't able to finish composing an answer — please try narrowing the question."

    graph_context = _graph_context(all_graph_nodes)

    return {
        "reply": final_reply,
        "citations": _dedupe_dicts(all_data_citations, ("indicator_label", "country_name", "year")),
        "paper_citations": _dedupe_dicts(all_paper_citations, ("doc_id", "page")),
        "chart_rows": all_chart_rows,
        "score_rows": _dedupe_dicts(all_score_rows, ("country_iso3", "pathway", "year")),
        "graph_context": graph_context,
        "trace": trace,
        "models": {"lead": LEAD_MODEL, "subagent": SUBAGENT_MODEL, "transport": getattr(pool, "transport", "?")},
    }


# --------------------------------------------------------------------- helpers
_POOL_HOLDER: dict[str, object] = {}


def set_pool(pool) -> None:
    _POOL_HOLDER["pool"] = pool


def _ambient_pool():
    pool = _POOL_HOLDER.get("pool")
    if pool is None:
        raise RuntimeError("MCP pool not initialised (app lifespan did not run).")
    return pool


def _dedupe(items: list[str]) -> list[str]:
    seen: set[str] = set()
    out = []
    for i in items:
        if i not in seen:
            seen.add(i)
            out.append(i)
    return out


def _dedupe_dicts(items: list[dict], key_fields: tuple[str, ...]) -> list[dict]:
    seen: set = set()
    out = []
    for it in items:
        k = tuple(it.get(f) for f in key_fields)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def _short_args(args: dict) -> str:
    return ", ".join(f"{k}={v}" for k, v in list(args.items())[:3] if v not in (None, [], ""))


def _brief_data(cits: list[dict]) -> list[dict]:
    return [
        {
            "indicator": c.get("indicator_label"),
            "country": c.get("country_name"),
            "year": c.get("year"),
            "value": c.get("value"),
            "source": c.get("source_name"),
        }
        for c in cits[:40]
    ]


def _harvest(name, result, data_c, paper_c, graph_ids, chart_rows, score_rows) -> None:
    if not isinstance(result, dict):
        return
    if name == "data.risk_scores":
        score_rows.extend(result.get("scores", []))
    elif name == "data.risk_ranking":
        score_rows.extend(
            {
                "country_iso3": r.get("country_iso3"),
                "country_name": r.get("country_name"),
                "year": r.get("year"),
                "pathway": r.get("pathway"),
                "risk": r.get("value") if r.get("value") is not None else None,
                "_ranking_dimension": r.get("level"),
            }
            for r in result.get("ranking", [])
        )
    elif name == "data.query_indicators":
        for row in result.get("rows", []):
            data_c.append(
                {
                    "indicator_label": row.get("indicator_label"),
                    "indicator_id": row.get("indicator_id"),
                    "country_name": row.get("country_name"),
                    "country_iso3": row.get("country_iso3"),
                    "year": row.get("year"),
                    "value": row.get("value"),
                    "unit": row.get("unit"),
                    "pathway": row.get("pathway"),
                    "source_name": row.get("source_name"),
                    "source_dataset": row.get("source_dataset"),
                    "source_url": row.get("source_url"),
                    "retrieved_at": row.get("retrieved_at"),
                }
            )
            chart_rows.append(row)
    elif name == "papers.search":
        for p in result.get("passages", []):
            paper_c.append(
                {
                    "doc_id": p.get("doc_id"),
                    "doc_short_title": p.get("doc_short_title"),
                    "doc_year": p.get("doc_year"),
                    "page": p.get("page"),
                    "section": p.get("section"),
                    "citation": p.get("citation"),
                    "url": p.get("doc_url"),
                    "snippet": (p.get("text") or "")[:300],
                }
            )
    elif name in ("graph.search",):
        for n in result.get("nodes", []):
            graph_ids.append(n.get("id"))
    elif name in ("graph.node",):
        if result.get("id"):
            graph_ids.append(result["id"])
        for group in (result.get("neighbors") or {}).values():
            for nb in group:
                graph_ids.append(nb.get("id"))
    elif name in ("graph.neighbors", "graph.path"):
        for n in result.get("nodes", []):
            graph_ids.append(n.get("id"))


def _trim_for_model(name: str, result: dict) -> dict:
    if not isinstance(result, dict):
        return {"result": result}
    if name == "data.query_indicators" and "rows" in result:
        rows = result["rows"][:MAX_ROWS_TO_MODEL]
        return {"rows": rows, "row_count": result.get("row_count"), "truncated": len(result["rows"]) > len(rows)}
    if name == "papers.search":
        return {
            "passages": [
                {"citation": p["citation"], "section": p["section"], "text": p["text"], "doc_id": p["doc_id"]}
                for p in result.get("passages", [])
            ]
        }
    return result


def _graph_context(node_ids: list[str]) -> dict:
    ids = _dedupe([n for n in node_ids if n])
    if not ids:
        return {"nodes": [], "edges": []}
    try:
        sub = graph_store.subgraph(ids)
    except FileNotFoundError:
        return {"nodes": [], "edges": []}
    # keep the payload light for the UI
    for n in sub.get("nodes", []):
        n.pop("evidence", None)
    return sub
