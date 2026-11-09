"""Unit tests for the LangGraph agent (mock responder, no network)."""

from vaani.agent import AgentReply, AgentRunner, AgentState
from vaani.llm import MockResponder
from vaani.tools import (
    Account,
    InMemoryAccountStore,
    KeywordRetriever,
    MemoryEscalationSink,
    PolicyDoc,
)


def runner(
    docs: list[PolicyDoc] | None = None,
    accounts: dict[str, Account] | None = None,
) -> tuple[AgentRunner, MemoryEscalationSink]:
    sink = MemoryEscalationSink()
    agent = AgentRunner(
        MockResponder(),
        KeywordRetriever(
            docs if docs is not None else [PolicyDoc(text="loan payment policy", source="p.md")]
        ),
        InMemoryAccountStore(accounts if accounts is not None else {}),
        sink,
    )
    return agent, sink


async def test_policy_search_cites_docs() -> None:
    agent, _ = runner()
    reply = await agent.run("mera loan pending hai", "hi", "t1")
    assert isinstance(reply, AgentReply)
    assert reply.citations == ["p.md"]
    assert not reply.escalated
    assert "loan payment policy" in reply.text


async def test_account_lookup_reports_balance() -> None:
    agent, _ = runner(accounts={"caller": Account("caller", "Rohan", 500.0, "2026-11-01")})
    reply = await agent.run("my balance is overdue", "en", "t1")
    assert "500.0" in reply.text
    assert not reply.escalated


async def test_account_lookup_missing_account() -> None:
    agent, _ = runner()
    reply = await agent.run("my balance is overdue", "en", "t1")
    assert "no account found" in reply.text


async def test_escalate_records_and_flags() -> None:
    agent, sink = runner()
    reply = await agent.run("talk to a human please", "en", "t1")
    assert reply.escalated
    assert len(sink.records) == 1
    assert sink.records[0].tenant == "t1"


async def test_chitchat_echoes_without_tools() -> None:
    agent, sink = runner()
    reply = await agent.run("hello there", "en", "t1")
    assert "hello there" in reply.text
    assert reply.citations == []
    assert not reply.escalated
    assert sink.records == []


async def test_unknown_intent_falls_back_to_chitchat() -> None:
    agent, _ = runner()
    state: AgentState = {
        "text": "x",
        "language": "en",
        "tenant": "t",
        "intent": "mystery",
    }
    out = await agent._act(state)
    assert str(out["observation"]) == "x"


async def test_empty_docs_retrieval_still_replies() -> None:
    agent, _ = runner(docs=[])
    reply = await agent.run("loan policy batao", "hi", "t1")
    assert isinstance(reply.text, str)
