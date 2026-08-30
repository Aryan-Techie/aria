"""Zero-dependency TF-IDF keyword retriever over the RAG corpus.

Deliberate deviation from the original plan's "Chroma + embeddings" choice:
Chroma's default embedding function downloads an ONNX model from HuggingFace
on first use, which hung for 90s+ with no progress when tested against this
environment's network — an unacceptable risk on demo day for a 4-document
corpus that doesn't need semantic embeddings to retrieve well. Plain TF-IDF
keyword scoring is instant, deterministic, and has no network dependency.
Swappable later (this module is the only seam) if real embeddings are wanted.
"""
import math
import re
from collections import Counter

from pydantic import BaseModel

from app.rag.ingest import Chunk, build_corpus

_WORD_RE = re.compile(r"[a-z0-9]+")


class SearchResult(BaseModel):
    source: str
    text: str
    score: float


def _tokenize(text: str) -> list[str]:
    return _WORD_RE.findall(text.lower())


class KeywordIndex:
    def __init__(self, chunks: list[Chunk]):
        self.chunks = chunks
        self._term_freqs: list[Counter] = [Counter(_tokenize(c.text)) for c in chunks]
        self._idf = self._compute_idf()

    def _compute_idf(self) -> dict[str, float]:
        n_docs = len(self.chunks)
        doc_freq: Counter = Counter()
        for tf in self._term_freqs:
            for term in tf:
                doc_freq[term] += 1
        return {
            term: math.log((n_docs + 1) / (df + 1)) + 1.0
            for term, df in doc_freq.items()
        }

    def search(self, query: str, top_k: int = 4) -> list[SearchResult]:
        query_terms = _tokenize(query)
        if not query_terms:
            return []

        results: list[SearchResult] = []
        for chunk, tf in zip(self.chunks, self._term_freqs):
            if not tf:
                continue
            score = 0.0
            for term in query_terms:
                if term in tf:
                    idf = self._idf.get(term, 0.0)
                    score += (tf[term] / len(tf)) * idf
            if score > 0:
                results.append(SearchResult(source=chunk.source, text=chunk.text, score=score))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]


_index: KeywordIndex | None = None


def get_index() -> KeywordIndex:
    global _index
    if _index is None:
        _index = KeywordIndex(build_corpus())
    return _index


def search(query: str, top_k: int = 4) -> list[SearchResult]:
    return get_index().search(query, top_k=top_k)


def top_score(query: str) -> float:
    """Highest match score for a query — used by the escalation guardrail
    to detect a likely-unanswerable question (low RAG confidence)."""
    results = search(query, top_k=1)
    return results[0].score if results else 0.0
