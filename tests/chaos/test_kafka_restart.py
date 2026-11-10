"""Chaos: Kafka restart mid-stream — no event loss.

Needs Docker. NOT part of the default suite (and outside the 100% gate):
    pytest tests/chaos -q
"""

import uuid

import pytest
from aiokafka import AIOKafkaConsumer
from testcontainers.core.container import DockerContainer

from vaani.cdc import CallEvent, EventPublisher

KAFKA_IMAGE = "apache/kafka:3.7.0"
HOST_PORT = 31992
TOPIC = "vaani.chaos-events"


async def wait_for_kafka(bootstrap: str, timeout_seconds: int = 180) -> None:
    import asyncio
    import contextlib
    import time

    from aiokafka import AIOKafkaConsumer

    deadline = time.monotonic() + timeout_seconds
    last: Exception | None = None
    while time.monotonic() < deadline:
        consumer = AIOKafkaConsumer(
            bootstrap_servers=bootstrap,
            group_id="chaos-probe",
            enable_auto_commit=False,
        )
        try:
            await consumer.start()
        except Exception as exc:  # noqa: BLE001 - readiness probe, any failure retries
            last = exc
            with contextlib.suppress(Exception):
                await consumer.stop()
            await asyncio.sleep(2)
            continue
        try:
            return
        finally:
            await consumer.stop()
    raise AssertionError(f"kafka not ready at {bootstrap}: {last}")


def kafka_container() -> DockerContainer:
    container = DockerContainer(KAFKA_IMAGE)
    container.with_env("KAFKA_NODE_ID", "1")
    container.with_env("KAFKA_PROCESS_ROLES", "broker,controller")
    container.with_env("KAFKA_CONTROLLER_LISTENER_NAMES", "CONTROLLER")
    container.with_env("KAFKA_INTER_BROKER_LISTENER_NAME", "INTERNAL")
    container.with_env(
        "KAFKA_LISTENERS",
        "INTERNAL://0.0.0.0:9092,CONTROLLER://0.0.0.0:9093,EXTERNAL://0.0.0.0:29092",
    )
    container.with_env(
        "KAFKA_ADVERTISED_LISTENERS",
        f"INTERNAL://localhost:9092,EXTERNAL://localhost:{HOST_PORT}",
    )
    container.with_env(
        "KAFKA_LISTENER_SECURITY_PROTOCOL_MAP",
        "INTERNAL:PLAINTEXT,CONTROLLER:PLAINTEXT,EXTERNAL:PLAINTEXT",
    )
    container.with_env("KAFKA_CONTROLLER_QUORUM_VOTERS", "1@localhost:9093")
    container.with_env("KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR", "1")
    container.with_env("KAFKA_TRANSACTION_STATE_LOG_REPLICATION_FACTOR", "1")
    container.with_env("KAFKA_TRANSACTION_STATE_LOG_MIN_ISR", "1")
    container.with_env("CLUSTER_ID", "MkU3OEVBNTcwNTJENDM2Qk")
    container.with_bind_ports(29092, HOST_PORT)
    return container


def event(i: int) -> CallEvent:
    return CallEvent(
        call_id=f"chaos-{i}",
        tenant="t1",
        frames_received=i,
        frames_dropped=0,
        errors=0,
        transcript_chars=1,
        escalated=False,
    )


async def consume_all(bootstrap: str, topic: str, expected: int) -> list[bytes]:
    consumer = AIOKafkaConsumer(
        topic,
        bootstrap_servers=bootstrap,
        group_id=f"chaos-{uuid.uuid4().hex[:8]}",
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await consumer.start()
    raw: list[bytes] = []
    try:
        for _ in range(60):
            batch = await consumer.getmany(timeout_ms=2000, max_records=100)
            for _, messages in batch.items():
                raw.extend(m.value for m in messages)
            if len(raw) >= expected:
                break
    finally:
        await consumer.stop()
    return raw


@pytest.mark.asyncio
async def test_events_survive_kafka_restart() -> None:
    bootstrap = f"localhost:{HOST_PORT}"
    with kafka_container() as kafka:
        await wait_for_kafka(bootstrap)
        publisher = EventPublisher(bootstrap, TOPIC)
        for i in range(3):
            await publisher.publish(event(i))
        kafka.get_wrapped_container().restart(timeout=30)
        await wait_for_kafka(bootstrap)
        for i in range(3, 6):
            await publisher.publish(event(i))
        await publisher.stop()
        raw = await consume_all(bootstrap, TOPIC, 6)
    assert len(raw) == 6
    assert sorted(CallEvent.from_json(m.decode()).call_id for m in raw) == [
        f"chaos-{i}" for i in range(6)
    ]
