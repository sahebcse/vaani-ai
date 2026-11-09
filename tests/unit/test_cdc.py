"""Unit tests for the CDC relay (Kafka/Postgres faked; no Docker)."""

from typing import Any

import pytest

from vaani.cdc import CallEvent, EventPublisher, RelayService, WarehouseLoader
from vaani.ledger import CallRecord


def record(call_id: str = "c1") -> CallRecord:
    return CallRecord(
        call_id=call_id,
        tenant="t1",
        frames_received=2,
        frames_dropped=0,
        errors=0,
        transcript_chars=9,
        escalated=False,
    )


def test_event_roundtrip() -> None:
    event = CallEvent.from_record(record("c9"))
    assert event.call_id == "c9"
    restored = CallEvent.from_json(event.to_json())
    assert restored == event


def test_from_json_rejects_garbage() -> None:
    with pytest.raises((ValueError, KeyError)):
        CallEvent.from_json("not json")
    with pytest.raises(KeyError):
        CallEvent.from_json('{"call_id": "x"}')


class FakeProducer:
    def __init__(self, fail: bool = False) -> None:
        self.sent: list[tuple[str, bytes]] = []
        self.starts = 0
        self.stops = 0
        self.fail = fail

    async def start(self) -> None:
        self.starts += 1

    async def stop(self) -> None:
        self.stops += 1

    async def send_and_wait(self, topic: str, data: bytes) -> None:
        if self.fail:
            raise RuntimeError("broker down")
        self.sent.append((topic, data))


def publisher(fake: FakeProducer) -> EventPublisher:
    return EventPublisher("dummy:9092", "vaani.call-events", producer_factory=lambda: fake)


async def test_publish_sends_event() -> None:
    fake = FakeProducer()
    pub = publisher(fake)
    await pub.publish(CallEvent.from_record(record("c1")))
    assert fake.starts == 1
    assert fake.sent[0][0] == "vaani.call-events"


async def test_publish_reuses_started_producer() -> None:
    fake = FakeProducer()
    pub = publisher(fake)
    await pub.start()
    await pub.start()
    assert fake.starts == 1
    await pub.stop()
    await pub.stop()
    assert fake.stops == 1


async def test_publish_failure_propagates() -> None:
    pub = publisher(FakeProducer(fail=True))
    with pytest.raises(RuntimeError, match="broker down"):
        await pub.publish(CallEvent.from_record(record("c1")))


class FakeConn:
    def __init__(self, fail_on: str = "") -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.closed = False
        self.fail_on = fail_on

    async def execute(self, sql: str, *args: Any) -> str:
        if self.fail_on and self.fail_on in sql:
            raise RuntimeError("db down")
        self.statements.append((sql, args))
        return "OK"

    async def close(self) -> None:
        self.closed = True


async def test_ensure_table_runs_ddl() -> None:
    conn = FakeConn()
    loader = WarehouseLoader("dsn", connect=lambda dsn: _coro(conn))
    await loader.ensure_table()
    assert any("CREATE TABLE" in sql for sql, _ in conn.statements)
    assert conn.closed


async def test_load_inserts_and_counts() -> None:
    conn = FakeConn()
    loader = WarehouseLoader("dsn", connect=lambda dsn: _coro(conn))
    event = CallEvent.from_record(record("c1"))
    assert await loader.load([event]) == 1
    assert await loader.load([]) == 0
    sql, args = conn.statements[0]
    assert "INSERT INTO call_warehouse" in sql
    assert args[0] == "c1"
    assert conn.closed


async def _coro(value: FakeConn) -> FakeConn:
    return value


async def test_default_connect_uses_asyncpg(monkeypatch: pytest.MonkeyPatch) -> None:
    import asyncpg

    conn = FakeConn()
    seen: list[str] = []

    async def fake_connect(dsn: str) -> FakeConn:
        seen.append(dsn)
        return conn

    monkeypatch.setattr(asyncpg, "connect", fake_connect)
    loader = WarehouseLoader("dsn://x")
    await loader.ensure_table()
    assert seen == ["dsn://x"]


async def test_load_failure_still_closes() -> None:
    conn = FakeConn(fail_on="INSERT")
    loader = WarehouseLoader("dsn", connect=lambda dsn: _coro(conn))
    with pytest.raises(RuntimeError, match="db down"):
        await loader.load([CallEvent.from_record(record("c1"))])
    assert conn.closed


async def test_drain_loads_good_and_skips_poison() -> None:
    conn = FakeConn()
    relay = RelayService(WarehouseLoader("dsn", connect=lambda dsn: _coro(conn)))
    good = CallEvent.from_record(record("c1")).to_json().encode()
    loaded, skipped = await relay.drain([good, b"not-json", b'{"a": 1}'])
    assert (loaded, skipped) == (1, 2)
