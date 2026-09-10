"""
Turn the source PDFs into a searchable, citation-tagged text corpus.

For every PDF in papers/, this script:
  1. reads the embedded table of contents to know which page belongs to
     which section,
  2. extracts the text of every page with PyMuPDF,
  3. splits each page into overlapping ~1,100-character chunks, each tagged
     with its document, section path, and page,
  4. writes the whole thing to data/papers/corpus.jsonl (one chunk per line)
     plus a small data/papers/manifest.json describing the documents.

The corpus is a build artifact: never hand-edit it, regenerate it with

    python etl/extract_papers.py

Design notes
------------
- Every chunk carries enough provenance (doc id + title + page + section) to
  render a real citation like "Pathways for Peace (2018), p. 277". The papers
  retrieval layer (backend/papers_store.py) never returns a passage without it.
- Text only, no network. Works fully offline once the PDFs are in papers/.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
PAPERS_DIR = ROOT / "papers"
OUT_DIR = ROOT / "data" / "papers"

CHUNK_CHARS = 1_100
CHUNK_OVERLAP = 150


@dataclass(frozen=True)
class PaperMeta:
    doc_id: str
    filename: str
    title: str
    short_title: str
    authors: str
    year: int
    publisher: str
    url: str
    role: str  # "framework" | "prevention-evidence"


# The four documents the assistant is grounded in. The three ESCWA papers
# supply the Arab Risk Monitor taxonomy and the regional data lens; the
# World Bank / UN "Pathways for Peace" supplies the conflict-prevention
# policy evidence base.
PAPERS: list[PaperMeta] = [
    PaperMeta(
        doc_id="pathways-for-peace",
        filename="pathways-for-peace-2018.pdf",
        title="Pathways for Peace: Inclusive Approaches to Preventing Violent Conflict",
        short_title="Pathways for Peace",
        authors="United Nations; World Bank",
        year=2018,
        publisher="World Bank, Washington, DC",
        url="https://openknowledge.worldbank.org/handle/10986/28337",
        role="prevention-evidence",
    ),
    PaperMeta(
        doc_id="arm-conceptual-framework",
        filename="arab-risk-monitor-conceptual-framework-english.pdf",
        title="Arab Risk Monitor: A Conceptual Framework",
        short_title="ARM — Conceptual Framework",
        authors="UN ESCWA",
        year=2023,
        publisher="United Nations, Beirut (E/ESCWA/CL6.GCP/2023/TP.2)",
        url="https://www.unescwa.org/publications/arab-risk-monitor-conceptual-framework",
        role="framework",
    ),
    PaperMeta(
        doc_id="arm-drivers-of-conflict",
        filename="arab-risk-monitor-drivers-conflict-english.pdf",
        title="Arab Risk Monitor: Quantifying the Drivers of Risk of Conflict, version 1.0",
        short_title="ARM — Drivers of Conflict",
        authors="UN ESCWA",
        year=2023,
        publisher="United Nations, Beirut (E/ESCWA/CL6.GCP/2023/TP.1)",
        url="https://www.unescwa.org/publications/arab-risk-monitor-quantifying-drivers-risk-conflict",
        role="framework",
    ),
    PaperMeta(
        doc_id="arm-vulnerability-resilience",
        filename="arab-risk-monitor-assessing-vulnerability-resilience-region-english.pdf",
        title="Arab Risk Monitor: Assessing Vulnerability and Resilience in the Region",
        short_title="ARM — Vulnerability & Resilience",
        authors="UN ESCWA",
        year=2023,
        publisher="United Nations, Beirut (E/ESCWA/CL6.GCP/2023/TP.5)",
        url="https://www.unescwa.org/publications/arab-risk-monitor-assessing-vulnerability-resilience-region",
        role="framework",
    ),
]

_LIGATURES = {"ﬀ": "ff", "ﬃ": "ffi", "ﬄ": "ffl", "ﬁ": "fi", "ﬂ": "fl"}
_LIG_SPLIT = re.compile(r"([A-Za-z])(ffi|ffl|ff|fi|fl)\s([a-z])")
_WS = re.compile(r"[^\S\n]+")


def clean(text: str) -> str:
    for lig, rep in _LIGATURES.items():
        text = text.replace(lig, rep)
    text = text.replace(" ", " ")
    # de-hyphenate words broken across lines: "preven-\ntion" -> "prevention"
    text = re.sub(r"(\w)-\n(\w)", r"\1\2", text)
    text = text.replace("\n", " ")
    # this PDF set leaves a stray space after a decomposed ligature mid-word
    # ("confl ict" -> "conflict", "signifi cant" -> "significant")
    for _ in range(2):
        text = _LIG_SPLIT.sub(r"\1\2\3", text)
    text = _WS.sub(" ", text)
    return text.strip()


def page_section_map(doc: fitz.Document) -> dict[int, str]:
    """Map every 1-indexed page to the single most specific TOC section that
    contains it, so each page is extracted exactly once (nested TOC entries
    otherwise cause the same page to be chunked many times over)."""
    toc = doc.get_toc()
    n = doc.page_count
    if not toc:
        return {p: "(full text)" for p in range(1, n + 1)}

    entries = sorted(
        ((pg, lvl, title.strip()) for lvl, title, pg in toc if 1 <= pg <= n),
        key=lambda e: (e[0], e[1]),
    )
    paths: list[tuple[int, str]] = []
    stack: list[tuple[int, str]] = []
    for pg, lvl, title in entries:
        while stack and stack[-1][0] >= lvl:
            stack.pop()
        stack.append((lvl, title))
        paths.append((pg, " › ".join(t for _, t in stack)))

    out: dict[int, str] = {}
    for p in range(1, n + 1):
        current = paths[0][1]
        for pg, path in paths:
            if pg <= p:
                current = path
            else:
                break
        out[p] = current
    return out


def chunk_text(text: str) -> list[str]:
    if len(text) <= CHUNK_CHARS:
        return [text] if text else []
    out: list[str] = []
    start = 0
    while start < len(text):
        end = start + CHUNK_CHARS
        if end < len(text):
            window = text.rfind(". ", start + CHUNK_CHARS - 300, end)
            if window != -1:
                end = window + 1
        out.append(text[start:end].strip())
        start = end - CHUNK_OVERLAP
    return [c for c in out if c]


_SKIP_SECTIONS = (
    "cover", "copyright", "acknowledg", "abbreviation", "contents", "half title",
    "notes", "references", "additional reading", "index", "title",
)


def process_paper(meta: PaperMeta) -> list[dict]:
    path = PAPERS_DIR / meta.filename
    if not path.exists():
        raise FileNotFoundError(f"{path} missing — cannot build the papers corpus.")
    doc = fitz.open(path)
    sec_map = page_section_map(doc)

    records: list[dict] = []
    seq = 0
    for page in range(1, doc.page_count + 1):
        section = sec_map.get(page, "(full text)")
        low = section.lower()
        if any(skip in low for skip in _SKIP_SECTIONS):
            continue
        raw = clean(doc[page - 1].get_text())
        if len(raw) < 120:
            continue
        for chunk in chunk_text(raw):
            if len(chunk) < 120:
                continue
            seq += 1
            records.append(
                {
                    "chunk_id": f"{meta.doc_id}:{seq:04d}",
                    "doc_id": meta.doc_id,
                    "doc_title": meta.title,
                    "doc_short_title": meta.short_title,
                    "doc_year": meta.year,
                    "doc_url": meta.url,
                    "doc_role": meta.role,
                    "section": section,
                    "page": page,
                    "text": chunk,
                }
            )
    doc.close()
    return records


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    all_records: list[dict] = []
    manifest = []
    for meta in PAPERS:
        recs = process_paper(meta)
        all_records.extend(recs)
        manifest.append(
            {
                "doc_id": meta.doc_id,
                "title": meta.title,
                "short_title": meta.short_title,
                "authors": meta.authors,
                "year": meta.year,
                "publisher": meta.publisher,
                "url": meta.url,
                "role": meta.role,
                "filename": meta.filename,
                "chunk_count": len(recs),
            }
        )
        print(f"  {meta.doc_id}: {len(recs)} chunks")

    corpus_path = OUT_DIR / "corpus.jsonl"
    with corpus_path.open("w") as f:
        for rec in all_records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    (OUT_DIR / "manifest.json").write_text(
        json.dumps({"documents": manifest, "total_chunks": len(all_records)}, indent=2)
    )
    print(f"\nWrote {len(all_records)} chunks to {corpus_path}")


if __name__ == "__main__":
    main()
