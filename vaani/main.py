"""ASGI entrypoint. Routers land here as units merge; keep this file thin."""

from fastapi import FastAPI

from vaani import __version__
from vaani.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="Vaani", version=__version__)

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {"status": "ok", "app": settings.app_name, "version": __version__}

    return app


app = create_app()
