"""WebSocket call loop: audio frames in, synthesized audio out.

Backpressure: one in-flight frame per call. A frame arriving while the
previous one is still being processed is dropped and counted (coalescing —
the standard choice for live audio, where stale frames are worthless).
The summary reports received/dropped/errors so drops are always visible.
Unit 4+: frames are answered by the LangGraph agent (was echo in Unit 3).
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import time
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from vaani.agent import AgentRunner
from vaani.cdc import CallEvent, EventPublisher
from vaani.ledger import CallLog, CallRecord
from vaani.logging import bind
from vaani.metrics import metrics
from vaani.sessions import CallSession, SessionStore
from vaani.speech import SarvamError, SpeechProvider
from vaani.tenancy import TenantStore

logger = logging.getLogger("vaani.calls")

router = APIRouter()


@router.websocket("/v1/calls/stream")
async def call_stream(websocket: WebSocket) -> None:
    manager: CallManager = websocket.app.state.call_manager
    tenant = websocket.query_params.get("tenant", "demo-nbfc")
    await manager.handle(websocket, tenant)


class CallManager:
    def __init__(
        self,
        provider: SpeechProvider,
        sessions: SessionStore,
        agent: AgentRunner,
        tenants: TenantStore,
        call_log: CallLog,
        events: EventPublisher | None = None,
    ) -> None:
        self._provider = provider
        self._sessions = sessions
        self._agent = agent
        self._tenants = tenants
        self._call_log = call_log
        self._events = events

    async def handle(self, websocket: WebSocket, tenant: str) -> None:
        await websocket.accept()
        if self._tenants.get(tenant) is None:
            await websocket.close(code=4403)
            return
        session = self._sessions.create(tenant)
        metrics.record_call_start()
        logger.info("call started", extra=bind(session.call_id, tenant=tenant))
        try:
            while True:
                try:
                    message = await websocket.receive()
                except WebSocketDisconnect:
                    break
                if message.get("bytes") is not None:
                    await self._on_audio(session, websocket, message["bytes"])
                else:
                    text = message.get("text") or ""
                    done = await self._on_control(session, websocket, text)
                    if done:
                        break
        finally:
            record = CallRecord(
                call_id=session.call_id,
                tenant=session.tenant,
                frames_received=session.frames_received,
                frames_dropped=session.frames_dropped,
                errors=session.errors,
                transcript_chars=sum(len(p) for p in session.transcript_parts),
                escalated=session.escalated,
            )
            self._call_log.append(record)
            if self._events is not None:
                try:
                    await self._events.publish(CallEvent.from_record(record))
                except Exception as exc:
                    logger.warning(
                        "event publish failed", extra=bind(session.call_id, error=str(exc))
                    )
            metrics.record_call_end()
            logger.info("call ended", extra=bind(session.call_id, tenant=session.tenant))
            await self._cleanup(session)

    async def _on_audio(self, session: CallSession, websocket: WebSocket, data: bytes) -> None:
        session.frames_received += 1
        metrics.record_frame()
        if session.busy:
            session.frames_dropped += 1
            metrics.record_drop()
            await websocket.send_json({"type": "dropped", "sequence": session.next_sequence})
            session.next_sequence += 1
            return
        sequence = session.next_sequence
        session.next_sequence += 1
        session.busy = True
        session.task = asyncio.create_task(self._process_frame(session, websocket, data, sequence))
        session.task.add_done_callback(lambda _: setattr(session, "busy", False))

    async def _process_frame(
        self, session: CallSession, websocket: WebSocket, data: bytes, sequence: int
    ) -> None:
        start = time.monotonic()
        try:
            transcript = await self._provider.atranscribe(data)
        except SarvamError as exc:
            session.errors += 1
            metrics.record_error("transcribe")
            logger.warning("transcribe failed", extra=bind(session.call_id, error=str(exc)))
            await websocket.send_json({"type": "error", "stage": "transcribe", "detail": str(exc)})
            return
        metrics.observe_transcribe(time.monotonic() - start)
        session.transcript_parts.append(transcript.text)
        started = time.monotonic()
        reply = await self._agent.run(transcript.text, transcript.language, session.tenant)
        metrics.observe_agent(time.monotonic() - started)
        if reply.escalated:
            session.escalated = True
        try:
            audio = await self._provider.asynthesize(reply.text, transcript.language)
        except SarvamError as exc:
            session.errors += 1
            metrics.record_error("synthesize")
            await websocket.send_json({"type": "error", "stage": "synthesize", "detail": str(exc)})
            return
        await websocket.send_json(
            {
                "type": "reply",
                "sequence": sequence,
                "text": reply.text,
                "citations": reply.citations,
            }
        )
        await websocket.send_bytes(audio.data)

    async def _on_control(self, session: CallSession, websocket: WebSocket, text: str) -> bool:
        try:
            control: dict[str, Any] = json.loads(text)
        except ValueError:
            await websocket.send_json({"type": "error", "stage": "control"})
            return False
        if control.get("type") != "end":
            await websocket.send_json({"type": "error", "stage": "control"})
            return False
        if session.task is not None and not session.task.done():
            await session.task
        await websocket.send_json(
            {
                "type": "summary",
                "frames_received": session.frames_received,
                "frames_dropped": session.frames_dropped,
                "errors": session.errors,
                "transcript": " ".join(session.transcript_parts),
            }
        )
        return True

    async def _cleanup(self, session: CallSession) -> None:
        if session.task is not None and not session.task.done():
            session.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await session.task
        self._sessions.remove(session.call_id)
