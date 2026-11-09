#!/usr/bin/env python3
"""Drain vaani.call-events once: consume, parse, load warehouse, print counts.

Usage: python scripts/relay-once.py [--expect-min N]
Exit 0 only if loaded >= expect-min (default 0).
"""

import argparse
import asyncio
import json
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aiokafka import AIOKafkaConsumer  # noqa: E402

from vaani.cdc import RelayService, WarehouseLoader  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--expect-min", type=int, default=0)
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args()

    bootstrap = os.environ.get("VAANI_KAFKA_BOOTSTRAP_SERVERS", "localhost:29092")
    dsn = os.environ.get("VAANI_POSTGRES_DSN", "postgresql://vaani:vaani@localhost:5432/vaani")
    loader = WarehouseLoader(dsn)
    await loader.ensure_table()
    relay = RelayService(loader)
    group = f"vaani-relay-e2e-{uuid.uuid4().hex[:8]}"
    consumer = AIOKafkaConsumer(
        "vaani.call-events",
        bootstrap_servers=bootstrap,
        group_id=group,
        auto_offset_reset="earliest",
        enable_auto_commit=False,
    )
    await consumer.start()
    raw: list[bytes] = []
    try:
        deadline = asyncio.get_event_loop().time() + args.timeout_seconds
        while asyncio.get_event_loop().time() < deadline:
            batch = await consumer.getmany(timeout_ms=1000, max_records=100)
            for _, messages in batch.items():
                raw.extend(m.value for m in messages)
            if raw:
                break
    finally:
        await consumer.stop()
    loaded, skipped = await relay.drain(raw)
    print(json.dumps({"loaded": loaded, "skipped": skipped}))
    return 0 if loaded >= args.expect_min else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
