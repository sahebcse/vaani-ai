"""Unit tests for SpeechProvider / SarvamProvider (HTTP mocked via respx)."""

import base64

import httpx
import pytest
import respx

from vaani.speech import SarvamError, SarvamProvider, SpeechProvider

BASE = "http://mock:8001"


def provider() -> SarvamProvider:
    return SarvamProvider(BASE, "key", timeout_seconds=5.0, max_retries=2)


def test_base_url_trailing_slash_stripped() -> None:
    p = SarvamProvider(BASE + "/", "key")
    assert p._base_url == BASE


async def test_transcribe_success() -> None:
    async with respx.mock:
        route = respx.post(f"{BASE}/speech-to-text").mock(
            return_value=httpx.Response(
                200, json={"text": "hello", "language": "en", "confidence": 0.9}
            )
        )
        out = await provider().atranscribe(b"wav-bytes", language_hint="en")
    assert route.called
    assert (out.text, out.language, out.confidence) == ("hello", "en", 0.9)


async def test_transcribe_default_confidence_and_hint() -> None:
    async with respx.mock:
        respx.post(f"{BASE}/speech-to-text").mock(
            return_value=httpx.Response(200, json={"text": "x", "language": "hi"})
        )
        out = await provider().atranscribe(b"wav-bytes")
    assert out.confidence == 1.0


async def test_transcribe_retries_then_succeeds() -> None:
    async with respx.mock:
        route = respx.post(f"{BASE}/speech-to-text").mock(
            side_effect=[
                httpx.Response(500, json={}),
                httpx.Response(200, json={"text": "ok", "language": "hi"}),
            ]
        )
        out = await provider().atranscribe(b"wav-bytes")
    assert route.call_count == 2
    assert out.text == "ok"


async def test_transcribe_4xx_raises_without_retry() -> None:
    async with respx.mock:
        route = respx.post(f"{BASE}/speech-to-text").mock(return_value=httpx.Response(400, json={}))
        with pytest.raises(SarvamError, match="rejected"):
            await provider().atranscribe(b"wav-bytes")
    assert route.call_count == 1


async def test_transcribe_5xx_always_raises_after_retries() -> None:
    async with respx.mock:
        route = respx.post(f"{BASE}/speech-to-text").mock(return_value=httpx.Response(503, json={}))
        with pytest.raises(SarvamError, match="after retries"):
            await provider().atranscribe(b"wav-bytes")
    assert route.call_count == 3  # 1 + max_retries(2)


async def test_transcribe_timeout_raises_after_retries() -> None:
    async with respx.mock:
        route = respx.post(f"{BASE}/speech-to-text").mock(side_effect=httpx.ConnectTimeout("down"))
        with pytest.raises(SarvamError, match="after retries"):
            await provider().atranscribe(b"wav-bytes")
    assert route.call_count == 3


async def test_transcribe_reset_mid_stream_becomes_sarvam_error() -> None:
    async with respx.mock:
        route = respx.post(f"{BASE}/speech-to-text").mock(
            side_effect=httpx.RemoteProtocolError("peer closed connection without response")
        )
        with pytest.raises(SarvamError, match="after retries"):
            await provider().atranscribe(b"wav-bytes")
    assert route.call_count == 3


async def test_translate_read_error_becomes_sarvam_error() -> None:
    async with respx.mock:
        route = respx.post(f"{BASE}/translate").mock(side_effect=httpx.ReadError("reset"))
        with pytest.raises(SarvamError, match="after retries"):
            await provider().atranslate("x", "en", "hi")
    assert route.call_count == 3


async def test_synthesize_maps_audio() -> None:
    raw = b"RIFF....fake-wav"
    async with respx.mock:
        respx.post(f"{BASE}/text-to-speech").mock(
            return_value=httpx.Response(
                200,
                json={
                    "audio_base64": base64.b64encode(raw).decode("ascii"),
                    "content_type": "audio/wav",
                },
            )
        )
        out = await provider().asynthesize("hello", "en", voice="v1")
    assert out.data == raw
    assert out.content_type == "audio/wav"


async def test_synthesize_default_content_type_and_no_voice() -> None:
    raw = b"RIFF....fake-wav"
    async with respx.mock:
        route = respx.post(f"{BASE}/text-to-speech").mock(
            return_value=httpx.Response(
                200, json={"audio_base64": base64.b64encode(raw).decode("ascii")}
            )
        )
        out = await provider().asynthesize("hello", "en")
    assert route.called
    assert out.content_type == "audio/wav"


async def test_translate_maps_fields() -> None:
    async with respx.mock:
        respx.post(f"{BASE}/translate").mock(
            return_value=httpx.Response(200, json={"text": "hola"})
        )
        out = await provider().atranslate("hello", "en", "es")
    assert out.text == "hola"
    assert (out.source_language, out.target_language) == ("en", "es")


async def test_json_path_4xx_raises_without_retry() -> None:
    async with respx.mock:
        route = respx.post(f"{BASE}/translate").mock(return_value=httpx.Response(422, json={}))
        with pytest.raises(SarvamError, match="rejected"):
            await provider().atranslate("x", "en", "hi")
    assert route.call_count == 1


async def test_provider_is_abstract() -> None:
    with pytest.raises(TypeError):
        SpeechProvider()  # type: ignore[abstract]
