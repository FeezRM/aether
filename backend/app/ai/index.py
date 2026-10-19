"""Find the passages of a document that answer a question.

Chunks are built from the same text blocks the editor shows (with PDF-space
rects, so answers can point at the page and highlight the passage). Short
documents go to the model whole; longer ones are searched with BM25 keyword
ranking fused with embedding similarity.
"""

from __future__ import annotations

import math
import re
import threading
from collections import Counter
from dataclasses import dataclass

from ..inspect_doc import page_detail
from ..store import DocEntry
from .runtime import LLM

CHUNK_WORDS = 120
TOP_K = 6
RRF_K = 60
WORD = re.compile(r"\w+")


@dataclass
class Chunk:
    page: int
    rect: list[float]
    text: str


def tokens(text: str) -> list[str]:
    return WORD.findall(text.lower())


def _union(a: list[float], b: list[float]) -> list[float]:
    return [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]


def build_chunks(entry: DocEntry, page_count: int) -> list[Chunk]:
    chunks: list[Chunk] = []
    for p in range(page_count):
        current: Chunk | None = None
        for block in page_detail(entry, p)["blocks"]:
            text = " ".join(block["text"].split())
            if current and len(tokens(current.text)) + len(tokens(text)) <= CHUNK_WORDS:
                current.text += " " + text
                current.rect = _union(current.rect, block["rect"])
            else:
                current = Chunk(p, list(block["rect"]), text)
                chunks.append(current)
    return chunks


class BM25:
    def __init__(self, docs: list[list[str]], k1: float = 1.5, b: float = 0.75) -> None:
        self.k1, self.b = k1, b
        self.tf = [Counter(d) for d in docs]
        self.len = [len(d) for d in docs]
        self.avg = sum(self.len) / len(docs) if docs else 0.0
        df = Counter(t for d in docs for t in set(d))
        n = len(docs)
        self.idf = {t: math.log(1 + (n - f + 0.5) / (f + 0.5)) for t, f in df.items()}

    def scores(self, query: list[str]) -> list[float]:
        out = []
        for tf, length in zip(self.tf, self.len):
            s = 0.0
            for t in query:
                f = tf.get(t)
                if f:
                    s += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * length / self.avg))
            out.append(s)
        return out


def _ranks(scores: list[float]) -> list[int]:
    """Indices ordered best first, ignoring zero scores."""
    return [i for i in sorted(range(len(scores)), key=lambda i: -scores[i]) if scores[i] > 0]


class DocIndex:
    def __init__(self, chunks: list[Chunk]) -> None:
        self.chunks = chunks
        self.bm25 = BM25([tokens(c.text) for c in chunks])

    def total_chars(self) -> int:
        return sum(len(c.text) for c in self.chunks)

    def search(self, query: str, llm: LLM | None, k: int = TOP_K) -> list[Chunk]:
        rankings = [_ranks(self.bm25.scores(tokens(query)))]
        if llm is not None and self.chunks:
            vectors = _embeddings(llm, [c.text for c in self.chunks])
            q = llm.embed([query])[0]
            rankings.append(_ranks([sum(a * b for a, b in zip(q, v)) for v in vectors]))
        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, i in enumerate(ranking):
                fused[i] = fused.get(i, 0.0) + 1 / (RRF_K + rank + 1)
        best = sorted(fused, key=lambda i: -fused[i])[:k]
        return [self.chunks[i] for i in sorted(best)]


# Embeddings are cached by chunk text, so an edit only re-embeds the chunks it changed.
_vectors: dict[str, list[float]] = {}
_indexes: dict[str, tuple[int, DocIndex]] = {}
_lock = threading.Lock()


def _embeddings(llm: LLM, texts: list[str]) -> list[list[float]]:
    missing = [t for t in dict.fromkeys(texts) if t not in _vectors]
    for start in range(0, len(missing), 32):
        batch = missing[start:start + 32]
        _vectors.update(zip(batch, llm.embed(batch)))
    return [_vectors[t] for t in texts]


def index_for(entry: DocEntry, page_count: int) -> DocIndex:
    with _lock:
        cached = _indexes.get(entry.id)
        if cached and cached[0] == entry.version:
            return cached[1]
    idx = DocIndex(build_chunks(entry, page_count))
    with _lock:
        _indexes[entry.id] = (entry.version, idx)
    return idx


def context_chunks(idx: DocIndex, question: str, llm: LLM | None, n_ctx: int) -> list[Chunk]:
    """Everything if it fits in about 60% of the context window, else the best matches."""
    if idx.total_chars() / 4 <= 0.6 * n_ctx:
        return idx.chunks
    return idx.search(question, llm)


def forget(doc_id: str) -> None:
    with _lock:
        _indexes.pop(doc_id, None)
