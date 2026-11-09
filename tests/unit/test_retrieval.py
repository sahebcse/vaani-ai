"""Unit tests for hybrid retrieval (OpenSearch client mocked; no Docker)."""

from typing import Any
from unittest.mock import MagicMock

import pytest

from vaani.retrieval import (
    EMBEDDING_DIM,
    DocumentStore,
    Embedder,
    HashEmbedder,
    OpenSearchRetriever,
    OpenSearchStore,
    ScoredDoc,
    build_policy_chain,
    chunk_markdown,
)
from vaani.tools import KeywordRetriever, PolicyDoc


def test_embedder_is_deterministic_and_normalized() -> None:
    embedder = HashEmbedder()
    first = embedder.embed(["hello", "world"])
    second = embedder.embed(["hello", "world"])
    assert first == second
    assert len(first[0]) == EMBEDDING_DIM
    norm = sum(v * v for v in first[0]) ** 0.5
    assert norm == pytest.approx(1.0)
    assert embedder.embed(["hello"])[0] != embedder.embed(["other"])[0]
    assert embedder.embed([]) == []


def test_embedder_custom_dim() -> None:
    assert len(HashEmbedder(dim=8).embed(["x"])[0]) == 8


def test_chunk_markdown_splits_and_attributes() -> None:
    docs = chunk_markdown("first para\n\n\nsecond para\n\n", "s.md")
    assert [(d.source, d.text) for d in docs] == [
        ("s.md#p0", "first para"),
        ("s.md#p1", "second para"),
    ]


def test_chunk_markdown_truncates_long_paragraphs() -> None:
    docs = chunk_markdown("x" * 100, "s.md", max_chars=10)
    assert docs[0].text == "x" * 10


def test_abstract_bases_raise() -> None:
    with pytest.raises(NotImplementedError):
        Embedder().embed(["x"])
    store = DocumentStore()
    with pytest.raises(NotImplementedError):
        store.ensure_index()
    with pytest.raises(NotImplementedError):
        store.index([], [])
    with pytest.raises(NotImplementedError):
        store.search([0.0], "q", "t", 3)


def mock_client() -> MagicMock:
    return MagicMock()


def test_ensure_index_skips_when_exists() -> None:
    client = mock_client()
    client.indices.exists.return_value = True
    OpenSearchStore(client, "idx").ensure_index()
    client.indices.create.assert_not_called()


def test_ensure_index_creates_knn_mapping() -> None:
    client = mock_client()
    client.indices.exists.return_value = False
    OpenSearchStore(client, "idx", dim=8).ensure_index()
    _, kwargs = client.indices.create.call_args
    assert kwargs["index"] == "idx"
    assert kwargs["body"]["settings"]["index.knn"] is True
    assert kwargs["body"]["mappings"]["properties"]["embedding"]["dimension"] == 8


def docs() -> list[PolicyDoc]:
    return [
        PolicyDoc(text="loan payment pending", source="a.md"),
        PolicyDoc(text="balance overdue fee", source="b.md"),
    ]


def hit(text: str, source: str, score: float) -> dict[str, Any]:
    return {"_score": score, "_source": {"text": text, "source": source}}


def test_index_sends_embeddings_per_doc() -> None:
    client = mock_client()
    store = OpenSearchStore(client, "idx")
    store.index(docs(), [[0.1, 0.2], [0.3, 0.4]])
    assert client.index.call_count == 2
    _, kwargs = client.index.call_args_list[0]
    assert kwargs["body"]["text"] == "loan payment pending"
    assert kwargs["body"]["embedding"] == [0.1, 0.2]


def test_search_fuses_lexical_and_vector() -> None:
    client = mock_client()
    client.search.side_effect = [
        {"hits": {"hits": [hit("loan payment pending", "a.md", 2.0)]}},
        {
            "hits": {
                "hits": [
                    hit("balance overdue fee", "b.md", 1.0),
                    hit("loan payment pending", "a.md", 0.5),
                ]
            }
        },
    ]
    store = OpenSearchStore(client, "idx")
    out = store.search([0.1], "loan", "t1", k=2)
    assert [d.source for d in out] == ["a.md", "b.md"]
    assert out[0].score == pytest.approx(0.6 * 1.0 + 0.4 * 0.5)
    # tenant filter + knn candidates flow into the request bodies
    lex_body = client.search.call_args_list[0].kwargs["body"]
    knn_body = client.search.call_args_list[1].kwargs["body"]
    assert lex_body["query"]["bool"]["filter"] == [{"term": {"tenant": "t1"}}]
    assert knn_body["query"]["knn"]["embedding"]["k"] == 50


def test_search_empty_results() -> None:
    client = mock_client()
    client.search.return_value = {"hits": {"hits": []}}
    assert OpenSearchStore(client, "idx").search([0.1], "q", "t", 3) == []


class FakeStore(DocumentStore):
    def __init__(self) -> None:
        self.calls: dict[str, Any] = {}

    def ensure_index(self) -> None:
        pass

    def index(self, docs: list[PolicyDoc], vectors: list[list[float]]) -> None:
        pass

    def search(self, vector: list[float], text: str, tenant: str, k: int) -> list[ScoredDoc]:
        self.calls.update(vector=vector, text=text, tenant=tenant, k=k)
        return [ScoredDoc(text="t", source="s.md", score=0.5)]


async def test_retriever_maps_hits_to_policy_docs() -> None:
    store = FakeStore()
    retriever = OpenSearchRetriever(store, HashEmbedder(), k=3)
    out = await retriever.retrieve("q", "t1")
    assert store.calls == {
        "vector": HashEmbedder().embed(["q"])[0],
        "text": "q",
        "tenant": "t1",
        "k": 3,
    }
    assert out == [PolicyDoc(text="t", source="s.md")]


async def test_policy_chain_formats_citations() -> None:
    chain = build_policy_chain(KeywordRetriever(docs()))
    out = await chain.ainvoke({"query": "loan payment", "tenant": "t1"})
    assert "[a.md] loan payment pending" in out


async def test_policy_chain_empty_docs() -> None:
    chain = build_policy_chain(KeywordRetriever([]))
    assert await chain.ainvoke({"query": "loan", "tenant": "t1"}) == "no policies found"


def test_policy_chain_sync_invoke_rejected() -> None:
    import pytest

    chain = build_policy_chain(KeywordRetriever([]))
    with pytest.raises(RuntimeError, match="async-only"):
        chain.invoke({"query": "loan", "tenant": "t1"})
