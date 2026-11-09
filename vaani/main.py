"""ASGI entrypoint. Routers land here as units merge; keep this file thin."""

import os

from fastapi import FastAPI

from vaani import __version__, calls
from vaani.agent import AgentRunner
from vaani.config import Settings, get_settings
from vaani.llm import MockResponder
from vaani.retrieval import EMBEDDING_DIM, HashEmbedder, OpenSearchRetriever, OpenSearchStore
from vaani.sessions import InMemorySessionStore
from vaani.speech import SarvamProvider, SpeechProvider
from vaani.tools import (
    Account,
    InMemoryAccountStore,
    KeywordRetriever,
    MemoryEscalationSink,
    PolicyDoc,
    Retriever,
)


def _load_policy_docs() -> list[PolicyDoc]:
    here = os.path.dirname(os.path.abspath(__file__))
    base = os.path.join(os.path.dirname(here), "fixtures", "policies")
    docs: list[PolicyDoc] = []
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return docs
    for name in names:
        if not name.endswith(".md") or name == "README.md":
            continue
        with open(os.path.join(base, name), encoding="utf-8") as fh:
            docs.append(PolicyDoc(text=fh.read(), source=name))
    return docs


def _build_retriever(settings: Settings) -> Retriever:
    """OpenSearch hybrid retrieval; keyword fallback for zero-infra runs."""
    if settings.retriever != "opensearch":
        return KeywordRetriever(_load_policy_docs())
    from opensearchpy import OpenSearch

    store = OpenSearchStore(
        OpenSearch(hosts=[settings.opensearch_url]), "vaani-policies", dim=EMBEDDING_DIM
    )
    return OpenSearchRetriever(store, HashEmbedder(), k=3)
    base = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fixtures", "policies"
    )
    docs: list[PolicyDoc] = []
    try:
        names = sorted(os.listdir(base))
    except OSError:
        return docs
    for name in names:
        if not name.endswith(".md") or name == "README.md":
            continue
        with open(os.path.join(base, name), encoding="utf-8") as fh:
            docs.append(PolicyDoc(text=fh.read(), source=name))
    return docs


def _demo_accounts() -> dict[str, Account]:
    return {
        "caller": Account(
            user_id="caller", name="Demo User", balance_due=1250.0, due_date="2026-12-01"
        )
    }


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
    agent = AgentRunner(
        MockResponder(),
        _build_retriever(settings),
        InMemoryAccountStore(_demo_accounts()),
        MemoryEscalationSink(),
    )
    app.state.call_manager = calls.CallManager(active, sessions, agent)
    app.state.default_tenant = tenant or settings.default_tenant
    app.include_router(calls.router)

    @app.get("/healthz")
    def healthz() -> dict[str, object]:
        return {"status": "ok", "app": settings.app_name, "version": __version__}

    return app


app = create_app()
