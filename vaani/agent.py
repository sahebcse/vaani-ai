"""LangGraph agent: understand -> act -> respond.

Runs per turn; stateless across turns in Unit 4 (Redis memory lands in U6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import END, StateGraph

from vaani.llm import Responder
from vaani.tools import (
    AccountStore,
    Escalation,
    EscalationSink,
    Retriever,
)


@dataclass(frozen=True)
class AgentReply:
    text: str
    citations: list[str] = field(default_factory=list)
    escalated: bool = False


class AgentState(TypedDict, total=False):
    text: str
    language: str
    tenant: str
    intent: str
    observation: str
    citations: list[str]
    escalated: bool
    reply: str


_UNDERSTAND_SYSTEM = "intent: classify the user turn into exactly one label"
_RESPOND_SYSTEM = "reply: answer in the user's language, grounded in observation"


class AgentRunner:
    def __init__(
        self,
        responder: Responder,
        retriever: Retriever,
        accounts: AccountStore,
        escalations: EscalationSink,
    ) -> None:
        self._responder = responder
        self._retriever = retriever
        self._accounts = accounts
        self._escalations = escalations
        graph = StateGraph(AgentState)
        graph.add_node("understand", self._understand)
        graph.add_node("act", self._act)
        graph.add_node("respond", self._respond)
        graph.set_entry_point("understand")
        graph.add_edge("understand", "act")
        graph.add_edge("act", "respond")
        graph.add_edge("respond", END)
        self._graph = graph.compile()

    async def _understand(self, state: AgentState) -> AgentState:
        intent = await self._responder.complete(_UNDERSTAND_SYSTEM, state["text"])
        return {"intent": intent.strip()}

    async def _act(self, state: AgentState) -> AgentState:
        intent = state.get("intent", "chitchat")
        if intent == "policy_search":
            docs = await self._retriever.retrieve(state["text"], state["tenant"])
            return {
                "observation": " ".join(doc.text for doc in docs),
                "citations": [doc.source for doc in docs],
            }
        if intent == "account_lookup":
            account = await self._accounts.lookup("caller", state["tenant"])
            if account is None:
                return {"observation": "no account found", "citations": []}
            return {
                "observation": (
                    f"{account.name} balance due {account.balance_due} " f"by {account.due_date}"
                ),
                "citations": [],
            }
        if intent == "escalate":
            await self._escalations.record(
                Escalation(
                    tenant=state["tenant"],
                    reason="user requested human",
                    transcript=state["text"],
                )
            )
            return {"observation": "connecting you to a human agent", "citations": []}
        return {"observation": state["text"], "citations": []}

    async def _respond(self, state: AgentState) -> AgentState:
        reply = await self._responder.complete(
            _RESPOND_SYSTEM,
            f"intent={state.get('intent', 'chitchat')} "
            f"observation={state.get('observation', '')}",
        )
        return {"reply": reply, "escalated": state.get("intent") == "escalate"}

    async def run(self, text: str, language: str, tenant: str) -> AgentReply:
        final = await self._graph.ainvoke(
            {
                "text": text,
                "language": language,
                "tenant": tenant,
                "citations": [],
            }
        )
        cites: list[str] = final.get("citations", [])
        return AgentReply(
            text=final.get("reply", ""),
            citations=cites,
            escalated=final.get("intent") == "escalate",
        )
