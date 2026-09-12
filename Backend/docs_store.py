"""Lightweight document retrieval for company policies (the "RAG" half).

The previous build advertised ChromaDB but returned one hard-coded travel
policy string for every question.  Wiring a vector DB + embedding service into
an air-gapped ERP box is a deployment problem, so this uses a dependency-free
BM25-style ranker over Markdown files in Backend/knowledge/.  It answers from
real content, cites the document + section, and takes ~1 ms.

Drop-in upgrade path: replace `search()` with a Chroma/pgvector query — the
return shape is all the agent depends on.
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

import config

STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "for", "on", "is", "are",
    "what", "which", "how", "our", "we", "i", "do", "does", "can", "with", "by",
    "at", "be", "as", "it", "this", "that", "from", "my", "me", "you", "your",
    "please", "tell", "show", "about", "any", "all",
}


@dataclass
class Chunk:
    doc: str
    title: str
    section: str
    text: str
    tokens: Counter
    length: int


def _tokenise(text: str) -> list[str]:
    return [t for t in re.findall(r"[a-z0-9']+", text.lower()) if t not in STOPWORDS and len(t) > 1]


class DocumentStore:
    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory or config.KNOWLEDGE_DIR)
        self._chunks: list[Chunk] = []
        self._df: Counter = Counter()
        self._avg_len = 1.0
        self._loaded = False
        self._lock = threading.Lock()

    def _load(self) -> None:
        if self._loaded:
            return
        with self._lock:
            if self._loaded:
                return
            chunks: list[Chunk] = []
            if self.directory.exists():
                for path in sorted(self.directory.glob("**/*.md")):
                    raw = path.read_text(encoding="utf-8", errors="ignore")
                    title = raw.splitlines()[0].lstrip("# ").strip() if raw.strip() else path.stem
                    sections = re.split(r"\n(?=##\s)", raw)
                    for section in sections:
                        body = section.strip()
                        if len(body) < 40:
                            continue
                        heading = body.splitlines()[0].lstrip("# ").strip()
                        tokens = Counter(_tokenise(body))
                        chunks.append(
                            Chunk(
                                doc=path.name,
                                title=title,
                                section=heading,
                                text=body,
                                tokens=tokens,
                                length=sum(tokens.values()) or 1,
                            )
                        )
            self._chunks = chunks
            self._df = Counter()
            for c in chunks:
                for term in c.tokens:
                    self._df[term] += 1
            self._avg_len = (sum(c.length for c in chunks) / len(chunks)) if chunks else 1.0
            self._loaded = True

    def reload(self) -> None:
        self._loaded = False
        self._load()

    @property
    def document_count(self) -> int:
        self._load()
        return len({c.doc for c in self._chunks})

    def search(self, query: str, top_k: int = 3) -> list[dict]:
        """BM25 retrieval over the knowledge base.

        IMPORTANT - what the returned numbers mean, and what they do not:

        The previous version returned a key called ``similarity`` computed as
        ``0.55 + 0.44 * (score / top_score)``. That rescales the *best* hit to
        0.99 no matter how irrelevant it is, so a question with no real answer in
        the corpus still came back "similarity: 0.99". That is a fabricated
        confidence number, and it is worse than no number at all - a client will
        quote it back at you.

        We now return:
          * ``retrieval_score``  - the raw BM25 score (only meaningful relative
                                   to the other hits in the same query)
          * ``top_gap``          - how far ahead the top hit is from the runner
                                   up; ~0 means the ranking is a coin flip
          * ``abstain``          - True when nothing in the corpus clears a
                                   documented floor, so the caller can say
                                   "no policy covers this" instead of quoting
                                   the least-bad paragraph

        There is deliberately NO calibrated 0-1 confidence figure: BM25 is not
        calibrated, and inventing one is exactly the kind of fake accuracy this
        product is not allowed to ship.
        """
        self._load()
        terms = _tokenise(query)
        if not terms or not self._chunks:
            return []
        n = len(self._chunks)
        k1, b = 1.5, 0.75
        scored: list[tuple[float, Chunk]] = []
        for chunk in self._chunks:
            score = 0.0
            for term in terms:
                tf = chunk.tokens.get(term, 0)
                if not tf:
                    # partial credit for prefix matches ("invoice" ~ "invoices")
                    tf = sum(v for t, v in chunk.tokens.items() if t.startswith(term[:5]) and len(term) > 4)
                    if not tf:
                        continue
                    tf *= 0.5
                df = self._df.get(term, 1)
                idf = math.log(1 + (n - df + 0.5) / (df + 0.5))
                denom = tf + k1 * (1 - b + b * chunk.length / self._avg_len)
                score += idf * (tf * (k1 + 1)) / denom
            if score > 0:
                scored.append((score, chunk))
        scored.sort(key=lambda x: x[0], reverse=True)
        best = scored[:top_k]
        if not best:
            return []

        top_score = best[0][0]
        runner_up = best[1][0] if len(best) > 1 else 0.0
        # Floor below which we tell the user "nothing in the knowledge base
        # answers this" rather than quoting the closest paragraph. 1.5 is the
        # score of roughly a single, low-IDF term match; tune per corpus and
        # re-measure with tests/accuracy, do not guess.
        ABSTAIN_FLOOR = 1.5

        return [
            {
                "document": c.doc,
                "title": c.title,
                "section": c.section,
                "retrieval_score": round(score, 3),
                "top_gap": round(score - runner_up, 3) if score == top_score else None,
                "abstain": score < ABSTAIN_FLOOR,
                "content": c.text[:1800],
            }
            for score, c in best
        ]


_store = DocumentStore()


def search(query: str, top_k: int = 3) -> list[dict]:
    return _store.search(query, top_k)


def document_count() -> int:
    return _store.document_count


def reload() -> None:
    _store.reload()
