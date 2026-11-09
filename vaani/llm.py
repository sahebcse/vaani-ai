"""LLM layer: Responder ABC, rule-based mock, LangChain adapter, fallback router.

Local e2e and unit tests run on MockResponder (deterministic, no keys).
LangChainLLMResponder activates when LLM credentials exist (env LLM_BASE_URL);
FallbackResponder tries primary, then fallback — the multi-LLM story.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import HumanMessage, SystemMessage


class Responder(ABC):
    @abstractmethod
    async def complete(self, system: str, user: str) -> str: ...


class MockResponder(Responder):
    """Keyword intent classifier + template replies. Deterministic by design."""

    async def complete(self, system: str, user: str) -> str:
        lowered = user.lower()
        if "intent:" in system:
            if any(k in lowered for k in ("balance", "बकाया", "due", "account")):
                return "account_lookup"
            if any(k in lowered for k in ("policy", "पॉलिसी", "loan", "लोन", "fee", "शुल्क")):
                return "policy_search"
            if any(k in lowered for k in ("human", "agent", "एजेंट", "इंसान")):
                return "escalate"
            return "chitchat"
        return user


class LangChainLLMResponder(Responder):
    """Thin adapter over any LangChain chat model."""

    def __init__(self, chat_model: BaseChatModel) -> None:
        self._chat_model = chat_model

    async def complete(self, system: str, user: str) -> str:
        message = await self._chat_model.ainvoke(
            [SystemMessage(content=system), HumanMessage(content=user)]
        )
        content = message.content
        if isinstance(content, str):
            return content
        return str(content)


class FallbackResponder(Responder):
    """Primary LLM first, fallback LLM on any failure."""

    def __init__(self, primary: Responder, fallback: Responder) -> None:
        self._primary = primary
        self._fallback = fallback

    async def complete(self, system: str, user: str) -> str:
        try:
            return await self._primary.complete(system, user)
        except Exception:
            return await self._fallback.complete(system, user)
