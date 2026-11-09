"""Per-call session registry. In-memory now; Redis backing lands with Unit 6."""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field


@dataclass
class CallSession:
    call_id: str
    tenant: str
    frames_received: int = 0
    frames_dropped: int = 0
    errors: int = 0
    transcript_parts: list[str] = field(default_factory=list)
    busy: bool = False
    task: asyncio.Task[None] | None = None
    next_sequence: int = 1


class SessionStore:
    """Registry interface; Unit 6 adds the Redis implementation."""

    def create(self, tenant: str) -> CallSession:
        raise NotImplementedError

    def get(self, call_id: str) -> CallSession | None:
        raise NotImplementedError

    def remove(self, call_id: str) -> None:
        raise NotImplementedError

    def count(self) -> int:
        raise NotImplementedError


class InMemorySessionStore(SessionStore):
    def __init__(self) -> None:
        self._sessions: dict[str, CallSession] = {}

    def create(self, tenant: str) -> CallSession:
        session = CallSession(call_id=uuid.uuid4().hex, tenant=tenant)
        self._sessions[session.call_id] = session
        return session

    def get(self, call_id: str) -> CallSession | None:
        return self._sessions.get(call_id)

    def remove(self, call_id: str) -> None:
        self._sessions.pop(call_id, None)

    def count(self) -> int:
        return len(self._sessions)
