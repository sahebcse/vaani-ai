"""Contract: mock Sarvam shapes pinned to the documented API surface.

If Sarvam's documented field names change, these tests fail first — only the
mock + contract change, never the app (the app only depends on SpeechProvider).
Documented surface (mock implements exactly this):
  POST /speech-to-text  (multipart: audio=file, language_hint=form)
    -> {text, language, confidence, language_hint}
  POST /text-to-speech  ({text, language, voice?})
    -> {audio_base64, content_type, language}
  POST /translate       ({text, source_language, target_language})
    -> {text, passthrough}
"""

import importlib.util
from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient


def load_mock_app() -> Any:
    path = Path(__file__).resolve().parents[2] / "mock-sarvam" / "app.py"
    spec = importlib.util.spec_from_file_location("mock_sarvam_contract", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def client() -> TestClient:
    return TestClient(load_mock_app().app)


def test_stt_contract_shape() -> None:
    body = (
        client()
        .post(
            "/speech-to-text",
            files={"audio": ("clip.wav", b"\x00\x01x", "audio/wav")},
            data={"language_hint": "hi"},
        )
        .json()
    )
    assert set(body) == {"text", "language", "confidence", "language_hint"}


def test_tts_contract_shape() -> None:
    body = client().post("/text-to-speech", json={"text": "x", "language": "hi"}).json()
    assert set(body) == {"audio_base64", "content_type", "language"}


def test_translate_contract_shape() -> None:
    body = (
        client()
        .post(
            "/translate",
            json={"text": "x", "source_language": "hi", "target_language": "en"},
        )
        .json()
    )
    assert set(body) == {"text", "passthrough"}
