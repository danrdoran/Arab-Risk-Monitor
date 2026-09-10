"""
Lightweight persistence for advisor conversations and the "brief" — the set
of passages, data points and graph nodes a user has pinned while working a
question.

SQLite (stdlib), one file at data/app.db (gitignored). Connections are opened
per call; at this scale that is simpler and safe. Nothing here talks to the
network or an LLM.

Tables
  conversations(id, created_at, updated_at, title, lang)
  messages(id, conversation_id, role, content, payload_json, created_at)
  brief_items(id, conversation_id, kind, ref_json, note, created_at)
      kind: 'passage' | 'data' | 'score' | 'graph_node' | 'note'
"""

from __future__ import annotations

import json
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "app.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS conversations (
    id TEXT PRIMARY KEY,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    title TEXT NOT NULL,
    lang TEXT NOT NULL DEFAULT 'en'
);
CREATE TABLE IF NOT EXISTS messages (
    id TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
    role TEXT NOT NULL,
    content TEXT NOT NULL,
    payload_json TEXT,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS brief_items (
    id TEXT PRIMARY KEY,
    conversation_id TEXT REFERENCES conversations(id) ON DELETE SET NULL,
    kind TEXT NOT NULL,
    ref_json TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_messages_conv ON messages(conversation_id, created_at);
CREATE INDEX IF NOT EXISTS ix_brief_conv ON brief_items(conversation_id, created_at);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _uid() -> str:
    return uuid.uuid4().hex[:16]


@contextmanager
def _conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    try:
        yield con
        con.commit()
    finally:
        con.close()


def init_db() -> None:
    with _conn() as con:
        con.executescript(_SCHEMA)


# ------------------------------------------------------------- conversations
def create_conversation(title: str = "New conversation", lang: str = "en") -> dict:
    cid, ts = _uid(), _now()
    with _conn() as con:
        con.execute(
            "INSERT INTO conversations (id, created_at, updated_at, title, lang) VALUES (?,?,?,?,?)",
            (cid, ts, ts, title.strip()[:120] or "New conversation", lang),
        )
    return {"id": cid, "created_at": ts, "updated_at": ts, "title": title, "lang": lang, "messages": []}


def list_conversations(limit: int = 50) -> list[dict]:
    with _conn() as con:
        rows = con.execute(
            """SELECT c.*, (SELECT COUNT(*) FROM messages m WHERE m.conversation_id = c.id) AS message_count
               FROM conversations c ORDER BY c.updated_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_conversation(cid: str) -> dict | None:
    with _conn() as con:
        conv = con.execute("SELECT * FROM conversations WHERE id = ?", (cid,)).fetchone()
        if not conv:
            return None
        msgs = con.execute(
            "SELECT id, role, content, payload_json, created_at FROM messages WHERE conversation_id = ? ORDER BY created_at",
            (cid,),
        ).fetchall()
    out = dict(conv)
    out["messages"] = [
        {**dict(m), "payload": json.loads(m["payload_json"]) if m["payload_json"] else None}
        for m in msgs
    ]
    for m in out["messages"]:
        m.pop("payload_json", None)
    return out


def rename_conversation(cid: str, title: str) -> bool:
    with _conn() as con:
        cur = con.execute(
            "UPDATE conversations SET title = ?, updated_at = ? WHERE id = ?",
            (title.strip()[:120] or "Untitled", _now(), cid),
        )
    return cur.rowcount > 0


def delete_conversation(cid: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM conversations WHERE id = ?", (cid,))
    return cur.rowcount > 0


def add_message(cid: str, role: str, content: str, payload: dict | None = None) -> dict:
    mid, ts = _uid(), _now()
    with _conn() as con:
        con.execute(
            "INSERT INTO messages (id, conversation_id, role, content, payload_json, created_at) VALUES (?,?,?,?,?,?)",
            (mid, cid, role, content, json.dumps(payload) if payload else None, ts),
        )
        con.execute("UPDATE conversations SET updated_at = ? WHERE id = ?", (ts, cid))
        # give a fresh conversation a title from its first user message
        if role == "user":
            row = con.execute("SELECT title FROM conversations WHERE id = ?", (cid,)).fetchone()
            if row and row["title"] in ("New conversation", "", None):
                con.execute(
                    "UPDATE conversations SET title = ? WHERE id = ?",
                    (content.strip().split("\n")[0][:80], cid),
                )
    return {"id": mid, "created_at": ts}


# -------------------------------------------------------------------- brief
def add_brief_item(kind: str, ref: dict, note: str = "", conversation_id: str | None = None) -> dict:
    bid, ts = _uid(), _now()
    with _conn() as con:
        con.execute(
            "INSERT INTO brief_items (id, conversation_id, kind, ref_json, note, created_at) VALUES (?,?,?,?,?,?)",
            (bid, conversation_id, kind, json.dumps(ref), note, ts),
        )
    return {"id": bid, "kind": kind, "ref": ref, "note": note, "created_at": ts, "conversation_id": conversation_id}


def list_brief_items(conversation_id: str | None = None) -> list[dict]:
    with _conn() as con:
        if conversation_id:
            rows = con.execute(
                "SELECT * FROM brief_items WHERE conversation_id = ? ORDER BY created_at", (conversation_id,)
            ).fetchall()
        else:
            rows = con.execute("SELECT * FROM brief_items ORDER BY created_at").fetchall()
    return [
        {
            "id": r["id"],
            "conversation_id": r["conversation_id"],
            "kind": r["kind"],
            "ref": json.loads(r["ref_json"]),
            "note": r["note"],
            "created_at": r["created_at"],
        }
        for r in rows
    ]


def update_brief_item(bid: str, note: str) -> bool:
    with _conn() as con:
        cur = con.execute("UPDATE brief_items SET note = ? WHERE id = ?", (note, bid))
    return cur.rowcount > 0


def delete_brief_item(bid: str) -> bool:
    with _conn() as con:
        cur = con.execute("DELETE FROM brief_items WHERE id = ?", (bid,))
    return cur.rowcount > 0


def export_brief_markdown(conversation_id: str | None = None) -> str:
    items = list_brief_items(conversation_id)
    title = "Conflict-prevention brief"
    if conversation_id:
        conv = get_conversation(conversation_id)
        if conv:
            title = f"Brief — {conv['title']}"
    lines = [f"# {title}", "", f"_Compiled {(_now())[:10]} · Arab Risk Monitor Conflict-Prevention Advisor_", ""]

    groups = {"passage": "## Policy evidence", "data": "## Data points", "score": "## Composite scores", "graph_node": "## Knowledge-graph context", "note": "## Notes"}
    for kind, heading in groups.items():
        chunk = [it for it in items if it["kind"] == kind]
        if not chunk:
            continue
        lines.append(heading)
        lines.append("")
        for it in chunk:
            ref = it["ref"]
            if kind == "passage":
                lines.append(f"- **{ref.get('citation', '')}** — {ref.get('section', '')}")
                if ref.get("snippet"):
                    lines.append(f"  > {ref['snippet'].strip()}")
                if ref.get("url"):
                    lines.append(f"  <{ref['url']}>")
            elif kind == "data":
                lines.append(
                    f"- **{ref.get('indicator_label', '')}** — {ref.get('country_name', '')} {ref.get('year', '')}: "
                    f"{ref.get('value', '')} {ref.get('unit', '')} "
                    f"({ref.get('source_name', '')}, retrieved {str(ref.get('retrieved_at', ''))[:10]})"
                )
            elif kind == "score":
                lines.append(
                    f"- **{ref.get('country_name', '')} — {ref.get('pathway', '')}** ({ref.get('year', '')}): "
                    f"risk {ref.get('risk', '')}, vulnerability {ref.get('vulnerability', '')}, resilience {ref.get('resilience', '')}"
                )
            elif kind == "graph_node":
                lines.append(f"- **{ref.get('label', '')}** ({ref.get('type', '')}) — {ref.get('summary', '')}")
            else:
                lines.append(f"- {ref.get('text', '')}")
            if it["note"]:
                lines.append(f"  — _{it['note'].strip()}_")
        lines.append("")
    return "\n".join(lines)
