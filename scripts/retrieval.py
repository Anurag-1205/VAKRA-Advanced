"""Tool retrievers, shared by the offline evaluation (tool_recall.py) and the runner (V2).

Every retriever ranks the same "name: description" text upstream's ToolShortlister embeds:
  minilm  upstream's model and similarity (all-MiniLM-L6-v2, cosine): V0
  bm25    Okapi BM25 (k1=1.5, b=0.75)
  hybrid  reciprocal-rank fusion of minilm and bm25 (RRF constant 60)

Shortlister is upstream's ToolShortlister with the ranking swapped for bm25 or hybrid; the
runner patches it into upstream's agent at run time, so upstream's code stays unmodified.
Needs third_party/vakra on sys.path (the runner runs from there).
"""
import math
import re
from collections import Counter

import numpy as np

from agents.components.tool_shortlister import ToolShortlister

RETRIEVERS = ("minilm", "bm25", "hybrid")
RRF_K = 60


def tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", text.lower())


class BM25:
    def __init__(self, docs: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.docs = [Counter(tokenize(d)) for d in docs]
        self.lens = np.array([sum(d.values()) for d in self.docs], dtype=float)
        self.avg = self.lens.mean() if len(self.docs) else 0.0
        df = Counter(t for d in self.docs for t in d)
        n = len(self.docs)
        self.idf = {t: math.log(1 + (n - c + 0.5) / (c + 0.5)) for t, c in df.items()}

    def scores(self, query: str) -> np.ndarray:
        out = np.zeros(len(self.docs))
        norm = self.k1 * (1 - self.b + self.b * self.lens / self.avg)
        for t in set(tokenize(query)):
            if t not in self.idf:
                continue
            tf = np.array([d.get(t, 0) for d in self.docs], dtype=float)
            out += self.idf[t] * tf * (self.k1 + 1) / (tf + norm)
        return out


def rank(scores: np.ndarray) -> np.ndarray:
    """Candidate indices, best first (stable, like np.argsort on ties)."""
    return np.argsort(-scores, kind="stable")


def rrf(*orders: np.ndarray) -> np.ndarray:
    """Reciprocal-rank fusion of candidate orderings (best first); returns the fused ordering."""
    fused = np.zeros(len(orders[0]))
    for order in orders:
        pos = np.empty(len(order), dtype=int)
        pos[order] = np.arange(len(order))
        fused += 1 / (RRF_K + 1 + pos)
    return rank(fused)


def normalize(emb: np.ndarray) -> np.ndarray:
    norm = np.linalg.norm(emb, axis=-1, keepdims=True)
    return emb / np.where(norm == 0, 1, norm)


def rankings(query: str, cand_emb: np.ndarray, bm25: BM25, model) -> dict[str, np.ndarray]:
    """{retriever: candidate indices, best first}. cand_emb must be L2-normalized."""
    q = normalize(model.encode([query], convert_to_numpy=True)[0])
    dense, sparse = rank(cand_emb @ q), rank(bm25.scores(query))
    return {"minilm": dense, "bm25": sparse, "hybrid": rrf(dense, sparse)}


class Shortlister(ToolShortlister):
    """Upstream's ToolShortlister with bm25 or hybrid ranking.

    Same contract as upstream: catalogs of <= top_k tools pass through whole, query_* tools are
    always kept and take the first slots, the rest are filled by rank.
    """

    retriever = "hybrid"

    def encode_tools(self, tools: list) -> None:
        super().encode_tools(tools)
        self._cand_idx = [i for i, t in enumerate(self._tools) if not self._tool_name(t).startswith("query_")]
        self._cand_emb = normalize(self._tool_embeddings[self._cand_idx])
        self._bm25 = BM25([self._tool_text(self._tools[i]) for i in self._cand_idx])

    def shortlist(self, query: str, tools: list) -> list:
        if len(tools) <= self.top_k:
            return tools
        if self._tools is None or [self._tool_name(t) for t in tools] != [self._tool_name(t) for t in self._tools]:
            self.encode_tools(tools)
        pinned = [t for t in tools if self._tool_name(t).startswith("query_")]
        candidates = [tools[i] for i in self._cand_idx]
        slots = self.top_k - len(pinned)
        if slots <= 0 or not candidates:
            return pinned
        if slots >= len(candidates):
            return pinned + candidates
        order = rankings(query, self._cand_emb, self._bm25, self.model)[self.retriever]
        return pinned + [candidates[i] for i in order[:slots]]
