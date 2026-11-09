#!/usr/bin/env python3
"""Generate deterministic fixture WAVs + manifest.json + translations.json.

Each WAV is a 1s 8kHz mono sine at a fixture-specific frequency. The mock
server maps SHA-256(file bytes) -> canned transcript, so e2e is deterministic.
"""

import hashlib
import json
import math
import os
import struct
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO_DIR = os.path.join(HERE, "..", "fixtures", "audio")

FIXTURES = [
    ("hindi-collection.wav", 330.0, "मेरा लोन का पेमेंट बाकी है", "hi"),
    ("english-balance.wav", 440.0, "my account balance is overdue", "en"),
    ("hindi-greeting.wav", 550.0, "नमस्ते, मैं वाणी हूँ", "hi"),
]

TRANSLATIONS = {
    "hi:en:मेरा लोन का पेमेंट बाकी है": "my loan payment is pending",
    "en:hi:my account balance is overdue": "मेरे खाते का बैलेंस बकाया है",
}


def make_wav(path: str, freq: float, seconds: float = 1.0) -> None:
    rate = 8000
    frames = int(rate * seconds)
    with wave.open(path, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        for i in range(frames):
            sample = int(12000 * math.sin(2 * math.pi * freq * i / rate))
            wav.writeframes(struct.pack("<h", sample))


def main() -> None:
    os.makedirs(AUDIO_DIR, exist_ok=True)
    manifest: dict[str, object] = {}
    for name, freq, text, lang in FIXTURES:
        path = os.path.join(AUDIO_DIR, name)
        make_wav(path, freq)
        with open(path, "rb") as fh:
            digest = hashlib.sha256(fh.read()).hexdigest()
        manifest[digest] = {"text": text, "language": lang, "confidence": 0.99}
    first = FIXTURES[0]
    manifest["default"] = {
        "text": first[2],
        "language": first[3],
        "confidence": 0.90,
    }
    with open(os.path.join(AUDIO_DIR, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(AUDIO_DIR, "translations.json"), "w", encoding="utf-8") as fh:
        json.dump(TRANSLATIONS, fh, ensure_ascii=False, indent=1)
    print(f"wrote {len(FIXTURES)} wavs + manifest + translations to {AUDIO_DIR}")


if __name__ == "__main__":
    main()
