"""Unit tests for agent tools (no I/O, no containers)."""

import pytest

from vaani.tools import (
    Account,
    Escalation,
    InMemoryAccountStore,
    KeywordRetriever,
    MemoryEscalationSink,
    PolicyDoc,
)


def docs() -> list[PolicyDoc]:
    return [
        PolicyDoc(text="loan payment pending within seven days", source="a.md"),
        PolicyDoc(text="balance overdue late fee policy", source="b.md"),
    ]


async def test_keyword_retriever_ranks_by_overlap() -> None:
    retriever = KeywordRetriever(docs())
    hits = await retriever.retrieve("my loan payment is pending", "t1")
    assert hits[0].source == "a.md"


async def test_keyword_retriever_falls_back_to_first_doc() -> None:
    retriever = KeywordRetriever(docs())
    hits = await retriever.retrieve("xyzzy", "t1")
    assert [d.source for d in hits] == ["a.md"]


async def test_keyword_retriever_caps_at_two() -> None:
    many = [PolicyDoc(text="loan payment policy fee", source=f"{i}.md") for i in range(5)]
    hits = await KeywordRetriever(many).retrieve("loan payment", "t1")
    assert len(hits) == 2


async def test_account_store_hit_and_miss() -> None:
    store = InMemoryAccountStore(
        {"u1": Account(user_id="u1", name="A", balance_due=10.0, due_date="2026-01-01")}
    )
    found = await store.lookup("u1", "t1")
    assert found is not None and found.name == "A"
    assert await store.lookup("ghost", "t1") is None


async def test_escalation_sink_records() -> None:
    sink = MemoryEscalationSink()
    assert sink.records == []
    await sink.record(Escalation(tenant="t", reason="r", transcript="hi"))
    assert [r.reason for r in sink.records] == ["r"]


async def test_abstract_tools_raise() -> None:
    from vaani.tools import AccountStore, EscalationSink, Retriever

    with pytest.raises(NotImplementedError):
        await Retriever().retrieve("q", "t")
    with pytest.raises(NotImplementedError):
        await AccountStore().lookup("u", "t")
    with pytest.raises(NotImplementedError):
        await EscalationSink().record(Escalation(tenant="t", reason="r", transcript="x"))
