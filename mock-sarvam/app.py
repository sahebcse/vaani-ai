"""Mock Sarvam server: Sarvam-compatible STT/TTS/translate over fixtures.

Deterministic: SHA-256(audio bytes) -> canned transcript. Unknown audio
falls back to the default fixture (never an error — keeps e2e stable).
Latency knob: MOCK_LATENCY_MS (slept per request, keeps timing tests stable).
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import math
import os
import struct
import wave
from io import BytesIO
from typing import Any

from fastapi import FastAPI, File, Form
from pydantic import BaseModel

app = FastAPI(title="Mock Sarvam")

_MANIFEST_PATH = os.getenv(
    "FIXTURE_MANIFEST",
    os.path.join(os.path.dirname(__file__), "..", "fixtures", "audio", "manifest.json"),
)
_TRANSLATIONS_PATH = os.getenv(
    "TRANSLATIONS_FILE",
    os.path.join(os.path.dirname(__file__), "..", "fixtures", "audio", "translations.json"),
)


def _load_json(path: str) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data: dict[str, Any] = json.load(fh)
            return data
    except (OSError, ValueError):
        return {}


def _latency_ms() -> int:
    try:
        return max(0, int(os.getenv("MOCK_LATENCY_MS", "0")))
    except ValueError:
        return 0


async def _maybe_delay() -> None:
    ms = _latency_ms()
    if ms > 0:
        await asyncio.sleep(ms / 1000.0)


def _manifest() -> dict[str, Any]:
    return _load_json(_MANIFEST_PATH)


def _translations() -> dict[str, Any]:
    return _load_json(_TRANSLATIONS_PATH)


def synth_wav(seed_text: str, seconds: float = 0.5) -> bytes:
    """Deterministic WAV for a text (freq derived from its hash)."""
    digest = hashlib.sha256(seed_text.encode("utf-8")).digest()
    freq = 220.0 + (digest[0] / 255.0) * 440.0
    rate = 8000
    frames = int(rate * seconds)
    buf = BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for i in range(frames):
            sample = int(12000 * math.sin(2 * math.pi * freq * i / rate))
            wav.writeframes(struct.pack("<h", sample))
    return buf.getvalue()


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {"status": "ok", "service": "mock-sarvam"}


@app.post("/speech-to-text")
async def speech_to_text(
    audio: bytes = File(),
    language_hint: str = Form(default="auto"),
) -> dict[str, object]:
    await _maybe_delay()
    manifest = _manifest()
    digest = hashlib.sha256(audio).hexdigest()
    entry = manifest.get(digest, manifest.get("default", {}))
    return {
        "text": entry.get("text", ""),
        "language": entry.get("language", "hi"),
        "confidence": entry.get("confidence", 0.99),
        "language_hint": language_hint,
    }


class TTSRequest(BaseModel):
    text: str
    language: str = "hi"
    voice: str | None = None


@app.post("/text-to-speech")
async def text_to_speech(req: TTSRequest) -> dict[str, object]:
    await _maybe_delay()
    audio = synth_wav(req.text)
    return {
        "audio_base64": base64.b64encode(audio).decode("ascii"),
        "content_type": "audio/wav",
        "language": req.language,
    }


class TranslateRequest(BaseModel):
    text: str
    source_language: str
    target_language: str


@app.post("/translate")
async def translate(req: TranslateRequest) -> dict[str, object]:
    await _maybe_delay()
    table = _translations()
    key = f"{req.source_language}:{req.target_language}:{req.text}"
    if key in table:
        return {"text": table[key], "passthrough": False}
    return {"text": req.text, "passthrough": True}


@app.post("/reload")
def reload_fixtures() -> dict[str, object]:
    loaded = len(_manifest())
    return {"status": "ok", "entries": loaded}
