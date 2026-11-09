"""CDC-style relay: call-completion events -> Kafka -> warehouse table.

Production swap: Debezium log-based CDC (sample connector in
docs/debezium-connector.json). The mechanism here — capture, stream, load —
is identical; only the capture source changes.
"""

from __future__ import annotations

import json
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from typing import Any

from vaani.ledger import CallRecord


@dataclass(frozen=True)
class CallEvent:
    call_id: str
    tenant: str
    frames_received: int
    frames_dropped: int
    errors: int
    transcript_chars: int
    escalated: bool

    @staticmethod
    def from_record(record: CallRecord) -> CallEvent:
        return CallEvent(
            call_id=record.call_id,
            tenant=record.tenant,
            frames_received=record.frames_received,
            frames_dropped=record.frames_dropped,
            errors=record.errors,
            transcript_chars=record.transcript_chars,
            escalated=record.escalated,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @staticmethod
    def from_json(raw: str) -> CallEvent:
        data = json.loads(raw)
        return CallEvent(
            call_id=str(data["call_id"]),
            tenant=str(data["tenant"]),
            frames_received=int(data["frames_received"]),
            frames_dropped=int(data["frames_dropped"]),
            errors=int(data["errors"]),
            transcript_chars=int(data["transcript_chars"]),
            escalated=bool(data["escalated"]),
        )


class EventPublisher:
    def __init__(
        self,
        bootstrap_servers: str,
        topic: str,
        producer_factory: Callable[[], Any] | None = None,
    ) -> None:
        from aiokafka import AIOKafkaProducer

        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._factory = producer_factory or (
            lambda: AIOKafkaProducer(bootstrap_servers=bootstrap_servers)
        )
        self._producer: Any = None

    async def start(self) -> None:
        if self._producer is None:
            self._producer = self._factory()
            await self._producer.start()

    async def stop(self) -> None:
        if self._producer is not None:
            await self._producer.stop()
            self._producer = None

    async def publish(self, event: CallEvent) -> None:
        producer = self._producer
        if producer is None:
            await self.start()
            producer = self._producer
        assert producer is not None
        await producer.send_and_wait(self._topic, event.to_json().encode())


ConnectFactory = Callable[[str], Awaitable[Any]]


class WarehouseLoader:
    """Loads call events into the analytics table (Postgres)."""

    def __init__(self, dsn: str, connect: ConnectFactory | None = None) -> None:
        self._dsn = dsn
        self._connect = connect

    async def _connection(self) -> Any:
        if self._connect is not None:
            return await self._connect(self._dsn)
        import asyncpg

        return await asyncpg.connect(self._dsn)

    async def ensure_table(self) -> None:
        conn = await self._connection()
        try:
            await conn.execute(
                "CREATE TABLE IF NOT EXISTS call_warehouse ("
                "call_id TEXT PRIMARY KEY, tenant TEXT NOT NULL, "
                "frames_received INT NOT NULL, frames_dropped INT NOT NULL, "
                "errors INT NOT NULL, transcript_chars INT NOT NULL, "
                "escalated BOOLEAN NOT NULL)"
            )
        finally:
            await conn.close()

    async def load(self, events: list[CallEvent]) -> int:
        if not events:
            return 0
        conn = await self._connection()
        try:
            for event in events:
                await conn.execute(
                    "INSERT INTO call_warehouse "
                    "(call_id, tenant, frames_received, frames_dropped, "
                    "errors, transcript_chars, escalated) "
                    "VALUES ($1, $2, $3, $4, $5, $6, $7) "
                    "ON CONFLICT (call_id) DO NOTHING",
                    event.call_id,
                    event.tenant,
                    event.frames_received,
                    event.frames_dropped,
                    event.errors,
                    event.transcript_chars,
                    event.escalated,
                )
        finally:
            await conn.close()
        return len(events)


class RelayService:
    """Parse raw Kafka records, skip poison, load the rest."""

    def __init__(self, loader: WarehouseLoader) -> None:
        self._loader = loader

    async def drain(self, raw_messages: list[bytes]) -> tuple[int, int]:
        events: list[CallEvent] = []
        skipped = 0
        for raw in raw_messages:
            try:
                events.append(CallEvent.from_json(raw.decode("utf-8")))
            except (ValueError, KeyError, AttributeError, TypeError):
                skipped += 1
        loaded = await self._loader.load(events)
        return loaded, skipped
