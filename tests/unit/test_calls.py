"""Unit tests for the WebSocket call loop (fake socket + fake provider)."""

import asyncio
from collections import deque
from typing import Any

from fastapi import WebSocketDisconnect
from fastapi.testclient import TestClient

from vaani.agent import AgentReply, AgentRunner
from vaani.calls import CallManager
from vaani.ledger import CallLog
from vaani.main import create_app
from vaani.sessions import InMemorySessionStore
from vaani.speech import SarvamError, SpeechAudio, Transcript
from vaani.tenancy import InMemoryTenantStore, Tenant


class FakeProvider:
    """SpeechProvider double with injectable behavior."""

    def __init__(self) -> None:
        self.block: asyncio.Event | None = None
        self.fail_transcribe: Exception | None = None
        self.fail_synthesize: Exception | None = None
        self.calls: list[str] = []

    async def atranscribe(self, audio: bytes, language_hint: str | None = None) -> Transcript:
        self.calls.append("transcribe")
        if self.fail_transcribe is not None:
            raise self.fail_transcribe
        if self.block is not None:
            await self.block.wait()
        return Transcript(text=f"heard-{len(audio)}", language="hi", confidence=1.0)

    async def asynthesize(self, text: str, language: str, voice: str | None = None) -> SpeechAudio:
        self.calls.append("synthesize")
        if self.fail_synthesize is not None:
            raise self.fail_synthesize
        return SpeechAudio(data=b"audio:" + text.encode(), content_type="audio/wav")

    async def atranslate(self, text: str, source_language: str, target_language: str) -> Any:
        raise AssertionError("not used in call loop")


class FakeWebSocket:
    def __init__(self, incoming: list[dict[str, Any]]) -> None:
        self._incoming: deque[dict[str, Any]] = deque(incoming)
        self.sent_json: list[dict[str, Any]] = []
        self.sent_bytes: list[bytes] = []
        self.accepted = False
        self.closed_code: int | None = None

    async def accept(self) -> None:
        self.accepted = True

    async def close(self, code: int = 1000, reason: str | None = None) -> None:
        del reason
        self.closed_code = code

    async def receive(self) -> dict[str, Any]:
        if self._incoming:
            return self._incoming.popleft()
        raise WebSocketDisconnect()

    async def send_json(self, data: dict[str, Any]) -> None:
        self.sent_json.append(data)

    async def send_bytes(self, data: bytes) -> None:
        self.sent_bytes.append(data)


def make_manager(
    provider: FakeProvider | None = None, escalated_reply: bool = False
) -> tuple[CallManager, FakeProvider, InMemorySessionStore, CallLog]:
    fake = provider or FakeProvider()
    store = InMemorySessionStore()
    tenants = InMemoryTenantStore(
        [Tenant(id="t1", display_name="T1"), Tenant(id="t9", display_name="T9")]
    )
    log = CallLog()

    class EchoAgent(AgentRunner):
        def __init__(self) -> None:
            pass

        async def run(self, text: str, language: str, tenant: str, style: str = "") -> AgentReply:
            del style
            return AgentReply(text=text, citations=[], escalated=escalated_reply)

    return (
        CallManager(fake, store, EchoAgent(), tenants, log),  # type: ignore[arg-type]
        fake,
        store,
        log,
    )


async def test_audio_frame_gets_reply_and_summary() -> None:
    manager, _, store, _log = make_manager()
    ws = FakeWebSocket([{"bytes": b"\x01\x02\x03"}, {"text": '{"type": "end"}'}])
    await manager.handle(ws, "t1")  # type: ignore[arg-type]
    assert ws.accepted
    assert ws.sent_bytes == [b"audio:heard-3"]
    assert ws.sent_json[0] == {
        "type": "reply",
        "sequence": 1,
        "text": "heard-3",
        "citations": [],
    }
    assert ws.sent_json[-1]["type"] == "summary"
    assert ws.sent_json[-1]["frames_received"] == 1
    assert ws.sent_json[-1]["transcript"] == "heard-3"
    assert store.count() == 0


async def test_busy_frame_dropped_and_counted() -> None:
    provider = FakeProvider()
    provider.block = asyncio.Event()
    manager, _, store, _log = make_manager(provider)
    ws = FakeWebSocket([{"bytes": b"a"}, {"bytes": b"b"}])
    await manager.handle(ws, "t1")  # type: ignore[arg-type]
    assert ws.sent_json[0] == {"type": "dropped", "sequence": 2}
    assert store.count() == 0


async def test_malformed_control_keeps_call_alive() -> None:
    manager, _, _, _ = make_manager()
    ws = FakeWebSocket([{"text": "not-json"}, {"text": '{"type": "end"}'}])
    await manager.handle(ws, "t1")  # type: ignore[arg-type]
    assert ws.sent_json[0] == {"type": "error", "stage": "control"}
    assert ws.sent_json[-1]["type"] == "summary"


async def test_unknown_control_type_rejected() -> None:
    manager, _, _, _ = make_manager()
    ws = FakeWebSocket([{"text": '{"type": "zap"}'}, {"text": '{"type": "end"}'}])
    await manager.handle(ws, "t1")  # type: ignore[arg-type]
    assert ws.sent_json[0] == {"type": "error", "stage": "control"}
    assert ws.sent_json[-1]["type"] == "summary"


async def test_neither_bytes_nor_text_treated_as_bad_control() -> None:
    manager, _, _, _ = make_manager()
    ws = FakeWebSocket([{"type": "websocket.close"}, {"text": '{"type": "end"}'}])
    await manager.handle(ws, "t1")  # type: ignore[arg-type]
    assert ws.sent_json[0] == {"type": "error", "stage": "control"}


async def test_transcribe_failure_reports_error_and_continues() -> None:
    provider = FakeProvider()
    provider.fail_transcribe = SarvamError("boom")
    manager, _, _, _ = make_manager(provider)
    ws = FakeWebSocket([{"bytes": b"a"}, {"text": '{"type": "end"}'}])
    await manager.handle(ws, "t1")  # type: ignore[arg-type]
    assert ws.sent_json[0] == {
        "type": "error",
        "stage": "transcribe",
        "detail": "boom",
    }
    assert ws.sent_bytes == []
    assert ws.sent_json[-1]["errors"] == 1


async def test_synthesize_failure_reports_error() -> None:
    provider = FakeProvider()
    provider.fail_synthesize = SarvamError("no-voice")
    manager, _, _, _ = make_manager(provider)
    ws = FakeWebSocket([{"bytes": b"a"}, {"text": '{"type": "end"}'}])
    await manager.handle(ws, "t1")  # type: ignore[arg-type]
    assert ws.sent_json[0]["stage"] == "synthesize"
    assert ws.sent_bytes == []


async def test_disconnect_mid_processing_cleans_up() -> None:
    provider = FakeProvider()
    provider.block = asyncio.Event()
    manager, _, store, _log = make_manager(provider)
    ws = FakeWebSocket([{"bytes": b"a"}])
    await manager.handle(ws, "t1")  # type: ignore[arg-type]
    assert store.count() == 0


async def test_disconnect_idle_cleans_up() -> None:
    manager, _, store, _log = make_manager()
    ws = FakeWebSocket([])
    await manager.handle(ws, "t1")  # type: ignore[arg-type]
    assert store.count() == 0
    assert ws.accepted


async def test_unknown_tenant_closes_with_4403() -> None:
    manager, _, store, log = make_manager()
    ws = FakeWebSocket([{"bytes": b"a"}])
    await manager.handle(ws, "ghost")  # type: ignore[arg-type]
    assert ws.closed_code == 4403
    assert store.count() == 0
    assert log.count() == 0


async def test_completed_call_is_logged() -> None:
    manager, _, _, log = make_manager()
    ws = FakeWebSocket([{"bytes": b"\x01\x02\x03"}, {"text": '{"type": "end"}'}])
    await manager.handle(ws, "t1")  # type: ignore[arg-type]
    assert log.count() == 1
    record = log.list_recent()[0]
    assert (record.tenant, record.frames_received, record.errors) == ("t1", 1, 0)
    assert record.transcript_chars == len("heard-3")
    assert not record.escalated


async def test_escalated_call_is_flagged_in_log() -> None:
    manager, _, _, log = make_manager(escalated_reply=True)
    ws = FakeWebSocket([{"bytes": b"\x01"}, {"text": '{"type": "end"}'}])
    await manager.handle(ws, "t1")  # type: ignore[arg-type]
    assert log.list_recent()[0].escalated


async def test_end_waits_for_inflight_frame() -> None:
    provider = FakeProvider()
    provider.block = asyncio.Event()
    manager, _, _, _ = make_manager(provider)
    ws = FakeWebSocket([{"bytes": b"a"}, {"text": '{"type": "end"}'}])

    async def releaser() -> None:
        await asyncio.sleep(0.05)
        assert provider.block is not None
        provider.block.set()

    await asyncio.gather(manager.handle(ws, "t1"), releaser())  # type: ignore[arg-type]
    summary = ws.sent_json[-1]
    assert summary["type"] == "summary"
    assert summary["transcript"] == "heard-1"


def test_real_transport_smoke() -> None:
    provider = FakeProvider()
    app = create_app(provider=provider)  # type: ignore[arg-type]
    client = TestClient(app)
    with client.websocket_connect("/v1/calls/stream?tenant=demo-nbfc") as ws:
        ws.send_bytes(b"\x01\x02")
        first = ws.receive_json()
        assert first["type"] == "reply"
        assert "heard-2" in first["text"]
        assert ws.receive_bytes() == b"audio:" + first["text"].encode()
        ws.send_text('{"type": "end"}')
        summary = ws.receive_json()
        assert summary["type"] == "summary"
        assert summary["frames_received"] == 1
