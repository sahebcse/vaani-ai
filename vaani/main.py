"""ASGI entrypoint. Routers land here as units merge; keep this file thin."""

from fastapi import FastAPI

from vaani import __version__, calls
from vaani.config import Settings, get_settings
from vaani.sessions import InMemorySessionStore
from vaani.speech import SarvamProvider, SpeechProvider


def create_app(
    provider: SpeechProvider | None = None,
    tenant: str | None = None,
) -> FastAPI:
    settings: Settings = get_settings()
    app = FastAPI(title="Vaani", version=__version__)
    sessions = InMemorySessionStore()
    active = provider or SarvamProvider(
        settings.sarvam_base_url,
        settings.sarvam_api_key,
        settings.sarvam_timeout_seconds,
    )
    app.state.call_manager = calls.CallManager(active, sessions)
    app.state.default_tenant = tenant or settings.default_tenant
    app.include_router(calls.router)

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {"status": "ok", "app": settings.app_name, "version": __version__}

    return app


app = create_app()
