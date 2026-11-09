#!/usr/bin/env python3
"""Unit 3 demo: stream a fixture WAV over the call WebSocket, assert echo.

Usage: BASE_URL=http://localhost:8080 python scripts/call_demo.py
"""

import asyncio
import hashlib
import json
import os
import sys

import websockets

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8080")
WS_URL = BASE_URL.replace("http", "ws") + "/v1/calls/stream?tenant=demo-nbfc"
FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "fixtures", "audio")


async def main() -> int:
    with open(os.path.join(FIXTURE, "manifest.json"), encoding="utf-8") as fh:
        manifest = json.load(fh)
    path = os.path.join(FIXTURE, "hindi-collection.wav")
    with open(path, "rb") as fh:
        audio = fh.read()
    digest = hashlib.sha256(audio).hexdigest()
    expected_text: str = manifest[digest]["text"]

    async with websockets.connect(WS_URL, max_size=10_000_000) as ws:
        # Single frame: the mock maps SHA-256(full file) -> fixture transcript,
        # so chunking would break determinism. Chunked delivery is covered by
        # unit tests (fake provider); here we prove the full loop end-to-end.
        await ws.send(audio)
        first = json.loads(await ws.recv())
        assert first["type"] == "reply", first
        assert first["text"], "reply must not be empty"
        assert first["citations"], "reply must cite a policy doc"
        raw = await ws.recv()
        assert isinstance(raw, bytes) and len(raw) > 44, "expected WAV bytes"
        await ws.send(json.dumps({"type": "end"}))
        summary = json.loads(await ws.recv())
        assert summary["type"] == "summary", summary
        assert summary["frames_received"] >= 1
        assert expected_text in summary["transcript"], summary
        print("demo call ok:", summary["frames_received"], "frames")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
