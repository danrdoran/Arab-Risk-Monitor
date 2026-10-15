# Arab Risk Monitor — Conflict Prevention Advisor

Ask, in plain English, French or Arabic, how to reduce the risk of violent
conflict in any of the 22 League of Arab States countries — and get back
**cited, evidence-based policy guidance**.

## Access the app

**Live demo: not published yet.** This branch includes everything needed to
deploy a public demo; pushing it to GitHub does not start a hosted server.

- **Try it on your computer:** follow [Quick start](#quick-start), then open
  **http://localhost:8420**. This address works only on the computer running
  the server.
- **Publish a demo for visitors:** follow [Deploy on Render](#deploy-on-render).
  Render supplies the public HTTPS address; visitors only need a browser.
  They do not need Python, a GitHub account, or their own API key.

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/danrdoran/Arab-Risk-Monitor/tree/feat/public-demo-browser-history)

The button creates your own Render deployment and requires a Render account.
It is **not** a link to an already-running app. After a successful deployment,
replace the "Live demo: not published yet" notice above with the actual HTTPS
link and add that same link to the repository's **About → Website** field.

The advisor is grounded in two bodies of work:

- **[Pathways for Peace: Inclusive Approaches to Preventing Violent Conflict](https://openknowledge.worldbank.org/handle/10986/28337)**
  (World Bank / United Nations, 2018) — the framework and evidence base for
  *preventing* violent conflict: actors, institutions and structural factors;
  the four arenas of contestation; sustained, inclusive and targeted
  prevention.
- **ESCWA's [Arab Risk Monitor](https://www.unescwa.org/publications/arab-risk-monitor-conceptual-framework)** three-paper series
  — the regional risk taxonomy (vulnerability vs. resilience across the
  Conflict, Climate and Development pathways), the indicator dataset, and the
  Annex 1 scoring methodology.

Every number and every recommendation the advisor gives is traceable: data
points carry their source and retrieval date, policy claims carry a page
citation in the source papers.

## What's in the app

| Tab | What it does |
|---|---|
| **Advisor** | Natural-language chat. A lead agent delegates to two specialists and synthesises a cited answer in your language. Conversations and pinned **Briefs** are saved in your browser; export either as Markdown. Live chat allows 10 submitted questions per network IP per rolling hour by default. |
| **Risk profile** | Composite vulnerability / resilience / risk scores per country and pathway (ESCWA Annex 1 method), with regional ranking, a vulnerability×resilience scatter, and score trends. |
| **Explore data** | Direct browse of 20 indicators × 22 countries, with a provenance panel. |
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

## Quick start

Use **Python 3.12** (also selected by `.python-version`). The repository
already contains prepared data, scores, paper passages and the knowledge
graph; you do not need to rebuild them to try the app.

```bash
git clone --branch feat/public-demo-browser-history https://github.com/danrdoran/Arab-Risk-Monitor.git
cd Arab-Risk-Monitor

# Create and activate virtual environment
python3.12 -m venv .venv
source .venv/bin/activate

# Install dependencies
python -m pip install -r requirements.txt

cp .env.example .env
# Optional: set OPENAI_API_KEY in .env to enable live Advisor answers.

python -m uvicorn backend.app:app --reload --port 8420 --no-proxy-headers
```

On Windows PowerShell, create the environment with
`py -3.12 -m venv .venv`, activate it with
`.\.venv\Scripts\Activate.ps1`, and copy the example environment file with
`Copy-Item .env.example .env`. The installation and launch commands are the same.

Open **http://localhost:8420**.

- **Risk profile**, **Explore data**, **Knowledge graph** and public paper
  search work without an OpenAI key.
- **Advisor** needs a server-side `OPENAI_API_KEY`. Never put it in
  JavaScript, browser storage or a committed file.
- `GET /api/health` reports whether the data and advisor are available.
- For a lighter single-process setup, set `ARM_MCP=0`; the same specialist
  tools run in process instead of spawning three stdio MCP servers.

### Refresh the data (optional)

Run these commands only when you want to rebuild or update the committed
artifacts. The running server does not refresh sources on each visit.

```bash
python etl/build_dataset.py --refresh
python etl/build_scores.py
python etl/extract_papers.py
python etl/build_graph.py

# Optional semantic retrieval; requires an API key and incurs API usage:
python etl/embed_papers.py
# Then set ARM_RETRIEVER=embeddings for the Advisor's internal retrieval.
```

## Deploy on Render

The root [render.yaml](render.yaml) defines a **Free Python Web Service**
using this branch. It serves the frontend and FastAPI API together. No
separate frontend deployment, database or persistent disk is needed.

1. Click **Deploy to Render** above, or connect the repository in Render and
   create a Blueprint from **feat/public-demo-browser-history**.
2. Supply your `OPENAI_API_KEY` in Render's secret environment settings to
   enable live chat. This is your key; visitors do not provide one.
3. Wait for the build and health check to succeed. Open the actual
   `https://…onrender.com` URL displayed on the service page.
4. Check the risk profile, data explorer, knowledge graph and one Advisor
   question. Confirm that `/api/health` reports loaded data.
5. Add the actual demo URL to [Access the app](#access-the-app) and the
   GitHub **About → Website** field. Share that URL with visitors.

To deploy manually without a Blueprint, choose **New → Web Service**, connect
this repository and use:

| Setting | Value |
|---|---|
| Branch | `feat/public-demo-browser-history` |
| Runtime / plan | Python / Free |
| Root directory | Repository root (leave blank) |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn backend.app:app --host 0.0.0.0 --port $PORT --workers 1 --no-proxy-headers` |
| Health check path | `/api/health` |
| Environment | `ARM_MCP=0`, `ARM_RETRIEVER=tfidf`; add `OPENAI_API_KEY` for live chat |

For a **data-only demo**, omit `OPENAI_API_KEY` when setting up the manual
service. Data tabs remain available and the interface explains that live
chat is disabled. Models remain configurable with `ARM_LEAD_MODEL` and
`ARM_SUBAGENT_MODEL`.

The Blueprint disables automatic deployment. Deploy new commits manually
after reviewing them. If this branch is merged or renamed later, update
the Blueprint's branch, the button's branch URL and the clone instructions.

### Hosting cost and availability

- Render supplies a public HTTPS address and managed certificate on its
  free tier, subject to its usage limits. No custom domain purchase is needed.
- Free services sleep after 15 minutes without traffic; the next visitor
  may wait roughly a minute for startup.
- Files created at runtime disappear on a restart/redeploy. Conversation
  history is in each visitor's browser, so it survives server restarts.
- **Live OpenAI usage is billed separately**, including internal specialist
  calls. Ten user questions can produce more than ten model API calls.
  The app's limits reduce usage; they are not a guaranteed dollar budget.

See [Render's free-tier limits](https://render.com/docs/free) and
[FastAPI deployment guide](https://render.com/docs/deploy-fastapi).

## Browser history and chat allowance

Conversations, the last answer's citations/chart context, pinned brief items
and their notes are stored under `arm_history_v1` in this website's
`localStorage`. The UI restores the active conversation after a reload and
offers deletion, **Clear history**, **Export chats**, and brief export/copy.

- History stays in that browser profile for that site; it does not sync
  between devices. A shared browser profile shares the saved history.
- Clearing website data removes history. Private browsing normally removes
  it when the private session ends.
- Storage keeps at most 20 conversations, 100 messages per conversation,
  200 brief items overall and approximately two million JSON characters.
  When storage fills, older content is trimmed before the current chat.
  Export anything you want to keep.
- If browser storage is unavailable, the app works in memory for the
  current page and displays a notice.
- Previous messages are still sent to the backend and AI provider as
  bounded context when you ask a follow-up. Browser storage does not mean
  local AI inference.

There are no public `/api/conversations` or `/api/brief` endpoints on this
branch. Chat no longer accepts `persist` or `conversation_id`; callers
cannot opt back into shared server storage. The legacy local SQLite file
is not imported or served by the new UI.

The backend allows **10 admitted Advisor messages per network IP within the
preceding 60 minutes**. A follow-up counts as another question. An admitted
request still counts if the AI later fails or times out; invalid requests
and requests rejected because the service is busy do not count. Charts,
rankings, the graph and offline paper search do not consume the allowance.

When the allowance is exhausted, `POST /api/chat` returns **429** with
`Retry-After`; the UI shows a countdown. `GET /api/chat/usage` reports the
current network's allowance without consuming it. Quotas are enforced
on the server, so clearing browser history does not reset them.

| Environment setting | Default | Purpose |
|---|---:|---|
| `ARM_CHAT_RATE_LIMIT` | 10 | Admitted questions per IP per window |
| `ARM_CHAT_WINDOW_SECONDS` | 3600 | Exact rolling-window length |
| `ARM_CHAT_MAX_CONCURRENT` | 2 | Maximum active questions across this process |
| `ARM_CHAT_TIMEOUT_SECONDS` | 120 | Overall deadline for an admitted question |
| `ARM_CHAT_MAX_OUTPUT_TOKENS` | 1200 | Output token limit on each model call |
| `ARM_CHAT_MAX_MODEL_CALLS` | 12 | Total lead + specialist model calls per question |
| `ARM_CHAT_MAX_TOOL_CALLS` | 24 | Total tool invocations per question |

Questions are limited to 2,000 characters. Each request may carry at most
21 user/assistant messages and 20,000 characters of context; the frontend
sends only the most recent context that fits. The server rejects oversized
bodies before parsing them and does not accept browser-supplied system prompts.
Public paper search always uses the local TF-IDF index, even if the
Advisor uses optional embeddings.

**Anonymous-demo limitations:** people on the same office/home network may
share an allowance; changing IPs can obtain another allowance. Counts are
held in process memory and reset on restart/sleep/redeploy. Keep **one worker
and one service instance**, as configured in the Blueprint. Strict quotas
across restarts or multiple instances require a persistent shared usage
store; per-account quotas additionally require sign-in.

Render sets `RENDER=true` itself. Only in that environment does the app
trust its edge-owned `True-Client-IP` / `CF-Connecting-IP` headers; missing
or invalid headers disable chat rather than allowing an unidentifiable
request through. Caller-supplied `X-Forwarded-For` is not used. Do not set
`RENDER=true` locally or expose this configuration through a direct socket.
For other hosting providers, configure client-IP trust explicitly before
using this demo's network-based quota.

## Checks

From the repository root:

```bash
python -m pip install -r requirements-dev.txt
ARM_MCP=0 python -m pytest -q
node --test tests/browser_history.test.cjs
```

The tests use simulated model replies and do not spend API credits. They
cover rolling-window boundaries, simultaneous admissions, request limits,
failure/timeout cleanup, removal of shared persistence endpoints, browser
history isolation/restoration, brief export and storage failures.

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
  chat_limits.py   in-memory rolling-window quota + concurrency reservations
  store_db.py      legacy local SQLite helpers (not used or exposed by app.py)
  i18n.py          per-language answer directive (EN / FR / AR)
  app.py           FastAPI: REST endpoints + serves the SPA

mcp_servers/       three standalone stdio MCP servers
frontend/          single-page app, no build step; history.js stores chats/briefs
                   in the browser; custom RTL-aware CSS,
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
