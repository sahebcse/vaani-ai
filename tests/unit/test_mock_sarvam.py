"""Unit tests for the mock Sarvam server (in-process via TestClient)."""

import base64
import hashlib
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


def load_mock_app() -> Any:
    path = Path(__file__).resolve().parents[2] / "mock-sarvam" / "app.py"
    spec = importlib.util.spec_from_file_location("mock_sarvam_app", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def client() -> TestClient:
    app = load_mock_app().app
    return TestClient(app)


def fixture_bytes(name: str) -> bytes:
    path = Path(__file__).resolve().parents[2] / "fixtures" / "audio" / name
    return path.read_bytes()


def test_manifest_matches_wav_files_on_disk() -> None:
    """Guards fixture regeneration drift (sha256(file) must equal manifest key)."""
    import hashlib

    for name in ("hindi-collection.wav", "english-balance.wav", "hindi-greeting.wav"):
        digest = hashlib.sha256(fixture_bytes(name)).hexdigest()
        assert digest in manifest(), name


def manifest() -> dict[str, Any]:
    path = Path(__file__).resolve().parents[2] / "fixtures" / "audio" / "manifest.json"
    raw: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return raw


def test_healthz() -> None:
    resp = client().get("/healthz")
    assert resp.status_code == 200
    assert resp.json()["service"] == "mock-sarvam"


def test_known_audio_returns_fixture_transcript() -> None:
    audio = fixture_bytes("hindi-collection.wav")
    digest = hashlib.sha256(audio).hexdigest()
    expected = manifest()[digest]
    resp = client().post("/speech-to-text", files={"audio": ("clip.wav", audio, "audio/wav")})
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == expected["text"]
    assert body["language"] == expected["language"]
    assert body["confidence"] == expected["confidence"]


def test_unknown_audio_falls_back_to_default() -> None:
    resp = client().post(
        "/speech-to-text",
        files={"audio": ("clip.wav", b"\x00\x01not-a-fixture", "audio/wav")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["text"] == manifest()["default"]["text"]


def test_language_hint_echoed() -> None:
    resp = client().post(
        "/speech-to-text",
        files={"audio": ("clip.wav", b"\x00\x01x", "audio/wav")},
        data={"language_hint": "en"},
    )
    assert resp.json()["language_hint"] == "en"


def test_tts_returns_valid_wav() -> None:
    resp = client().post("/text-to-speech", json={"text": "hello", "language": "en"})
    assert resp.status_code == 200
    raw = base64.b64decode(resp.json()["audio_base64"])
    assert raw[:4] == b"RIFF"
    assert len(raw) > 44
    assert resp.json()["language"] == "en"


def test_tts_deterministic_per_text() -> None:
    c = client()
    first = c.post("/text-to-speech", json={"text": "same", "language": "hi"}).json()
    second = c.post("/text-to-speech", json={"text": "same", "language": "hi"}).json()
    assert first["audio_base64"] == second["audio_base64"]


def test_translate_known_pair() -> None:
    resp = client().post(
        "/translate",
        json={
            "text": "मेरा लोन का पेमेंट बाकी है",
            "source_language": "hi",
            "target_language": "en",
        },
    )
    assert resp.status_code == 200
    assert resp.json() == {"text": "my loan payment is pending", "passthrough": False}


def test_translate_unknown_passthrough() -> None:
    resp = client().post(
        "/translate",
        json={"text": "something new", "source_language": "en", "target_language": "hi"},
    )
    assert resp.json() == {"text": "something new", "passthrough": True}


def test_reload_reports_entries() -> None:
    resp = client().post("/reload")
    assert resp.status_code == 200
    assert resp.json()["entries"] >= 4  # 3 fixtures + default


def test_missing_manifest_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("FIXTURE_MANIFEST", "/nonexistent/manifest.json")
    resp = client().post(
        "/speech-to-text",
        files={"audio": ("clip.wav", b"\x00\x01x", "audio/wav")},
    )
    assert resp.json()["text"] == ""


def test_bad_latency_env_treated_as_zero(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MOCK_LATENCY_MS", "not-a-number")
    resp = client().get("/healthz")
    assert resp.status_code == 200


def test_latency_knob_applies(monkeypatch: pytest.MonkeyPatch) -> None:
    import time

    monkeypatch.setenv("MOCK_LATENCY_MS", "50")
    start = time.monotonic()
    client().post(
        "/speech-to-text",
        files={"audio": ("clip.wav", b"\x00\x01x", "audio/wav")},
    )
    assert (time.monotonic() - start) >= 0.04
