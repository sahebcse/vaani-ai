import os

from fastapi.testclient import TestClient

from vaani import __version__
from vaani.config import Settings, get_settings
from vaani.main import create_app


def test_version_pinned():
    assert __version__ == "0.1.0"


def test_health_endpoint():
    client = TestClient(create_app())
    resp = client.get("/healthz")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok", "app": "vaani", "version": "0.1.0"}


def test_settings_defaults():
    s = Settings()
    assert s.postgres_dsn.startswith("postgresql://")
    assert s.redis_url.startswith("redis://")
    assert s.sarvam_base_url.startswith("http")
    assert s.sarvam_timeout_seconds > 0
    assert 0.0 <= s.eval_score_threshold <= 1.0


def test_settings_env_override(monkeypatch):
    monkeypatch.setenv("VAANI_LOG_LEVEL", "DEBUG")
    monkeypatch.setenv("VAANI_SARVAM_TIMEOUT_SECONDS", "3.5")
    s = Settings()
    assert s.log_level == "DEBUG"
    assert s.sarvam_timeout_seconds == 3.5


def test_get_settings_returns_settings():
    assert isinstance(get_settings(), Settings)
    assert os.getenv("VAANI_APP_NAME", "vaani") == get_settings().app_name
