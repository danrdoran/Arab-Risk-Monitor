from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from fastapi import FastAPI, HTTPException, Query, Request, Response  # noqa: E402
from fastapi.staticfiles import StaticFiles  # noqa: E402
from fastapi.responses import FileResponse  # noqa: E402
from openai import OpenAIError  # noqa: E402
from pydantic import BaseModel, ConfigDict, Field, model_validator  # noqa: E402

from backend import data_store, graph_store, orchestrator, papers_store, scores_store  # noqa: E402
from backend.chat_limits import (  # noqa: E402
    ChatAdmission, ChatBodyLimit, ChatSettings, client_key,
    MAX_HISTORY_CHARS, MAX_HISTORY_MESSAGES, MAX_MESSAGE_CHARS, MAX_QUESTION_CHARS,
)
from backend.i18n import SUPPORTED, normalize  # noqa: E402
from backend.mcp_client import build_pool  # noqa: E402


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.chat_settings = ChatSettings.from_env()
    app.state.chat_admission = ChatAdmission(app.state.chat_settings)
    pool = await build_pool()
    orchestrator.set_pool(pool)
    app.state.pool = pool
    try:
        yield
    finally:
        await pool.stop()


app = FastAPI(title="Arab Risk Monitor — Conflict-Prevention Advisor", lifespan=lifespan)
app.add_middleware(ChatBodyLimit)
logger = logging.getLogger(__name__)


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=MAX_MESSAGE_CHARS)


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    messages: list[ChatMessage] = Field(min_length=1, max_length=MAX_HISTORY_MESSAGES)
    lang: str = "en"

    @model_validator(mode="after")
    def check_context(self):
        if self.messages[-1].role != "user":
            raise ValueError("The last message must be a question from the user.")
        if any(not m.content.strip() for m in self.messages):
            raise ValueError("Messages cannot be blank.")
        if any(len(m.content) > MAX_QUESTION_CHARS for m in self.messages if m.role == "user"):
            raise ValueError(f"Questions must be at most {MAX_QUESTION_CHARS} characters.")
        if sum(len(m.content) for m in self.messages) > MAX_HISTORY_CHARS:
            raise ValueError(f"Conversation context must be at most {MAX_HISTORY_CHARS} characters.")
        return self


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
def papers_search(q: str = Query(..., min_length=2, max_length=500), k: int = Query(6, ge=1, le=20), doc_id: str | None = None):
    try:
        # Public browsing must not provide an unmetered embedding-API route.
        return {"query": q, "passages": papers_store.search_offline(q, k=k, doc_id=doc_id)}
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


# Conversation and brief persistence lives exclusively in the browser.
# Do not expose the legacy SQLite module through anonymous API endpoints.


def _client_key(request: Request) -> str:
    try:
        return client_key(request, on_render=request.app.state.chat_settings.on_render)
    except ValueError:
        logger.warning("Chat client identification is unavailable at the hosting proxy.")
        raise HTTPException(status_code=503, detail="Live chat is temporarily unavailable.") from None


@app.get("/api/chat/usage")
def chat_usage(request: Request, response: Response):
    settings = request.app.state.chat_settings
    usage = request.app.state.chat_admission.usage(_client_key(request))
    response.headers.update(usage.headers)
    return {
        "limit": usage.limit,
        "remaining": usage.remaining,
        "reset_after": usage.reset_after,
        "window_seconds": settings.window_seconds,
        "max_question_chars": MAX_QUESTION_CHARS,
        "max_history_messages": MAX_HISTORY_MESSAGES,
        "max_history_chars": MAX_HISTORY_CHARS,
    }


# ----------------------------------------------------------------------- chat
@app.post("/api/chat")
async def chat_endpoint(req: ChatRequest, request: Request, response: Response):
    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="Live chat is not enabled. You can still explore the data, scores and graph.")
    settings = request.app.state.chat_settings
    controller = request.app.state.chat_admission
    key = _client_key(request)
    admission = controller.admit(key)
    headers = admission.headers
    if admission.reason:
        is_rate = admission.reason == "rate"
        headers["Retry-After"] = str(max(1, admission.reset_after) if is_rate else 5)
        raise HTTPException(
            status_code=429 if is_rate else 503,
            detail="This network has reached its hourly chat allowance." if is_rate else "The advisor is busy. Please try again shortly.",
            headers=headers,
        )
    try:
        result = await asyncio.wait_for(
            orchestrator.run(
                [m.model_dump() for m in req.messages], lang=normalize(req.lang),
                max_output_tokens=settings.max_output_tokens,
                max_model_calls=settings.max_model_calls,
                max_tool_calls=settings.max_tool_calls,
            ),
            timeout=settings.timeout_seconds,
        )
    except TimeoutError:
        raise HTTPException(status_code=504, detail="The advisor took too long. Please try a narrower question.", headers=headers) from None
    except orchestrator.ChatBudgetExceeded:
        raise HTTPException(status_code=503, detail="This question required too many steps. Please try a narrower question.", headers=headers) from None
    except (RuntimeError, FileNotFoundError):
        raise HTTPException(status_code=503, detail="The advisor's data or configuration is unavailable.", headers=headers) from None
    except OpenAIError:
        raise HTTPException(status_code=502, detail="The AI service is temporarily unavailable. Please try again later.", headers=headers) from None
    finally:
        controller.release()
        # Model work may take time; report the remaining window at response time.
        headers.update(controller.usage(key).headers)
    response.headers.update(headers)
    return result


# --------------------------------------------- serve the SPA (no build step)
FRONTEND_DIR = ROOT / "frontend"
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/")
def index():
    return FileResponse(FRONTEND_DIR / "index.html")
