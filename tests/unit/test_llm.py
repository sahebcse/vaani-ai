"""Unit tests for the LLM layer (no network; stub chat model in-test)."""

from typing import Any

import pytest
from langchain_core.language_models import BaseChatModel
from langchain_core.messages import AIMessage
from langchain_core.outputs import ChatGeneration, ChatResult

from vaani.llm import FallbackResponder, LangChainLLMResponder, MockResponder


class BoomResponder(MockResponder):
    async def complete(self, system: str, user: str) -> str:
        raise RuntimeError("primary down")


async def test_mock_intent_routing() -> None:
    responder = MockResponder()
    assert await responder.complete("intent: x", "my balance is overdue") == "account_lookup"
    assert await responder.complete("intent: x", "मेरा लोन चाहिए") == "policy_search"
    assert await responder.complete("intent: x", "talk to a human") == "escalate"
    assert await responder.complete("intent: x", "hello there") == "chitchat"


async def test_mock_passthrough_when_not_classifying() -> None:
    responder = MockResponder()
    assert await responder.complete("reply:", "hello") == "hello"


class StubChatModel(BaseChatModel):
    canned: list[str]

    @property
    def _llm_type(self) -> str:
        return "stub"

    def _generate(
        self,
        messages: Any,
        stop: Any = None,
        run_manager: Any = None,
        **kwargs: Any,
    ) -> ChatResult:
        return ChatResult(
            generations=[ChatGeneration(message=AIMessage(content=self.canned.pop(0)))]
        )


async def test_langchain_responder_returns_text() -> None:
    responder = LangChainLLMResponder(StubChatModel(canned=["namaste"]))
    assert await responder.complete("sys", "user") == "namaste"


async def test_langchain_responder_coerces_non_string() -> None:
    class ListContentModel(StubChatModel):
        def _generate(
            self,
            messages: Any,
            stop: Any = None,
            run_manager: Any = None,
            **kwargs: Any,
        ) -> ChatResult:
            from langchain_core.messages import AIMessage

            return ChatResult(generations=[ChatGeneration(message=AIMessage(content=["a", "b"]))])

    responder = LangChainLLMResponder(ListContentModel(canned=[]))
    assert await responder.complete("sys", "user") == "['a', 'b']"


async def test_fallback_uses_primary_when_healthy() -> None:
    router = FallbackResponder(MockResponder(), MockResponder())
    assert await router.complete("reply:", "hi") == "hi"


async def test_fallback_switches_on_primary_failure() -> None:
    router = FallbackResponder(BoomResponder(), MockResponder())
    assert await router.complete("reply:", "hi") == "hi"


async def test_fallback_raises_when_both_fail() -> None:
    router = FallbackResponder(BoomResponder(), BoomResponder())
    with pytest.raises(RuntimeError, match="primary down"):
        await router.complete("reply:", "hi")
