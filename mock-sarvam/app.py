"""Mock Sarvam server (Unit 1: health only; full STT/TTS/translate in Unit 2)."""

from fastapi import FastAPI

app = FastAPI(title="Mock Sarvam")


@app.get("/healthz")
def healthz() -> dict[str, object]:
    return {"status": "ok", "service": "mock-sarvam"}
