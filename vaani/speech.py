"""Speech provider abstraction.

All Sarvam calls (real or mocked) go through :class:`SpeechProvider`, so the
app never knows which backend serves it. Unit 3+ builds on this interface.
"""

from __future__ import annotations

import asyncio
import base64
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

import httpx


@dataclass(frozen=True)
class Transcript:
    text: str
    language: str
    confidence: float


@dataclass(frozen=True)
class SpeechAudio:
    data: bytes
    content_type: str


@dataclass(frozen=True)
class Translation:
    text: str
    source_language: str
    target_language: str


class SarvamError(Exception):
    """Raised when the speech backend fails irrecoverably."""


class SpeechProvider(ABC):
    """Transcribe / synthesize / translate. Implementations: Sarvam, mock."""

    @abstractmethod
    async def atranscribe(self, audio: bytes, language_hint: str | None = None) -> Transcript: ...

    @abstractmethod
    async def asynthesize(
        self, text: str, language: str, voice: str | None = None
    ) -> SpeechAudio: ...

    @abstractmethod
    async def atranslate(
        self, text: str, source_language: str, target_language: str
    ) -> Translation: ...


class SarvamProvider(SpeechProvider):
    """HTTP client for Sarvam AI (or the local mock — same shapes)."""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        timeout_seconds: float = 10.0,
        max_retries: int = 3,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout_seconds
        self._max_retries = max_retries

    async def _send(
        self,
        path: str,
        json_body: dict[str, Any] | None = None,
        audio: bytes | None = None,
        form: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                async with httpx.AsyncClient() as client:
                    if audio is not None:
                        resp = await client.post(
                            self._base_url + path,
                            files={"audio": ("clip.wav", audio, "audio/wav")},
                            data=form or {},
                            headers=self._auth(),
                            timeout=self._timeout,
                        )
                    else:
                        resp = await client.post(
                            self._base_url + path,
                            json=json_body or {},
                            headers=self._auth(),
                            timeout=self._timeout,
                        )
            except httpx.HTTPError as exc:
                # Any transport failure (timeout, refused, reset mid-stream,
                # truncated response) is a provider failure, never a crash.
                last_error = exc
            else:
                if resp.status_code < 400:
                    payload: dict[str, Any] = resp.json()
                    return payload
                if resp.status_code < 500:
                    raise SarvamError(f"{path} rejected: {resp.status_code}")
                last_error = SarvamError(f"{path} failed: {resp.status_code}")
            if attempt < self._max_retries:
                await asyncio.sleep(0.05 * (2**attempt))
        raise SarvamError(f"{path} failed after retries: {last_error}")

    def _auth(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self._api_key}"}

    async def atranscribe(self, audio: bytes, language_hint: str | None = None) -> Transcript:
        data = await self._send(
            "/speech-to-text", audio=audio, form={"language_hint": language_hint or "auto"}
        )
        return Transcript(
            text=str(data["text"]),
            language=str(data["language"]),
            confidence=float(data.get("confidence", 1.0)),
        )

    async def asynthesize(self, text: str, language: str, voice: str | None = None) -> SpeechAudio:
        payload: dict[str, Any] = {"text": text, "language": language}
        if voice is not None:
            payload["voice"] = voice
        data = await self._send("/text-to-speech", json_body=payload)
        return SpeechAudio(
            data=base64.b64decode(str(data["audio_base64"])),
            content_type=str(data.get("content_type", "audio/wav")),
        )

    async def atranslate(
        self, text: str, source_language: str, target_language: str
    ) -> Translation:
        data = await self._send(
            "/translate",
            json_body={
                "text": text,
                "source_language": source_language,
                "target_language": target_language,
            },
        )
        return Translation(
            text=str(data["text"]),
            source_language=source_language,
            target_language=target_language,
        )
