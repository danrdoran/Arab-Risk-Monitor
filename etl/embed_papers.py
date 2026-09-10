"""
Embed the paper corpus for semantic retrieval.

Reads data/papers/corpus.jsonl, embeds every chunk with an OpenAI embedding
model, and writes data/papers/embeddings.npz (chunk ids + a float32 matrix +
the model name).

This is optional. Without it, backend/papers_store.py uses its offline TF-IDF
retriever. With it, set ARM_RETRIEVER=embeddings (or =auto) to use semantic
search — better recall on paraphrased policy questions.

    OPENAI_API_KEY=...  python etl/embed_papers.py
    python etl/embed_papers.py --model text-embedding-3-large

Cost is a fraction of a cent for the ~1,400-chunk corpus with the small model.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

from openai import OpenAI  # noqa: E402

CORPUS = ROOT / "data" / "papers" / "corpus.jsonl"
OUT = ROOT / "data" / "papers" / "embeddings.npz"
BATCH = 128


def main() -> None:
    model = "text-embedding-3-small"
    if "--model" in sys.argv:
        model = sys.argv[sys.argv.index("--model") + 1]

    if not os.environ.get("OPENAI_API_KEY"):
        sys.exit("OPENAI_API_KEY not set — the TF-IDF retriever needs no key; this step is optional.")
    if not CORPUS.exists():
        sys.exit(f"{CORPUS} not found. Run `python etl/extract_papers.py` first.")

    records = [json.loads(line) for line in CORPUS.read_text().splitlines() if line.strip()]
    client = OpenAI()

    ids: list[str] = []
    vectors: list[list[float]] = []
    for start in range(0, len(records), BATCH):
        batch = records[start : start + BATCH]
        resp = client.embeddings.create(model=model, input=[r["text"] for r in batch])
        for rec, item in zip(batch, resp.data):
            ids.append(rec["chunk_id"])
            vectors.append(item.embedding)
        print(f"  embedded {start + len(batch)}/{len(records)}")

    mat = np.asarray(vectors, dtype=np.float32)
    mat /= np.linalg.norm(mat, axis=1, keepdims=True) + 1e-9  # store L2-normalized
    np.savez_compressed(OUT, ids=np.asarray(ids), vectors=mat, model=np.asarray(model))
    print(f"wrote {OUT}  ({mat.shape[0]} vectors, dim {mat.shape[1]}, model {model})")


if __name__ == "__main__":
    main()
