# Arab Risk Monitor — Conflict Prevention Advisor

Ask, in plain English, French or Arabic, how to reduce the risk of violent
conflict in any of the 22 League of Arab States countries — and get back
**cited, evidence-based policy guidance**.

The advisor is grounded in two bodies of work:

- **[Pathways for Peace: Inclusive Approaches to Preventing Violent Conflict](https://openknowledge.worldbank.org/handle/10986/28337)**
  (World Bank / United Nations, 2018) — the framework and evidence base for
  *preventing* violent conflict: actors, institutions and structural factors;
  the four arenas of contestation; sustained, inclusive and targeted
  prevention.
- **ESCWA's [Arab Risk Monitor](https://www.unescwa.org/)** three-paper series
  — the regional risk taxonomy (vulnerability vs. resilience across the
  Conflict, Climate and Development pathways), the indicator dataset, and the
  Annex 1 scoring methodology.

Every number and every recommendation the advisor gives is traceable: data
points carry their source and retrieval date, policy claims carry a page
citation in the source papers.

## What's in the app

| Tab | What it does |
|---|---|
| **Advisor** | Natural-language chat. A lead agent delegates to two specialist subagents (over MCP) and synthesises a single cited answer in your language. Conversations are saved; pin any passage, data point or graph node to a **Brief** and export it as Markdown. |
| **Risk profile** | Composite vulnerability / resilience / risk scores per country and pathway (ESCWA Annex 1 method), with regional ranking, a vulnerability×resilience scatter, and score trends. |
| **Explore data** | Direct browse of the 20 live indicators × 22 countries, with a provenance panel. |
| **Knowledge graph** | An interactive graph linking risk factors → policy levers → indicators → the pages of the papers that support each link. |
| **Methodology** | How it's built and the source documents. |

## Architecture

```
                        ┌───────────────────────────────┐
   your question  ───▶  │  LEAD AGENT   (gpt-4o)         │
   (EN / FR / AR)       │  plans · delegates · writes    │
                        └───┬───────────────────┬────────┘
              consult_policy_advisor    consult_data_analyst
                        │                       │
              ┌─────────▼─────────┐   ┌──────────▼─────────┐
              │ POLICY ADVISOR    │   │ DATA ANALYST       │   (gpt-4o-mini)
              │ papers.* + graph.*│   │ data.*  (+ scores) │
              └───────┬───────────┘   └──────────┬─────────┘
                      │      Model Context Protocol (stdio)
        ┌─────────────▼──────┐ ┌──────────────┐ ┌▼───────────────┐
        │ arm_papers_server  │ │ arm_graph_.. │ │ arm_data_server│
        │ TF-IDF / embeddings│ │ knowledge    │ │ indicators +   │
        │ over the 4 papers  │ │ graph        │ │ composite scores│
        └────────────────────┘ └──────────────┘ └────────────────┘
```

The three **MCP servers** in [`mcp_servers/`](mcp_servers/) are standalone —
run any of them with `python -m mcp_servers.arm_data_server` and point the MCP Inspector at it. The FastAPI app launches all three at
startup and routes subagent tool calls through them. Set `ARM_MCP=0` to run
the identical tools in-process instead.

## Quick start

Requires Python 3.10+.

```bash
git clone --branch main https://github.com/danrdoran/Arab-Risk-Monitor.git
cd Arab-Risk-Monitor

# Create and activate virtual environment
uv venv --python 3.12
source .venv/bin/activate

# Install dependencies
uv pip install --python .venv/bin/python -r requirements.txt

cp .env.example .env          # add OPENAI_API_KEY (only needed for the Advisor tab)

# Build the data artifacts (safe to re-run; no API key needed):
python etl/build_dataset.py --refresh   # fetch every source + merge -> data/processed/indicators.csv
python etl/build_scores.py              # composite scores           -> data/processed/scores.csv
python etl/extract_papers.py            # paper corpus               -> data/papers/
python etl/build_graph.py               # knowledge graph            -> data/graph/

# Optional (needs OPENAI_API_KEY): semantic paper retrieval
python etl/embed_papers.py              # -> data/papers/embeddings.npz  (then ARM_RETRIEVER=embeddings)

uvicorn backend.app:app --reload --port 8420
```

Open **http://localhost:8420**.

- **Risk profile**, **Explore data** and **Knowledge graph** work immediately,
  no OpenAI key.
- **Advisor** needs `OPENAI_API_KEY` in `.env`. Models and the retriever are
  configurable (`ARM_LEAD_MODEL`, `ARM_SUBAGENT_MODEL`, `ARM_RETRIEVER`).

## Data pipeline

Each fetcher writes a `data/processed/parts/<source>.csv`; `build_dataset.py`
merges the parts and computes the derived indicators.

```
etl/
  indicators.py         Indicator registry (Annex 4) + a border-adjacency map
                        and Gleditsch-Ward country codes.
  fetch_worldbank.py    World Bank WDI/WGI + SIPRI military expenditure (no key)
  fetch_ucdp.py         UCDP Battle-Related Deaths v24.1 (static download, no key)
  fetch_unhcr.py        UNHCR refugees (origin + hosted) and IDPs (API, no key)
  fetch_emdat.py        EM-DAT disaster impact          (needs EMDAT_API_TOKEN)
  fetch_oecd_climate.py OECD climate adaptation finance (needs a pinned dataflow)
  build_dataset.py      merge parts + derive conflict intensity (per 100k),
                        neighbouring conflict, forced displacement (% pop)
  build_scores.py       ESCWA Annex 1: min-max normalization (with literature
                        threshold overrides), equal weights, indicator->theme->
                        pathway aggregation, the 0.2/0.4/0.6/0.8 risk bands
  extract_papers.py     PyMuPDF -> section-aware, page-cited corpus.jsonl
  embed_papers.py       OpenAI embeddings -> embeddings.npz (optional)
  graph_seed.py         Curated knowledge-graph nodes + edges + indicator links
  build_graph.py        Assemble knowledge_graph.json, attaching the supporting
                        paper passages to every concept

backend/
  data_store.py    scores_store.py   graph_store.py   papers_store.py
  tools.py         shared tool surface (data.* / papers.* / graph.*)
  mcp_client.py    task-per-server stdio session pool
  orchestrator.py  lead agent + policy-advisor / data-analyst subagents
  store_db.py      SQLite: conversations, messages, brief items
  i18n.py          per-language answer directive (EN / FR / AR)
  app.py           FastAPI: REST endpoints + serves the SPA

mcp_servers/       three standalone stdio MCP servers
frontend/          single-page app, no build step; custom RTL-aware CSS,
                   d3-force graph, Chart.js, trilingual UI (static/i18n.js)
```

## Composite scores

`data/processed/scores.csv` follows the ESCWA Arab Risk Monitor methodology
(Annex 1 of *Quantifying the drivers of risk of conflict*): every scoring
indicator is min-max normalized to `[0, 1]` (using a literature threshold
where the registry sets one), turned into a `0 = best, 1 = worst` value by its
direction, then averaged with **equal weights** in two steps —
indicator → theme → pathway — for the vulnerability and resilience dimensions
separately. Levels use the paper's bands (0.2 / 0.4 / 0.6 / 0.8). The single
`risk` score (mean of vulnerability and `1 − resilience`) is this project's
synthesis of the paper's two-dimensional representation, not from ESCWA.
`data/processed/scores_meta.json` records the exact bounds used per indicator.

## Data provenance

Every observation in `data/processed/indicators.csv` carries its source name
and dataset, a deep link, and a retrieval timestamp; the raw API responses are
saved byte-for-byte under `data/raw/`. Indicators still awaiting a wired-up
source (EM-DAT without a token, OECD adaptation finance, V-DEM, Small Arms
Survey) keep `status="planned"` — the advisor says so plainly rather than
guessing a number. Nothing under `data/processed/`, `data/papers/` or
`data/graph/` is hand-edited.

Known limitation: `forced_displacement` uses UNHCR-mandate figures, so it
undercounts UNRWA-registered Palestinians in Jordan and Lebanon.
