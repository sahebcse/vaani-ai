"""Chaos: mock-sarvam dies mid-call — error frame + clean summary, no hang.

Builds the mock image once per session, starts it with a 3s latency knob,
kills it while a transcription is in flight, and asserts the call degrades
gracefully instead of hanging.

Needs Docker. NOT part of the default suite:
    pytest tests/chaos -q
"""

import subprocess
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from testcontainers.core.container import DockerContainer

from vaani.main import create_app
from vaani.speech import SarvamProvider

REPO_ROOT = Path(__file__).resolve().parents[2]
IMAGE_TAG = "vaani-mock-sarvam:chaos"


@pytest.fixture(scope="module")
def mock_image() -> Iterator[str]:
    subprocess.run(
        ["docker", "build", "-t", IMAGE_TAG, "-f", "mock-sarvam/Dockerfile", "."],
        cwd=str(REPO_ROOT),
        check=True,
        capture_output=True,
        timeout=600,
    )
    yield IMAGE_TAG
    subprocess.run(
        ["docker", "rmi", "-f", IMAGE_TAG],
        capture_output=True,
        timeout=300,
    )


@pytest.mark.asyncio
async def test_call_survives_provider_death(mock_image: str) -> None:
    container = DockerContainer(mock_image)
    container.with_exposed_ports(8001)
    container.with_env("MOCK_LATENCY_MS", "3000")
    with container:
        host_port = int(container.get_exposed_port(8001))
        provider = SarvamProvider(f"http://127.0.0.1:{host_port}", "k", timeout_seconds=20.0)
        app = create_app(provider=provider)
        client = TestClient(app)
        with client.websocket_connect("/v1/calls/stream?tenant=demo-nbfc") as ws:
            ws.send_bytes(b"\x01\x02\x03")

            def killer() -> None:
                time.sleep(0.5)
                container.stop()

            thread = threading.Thread(target=killer, daemon=True)
            thread.start()
            first = ws.receive_json()
            assert first["type"] == "error", first
            assert first["stage"] == "transcribe"
            ws.send_text('{"type": "end"}')
            summary = ws.receive_json()
            assert summary["type"] == "summary"
            assert summary["errors"] >= 1
            thread.join(timeout=30)
