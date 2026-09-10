from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, HTTPException, Query  # noqa: E402
from fastapi.middleware.cors import CORSMiddleware  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import FileResponse, PlainTextResponse  # noqa: E402
from openai import OpenAIError  # noqa: E402
from pydantic import BaseModel  # noqa: E402

from backend import data_store, graph_store, orchestrator, papers_store, scores_store, store_db  # noqa: E402
from backend.i18n import SUPPORTED, normalize  # noqa: E402
from backend.mcp_client import build_pool  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    store_db.init_db()
    pool = await build_pool()
    orchestrator.set_pool(pool)
    app.state.pool = pool
    try:
        yield
    finally:
        await pool.stop()


app = FastAPI(title="Arab Risk Monitor — Conflict-Prevention Advisor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: list[ChatMessage]
    lang: str = "en"
    conversation_id: str | None = None
    persist: bool = False


class ConversationCreate(BaseModel):
    title: str = "New conversation"
    lang: str = "en"


class RenameRequest(BaseModel):
    title: str


class BriefItemCreate(BaseModel):
    kind: str
    ref: dict
    note: str = ""
    conversation_id: str | None = None


class BriefNoteUpdate(BaseModel):
    note: str


# --------------------------------------------------------------------- health
@app.get("/api/health")
def health():
    try:
        data_store.load_data()
        data_ok = True
    except FileNotFoundError:
        data_ok = False
    pool = getattr(app.state, "pool", None)
    return {
        "status": "ok",
        "data_loaded": data_ok,
        "papers_loaded": papers_store.loaded(),
        "graph_loaded": graph_store.loaded(),
        "scores_loaded": scores_store.loaded(),
        "retriever": papers_store.retriever_name(),
        "chat_configured": bool(os.environ.get("OPENAI_API_KEY")),
        "mcp_transport": getattr(pool, "transport", "unknown"),
        "models": {
            "lead": os.environ.get("ARM_LEAD_MODEL", "gpt-4o"),
            "subagent": os.environ.get("ARM_SUBAGENT_MODEL", "gpt-4o-mini"),
        },
        "languages": list(SUPPORTED),
    }


# ----------------------------------------------------------------------- data
@app.get("/api/countries")
def countries():
    return data_store.list_countries()


@app.get("/api/indicators")
def indicators():
    return data_store.list_indicators()


@app.get("/api/data")
def data(
    countries: str | None = None,
    indicator_ids: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    latest_only: bool = False,
):
    df = data_store.query(
        countries=countries.split(",") if countries else None,
        indicator_ids=indicator_ids.split(",") if indicator_ids else None,
        year_min=year_min,
        year_max=year_max,
        latest_only=latest_only,
    )
    return df.to_dict(orient="records")


# --------------------------------------------------------------------- papers
@app.get("/api/papers")
def papers():
    return papers_store.list_documents()


@app.get("/api/papers/search")
def papers_search(q: str = Query(..., min_length=2), k: int = 6, doc_id: str | None = None):
    try:
        return {"query": q, "passages": papers_store.search(q, k=k, doc_id=doc_id)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


# --------------------------------------------------------------------- scores
@app.get("/api/scores")
def scores(
    countries: str | None = None,
    pathways: str | None = None,
    year_min: int | None = None,
    year_max: int | None = None,
    latest_only: bool = False,
):
    try:
        return scores_store.query(
            countries=countries.split(",") if countries else None,
            pathways=pathways.split(",") if pathways else None,
            year_min=year_min,
            year_max=year_max,
            latest_only=latest_only,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/scores/meta")
def scores_meta():
    return {"meta": scores_store.meta(), "latest_year": scores_store.latest_year() if scores_store.loaded() else None}


@app.get("/api/scores/ranking")
def scores_ranking(pathway: str = "Overall", dimension: str = "risk", year: int | None = None):
    try:
        return {"pathway": pathway, "dimension": dimension, "ranking": scores_store.ranking(pathway, dimension, year)}
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/scores/country/{iso3}")
def scores_country(iso3: str):
    prof = scores_store.country_profile(iso3)
    if not prof:
        raise HTTPException(status_code=404, detail=f"no scores for '{iso3}'")
    return prof


# ---------------------------------------------------------------------- graph
@app.get("/api/graph")
def graph():
    try:
        return graph_store.full()
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.get("/api/graph/search")
def graph_search(q: str = Query(..., min_length=2)):
    return {"query": q, "nodes": graph_store.search(q)}


@app.get("/api/graph/node/{node_id:path}")
def graph_node(node_id: str):
    node = graph_store.node(node_id)
    if not node:
        raise HTTPException(status_code=404, detail=f"no node '{node_id}'")
    return node


# --------------------------------------------------------- conversations / brief
@app.get("/api/conversations")
def conversations_list():
    return store_db.list_conversations()


@app.post("/api/conversations")
def conversations_create(req: ConversationCreate):
    return store_db.create_conversation(req.title, normalize(req.lang))


@app.get("/api/conversations/{cid}")
def conversations_get(cid: str):
    conv = store_db.get_conversation(cid)
    if not conv:
        raise HTTPException(status_code=404, detail="no such conversation")
    return conv


@app.patch("/api/conversations/{cid}")
def conversations_rename(cid: str, req: RenameRequest):
    if not store_db.rename_conversation(cid, req.title):
        raise HTTPException(status_code=404, detail="no such conversation")
    return {"ok": True}


@app.delete("/api/conversations/{cid}")
def conversations_delete(cid: str):
    store_db.delete_conversation(cid)
    return {"ok": True}


@app.get("/api/brief")
def brief_list(conversation_id: str | None = None):
    return store_db.list_brief_items(conversation_id)


@app.post("/api/brief")
def brief_add(req: BriefItemCreate):
    return store_db.add_brief_item(req.kind, req.ref, req.note, req.conversation_id)


@app.patch("/api/brief/{bid}")
def brief_update(bid: str, req: BriefNoteUpdate):
    if not store_db.update_brief_item(bid, req.note):
        raise HTTPException(status_code=404, detail="no such item")
    return {"ok": True}


@app.delete("/api/brief/{bid}")
def brief_delete(bid: str):
    store_db.delete_brief_item(bid)
    return {"ok": True}


@app.get("/api/brief/export")
def brief_export(conversation_id: str | None = None):
    md = store_db.export_brief_markdown(conversation_id)
    return PlainTextResponse(md, media_type="text/markdown")


# ----------------------------------------------------------------------- chat
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest):
    try:
        result = await orchestrator.run(
            [m.model_dump() for m in req.messages], lang=normalize(req.lang)
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except OpenAIError as exc:
        raise HTTPException(status_code=502, detail=f"OpenAI API error: {exc}") from exc

    cid = req.conversation_id
    if cid or req.persist:
        if not cid:
            cid = store_db.create_conversation(lang=normalize(req.lang))["id"]
        last_user = next((m.content for m in reversed(req.messages) if m.role == "user"), "")
        if last_user:
            store_db.add_message(cid, "user", last_user)
        store_db.add_message(cid, "assistant", result.get("reply", ""), payload=_light_payload(result))
    result["conversation_id"] = cid
    return result


def _light_payload(result: dict) -> dict:
    """Trim the chat result to what the rail needs to re-render, for storage."""
    return {
        "citations": result.get("citations", [])[:60],
        "paper_citations": result.get("paper_citations", [])[:20],
        "score_rows": result.get("score_rows", [])[:40],
        "chart_rows": result.get("chart_rows", [])[:400],
        "graph_context": result.get("graph_context", {"nodes": [], "edges": []}),
        "trace": result.get("trace", []),
        "models": result.get("models", {}),
    }


# --------------------------------------------- serve the SPA (no build step)
FRONTEND_DIR = ROOT / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
