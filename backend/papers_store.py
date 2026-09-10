"""
Retrieval over the source-paper corpus (data/papers/corpus.jsonl).

Two backends, same result shape:

  tfidf       (default, offline) — a scikit-learn TF-IDF vector space with a
              light domain-synonym query expansion. Zero API keys.
  embeddings  (opt-in) — cosine search over data/papers/embeddings.npz
              (built by `python etl/embed_papers.py`). Better recall on
              paraphrased policy questions; embeds the query via OpenAI at
              search time, so it needs OPENAI_API_KEY.

Select with ARM_RETRIEVER = tfidf | embeddings | auto (default auto:
embeddings when the .npz and a key are both present, otherwise tfidf). Any
embedding error at query time falls back to tfidf for that query.

Every result is a passage plus a full citation (doc, page, section, URL) so
the policy advisor can ground each recommendation in a specific page of
"Pathways for Peace" (or one of the ESCWA framework papers).
"""

from __future__ import annotations

import json
import os
import re
import sys
from functools import lru_cache
from pathlib import Path

import numpy as np
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel

ROOT = Path(__file__).resolve().parent.parent
CORPUS_PATH = ROOT / "data" / "papers" / "corpus.jsonl"
MANIFEST_PATH = ROOT / "data" / "papers" / "manifest.json"
EMBEDDINGS_PATH = ROOT / "data" / "papers" / "embeddings.npz"

# Small, hand-curated synonym expansion so lay phrasing hits the report's
# vocabulary (e.g. a user asking about "jobs for young people" should reach
# passages on "youth exclusion" and "horizontal inequality").
_EXPANSIONS = {
    "jobs": "employment unemployment livelihoods",
    "youth": "young people youth exclusion aspirations",
    "women": "gender women's participation inclusion",
    "corruption": "corruption accountability rule of law state legitimacy",
    "water": "water resources riparian transboundary scarcity",
    "climate": "climate change environmental shocks drought resilience",
    "election": "elections electoral authorities power sharing political",
    "police": "security sector justice policing security and justice",
    "inequality": "horizontal inequality exclusion grievances redistribution",
    "refugees": "forced displacement refugees IDPs displacement",
    "early warning": "early warning systems risk monitoring prevention",
}


def _hit(rec: dict, score: float) -> dict:
    return {
        "chunk_id": rec["chunk_id"],
        "doc_id": rec["doc_id"],
        "doc_title": rec["doc_title"],
        "doc_short_title": rec["doc_short_title"],
        "doc_year": rec["doc_year"],
        "doc_url": rec["doc_url"],
        "section": rec["section"],
        "page": rec["page"],
        "text": rec["text"],
        "score": round(float(score), 4),
        "citation": f"{rec['doc_short_title']} ({rec['doc_year']}), p. {rec['page']}",
    }


class _Store:
    def __init__(self) -> None:
        if not CORPUS_PATH.exists():
            raise FileNotFoundError(
                f"{CORPUS_PATH} not found. Run `python etl/extract_papers.py` first."
            )
        self.records: list[dict] = [
            json.loads(line) for line in CORPUS_PATH.read_text().splitlines() if line.strip()
        ]
        self.by_id = {r["chunk_id"]: r for r in self.records}
        self.vectorizer = TfidfVectorizer(
            stop_words="english", ngram_range=(1, 2), sublinear_tf=True, min_df=2, max_df=0.6
        )
        self.matrix = self.vectorizer.fit_transform(r["text"] for r in self.records)
        self.manifest = (
            json.loads(MANIFEST_PATH.read_text()) if MANIFEST_PATH.exists() else {"documents": []}
        )

        # optional embeddings backend
        self.emb_ids: np.ndarray | None = None
        self.emb_matrix: np.ndarray | None = None
        self.emb_model: str | None = None
        if EMBEDDINGS_PATH.exists():
            npz = np.load(EMBEDDINGS_PATH, allow_pickle=True)
            self.emb_ids = npz["ids"]
            self.emb_matrix = npz["vectors"].astype(np.float32)
            self.emb_model = str(npz["model"]) if "model" in npz else "text-embedding-3-small"
        self._embed_broken = False

    # ---------------------------------------------------------------- picking
    def active_retriever(self) -> str:
        pref = os.environ.get("ARM_RETRIEVER", "auto").strip().lower()
        has_emb = self.emb_matrix is not None and bool(os.environ.get("OPENAI_API_KEY"))
        if pref == "embeddings":
            return "embeddings" if (self.emb_matrix is not None and not self._embed_broken) else "tfidf"
        if pref == "tfidf":
            return "tfidf"
        return "embeddings" if (has_emb and not self._embed_broken) else "tfidf"

    def retriever_label(self) -> str:
        return f"embeddings ({self.emb_model})" if self.active_retriever() == "embeddings" else "tfidf"

    # ---------------------------------------------------------------- search
    def search(self, query: str, k: int = 5, doc_id: str | None = None) -> list[dict]:
        if self.active_retriever() == "embeddings":
            try:
                return self._embed_search(query, k, doc_id)
            except Exception as exc:  # noqa: BLE001
                self._embed_broken = True
                sys.stderr.write(f"[papers] embedding search failed ({exc}); falling back to TF-IDF\n")
        return self._tfidf_search(query, k, doc_id)

    def _tfidf_search(self, query: str, k: int, doc_id: str | None) -> list[dict]:
        expanded = query
        low = query.lower()
        for trigger, extra in _EXPANSIONS.items():
            if trigger in low:
                expanded += " " + extra
        scores = linear_kernel(self.vectorizer.transform([expanded]), self.matrix).ravel()
        hits: list[dict] = []
        for idx in scores.argsort()[::-1]:
            if scores[idx] <= 0.0:
                break
            rec = self.records[idx]
            if doc_id and rec["doc_id"] != doc_id:
                continue
            hits.append(_hit(rec, scores[idx]))
            if len(hits) >= k:
                break
        return hits

    def _embed_search(self, query: str, k: int, doc_id: str | None) -> list[dict]:
        qv = _embed_query(query, self.emb_model)
        sims = self.emb_matrix @ qv  # both L2-normalized -> cosine
        hits: list[dict] = []
        for idx in np.argsort(sims)[::-1]:
            rec = self.by_id.get(str(self.emb_ids[idx]))
            if rec is None:
                continue
            if doc_id and rec["doc_id"] != doc_id:
                continue
            hits.append(_hit(rec, sims[idx]))
            if len(hits) >= k:
                break
        return hits

    def get_section(self, doc_id: str, page: int, radius: int = 1) -> list[dict]:
        return [
            r
            for r in self.records
            if r["doc_id"] == doc_id and abs(r["page"] - page) <= radius
        ]


@lru_cache(maxsize=256)
def _embed_query(query: str, model: str | None) -> np.ndarray:
    from openai import OpenAI

    vec = OpenAI().embeddings.create(model=model or "text-embedding-3-small", input=query).data[0].embedding
    arr = np.asarray(vec, dtype=np.float32)
    return arr / (np.linalg.norm(arr) + 1e-9)


@lru_cache(maxsize=1)
def _store() -> _Store:
    return _Store()


def search(query: str, k: int = 5, doc_id: str | None = None) -> list[dict]:
    return _store().search(query, k=k, doc_id=doc_id)


def get_section(doc_id: str, page: int, radius: int = 1) -> list[dict]:
    return _store().get_section(doc_id, page, radius=radius)


def list_documents() -> list[dict]:
    return _store().manifest.get("documents", [])


def loaded() -> bool:
    try:
        _store()
        return True
    except FileNotFoundError:
        return False


def retriever_name() -> str:
    try:
        return _store().retriever_label()
    except FileNotFoundError:
        return "unavailable"


if __name__ == "__main__":  # quick manual check
    import sys

    q = " ".join(sys.argv[1:]) or "How can power-sharing reduce the risk of civil war?"
    for h in search(q, k=4):
        print(f"[{h['score']}] {h['citation']} — {h['section']}")
        print("   " + re.sub(r"\s+", " ", h["text"])[:240] + "…\n")
