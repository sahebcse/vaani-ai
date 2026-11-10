"""Hybrid retrieval: LangChain chain + OpenSearch store (Unit 5).

Lexical (BM25 match) + kNN vector queries fused client-side (weighted sum
over normalized scores) — no server plugin required. ef_search/candidates
and the fusion weights are explicit tuning knobs, pinned by unit tests.
"""

from __future__ import annotations

import hashlib
import random
from dataclasses import dataclass
from typing import Any

from langchain_core.runnables import Runnable, RunnableLambda
from opensearchpy import OpenSearch

from vaani.tools import PolicyDoc, Retriever

EMBEDDING_DIM = 64


@dataclass(frozen=True)
class ScoredDoc:
    text: str
    source: str
    score: float


class Embedder:
    def embed(self, texts: list[str]) -> list[list[float]]:
        raise NotImplementedError


class HashEmbedder(Embedder):
    """Deterministic stand-in embeddings (hash-seeded, L2-normalized).

    Real model embeddings plug in behind this interface later; the mock
    keeps Unit 5-7 e2e deterministic without GPU weights.
    """

    def __init__(self, dim: int = EMBEDDING_DIM) -> None:
        self._dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [self._one(text) for text in texts]

    def _one(self, text: str) -> list[float]:
        seed = int.from_bytes(hashlib.sha256(text.encode("utf-8")).digest()[:8])
        rng = random.Random(seed)
        vec = [rng.gauss(0.0, 1.0) for _ in range(self._dim)]
        norm = sum(v * v for v in vec) ** 0.5 or 1.0
        return [v / norm for v in vec]


def chunk_markdown(text: str, source: str, max_chars: int = 500) -> list[PolicyDoc]:
    """Split markdown into paragraph chunks, each attributed to its source."""
    chunks: list[PolicyDoc] = []
    index = 0
    for para in text.split("\n\n"):
        stripped = para.strip()
        if not stripped:
            continue
        body = stripped[:max_chars]
        chunks.append(PolicyDoc(text=body, source=f"{source}#p{index}"))
        index += 1
    return chunks


class DocumentStore:
    def ensure_index(self) -> None:
        raise NotImplementedError

    def index(self, docs: list[PolicyDoc], vectors: list[list[float]]) -> None:
        raise NotImplementedError

    def search(self, vector: list[float], text: str, tenant: str, k: int) -> list[ScoredDoc]:
        raise NotImplementedError


class OpenSearchStore(DocumentStore):
    """Hybrid lexical + kNN store. Tuning knobs: k, knn_candidates, weights."""

    def __init__(
        self,
        client: OpenSearch,
        index: str,
        dim: int = EMBEDDING_DIM,
        knn_candidates: int = 50,
        lexical_weight: float = 0.6,
        vector_weight: float = 0.4,
    ) -> None:
        self._client = client
        self._index = index
        self._dim = dim
        self._knn_candidates = knn_candidates
        self._lexical_weight = lexical_weight
        self._vector_weight = vector_weight

    def ensure_index(self) -> None:
        if self._client.indices.exists(index=self._index):
            return
        self._client.indices.create(
            index=self._index,
            body={
                "settings": {
                    "index.knn": True,
                    "number_of_shards": 1,
                    "number_of_replicas": 0,
                    "refresh_interval": "1s",
                },
                "mappings": {
                    "properties": {
                        "text": {"type": "text"},
                        "embedding": {
                            "type": "knn_vector",
                            "dimension": self._dim,
                        },
                        "tenant": {"type": "keyword"},
                        "source": {"type": "keyword"},
                    }
                },
            },
        )

    def index(self, docs: list[PolicyDoc], vectors: list[list[float]]) -> None:
        for doc, vector in zip(docs, vectors, strict=True):
            self._client.index(
                index=self._index,
                body={
                    "text": doc.text,
                    "embedding": vector,
                    "tenant": "shared",
                    "source": doc.source,
                },
                refresh=True,
            )

    def search(self, vector: list[float], text: str, tenant: str, k: int) -> list[ScoredDoc]:
        # Tenant docs plus the shared corpus are visible to every tenant.
        tenant_filter: dict[str, Any] = {
            "bool": {
                "should": [{"term": {"tenant": tenant}}, {"term": {"tenant": "shared"}}],
                "minimum_should_match": 1,
            }
        }
        lexical = self._client.search(
            index=self._index,
            body={
                "size": k,
                "query": {
                    "bool": {
                        "must": [{"match": {"text": text}}],
                        "filter": [tenant_filter],
                    }
                },
            },
        )
        knn = self._client.search(
            index=self._index,
            body={
                "size": self._knn_candidates,
                "query": {
                    "knn": {
                        "embedding": {
                            "vector": vector,
                            "k": self._knn_candidates,
                            "filter": tenant_filter,
                        }
                    }
                },
            },
        )
        return self._fuse(lexical, knn, k)

    def _fuse(self, lexical: dict[str, Any], knn: dict[str, Any], k: int) -> list[ScoredDoc]:
        def scored(resp: dict[str, Any]) -> dict[tuple[str, str], float]:
            hits = resp.get("hits", {}).get("hits", [])
            top = max([h.get("_score", 0.0) for h in hits] + [0.0])
            out: dict[tuple[str, str], float] = {}
            for hit in hits:
                src = hit.get("_source", {})
                key = (str(src.get("text", "")), str(src.get("source", "")))
                out[key] = (hit.get("_score", 0.0) / top) if top > 0 else 0.0
            return out

        lex, vec = scored(lexical), scored(knn)
        combined: dict[tuple[str, str], float] = {}
        for key in set(lex) | set(vec):
            combined[key] = self._lexical_weight * lex.get(
                key, 0.0
            ) + self._vector_weight * vec.get(key, 0.0)
        ranked = sorted(combined.items(), key=lambda item: item[1], reverse=True)[:k]
        return [
            ScoredDoc(text=text, source=source, score=score) for (text, source), score in ranked
        ]


class OpenSearchRetriever(Retriever):
    def __init__(self, store: DocumentStore, embedder: Embedder, k: int = 3) -> None:
        self._store = store
        self._embedder = embedder
        self._k = k

    async def retrieve(self, query: str, tenant: str) -> list[PolicyDoc]:
        vector = self._embedder.embed([query])[0]
        hits = self._store.search(vector, query, tenant, self._k)
        return [PolicyDoc(text=hit.text, source=hit.source) for hit in hits]


def build_policy_chain(
    retriever: Retriever,
) -> Runnable[dict[str, str], str]:
    """LangChain retrieval chain: query -> docs -> cited answer context."""

    async def _run(inputs: dict[str, str]) -> str:
        docs = await retriever.retrieve(inputs["query"], inputs["tenant"])
        if not docs:
            return "no policies found"
        return "\n".join(f"[{doc.source}] {doc.text}" for doc in docs)

    def _sync_only(inputs: dict[str, str]) -> str:
        del inputs
        raise RuntimeError("policy chain is async-only; use ainvoke")

    return RunnableLambda(_sync_only, afunc=_run)
