"""Unit tests for the admin REST APIs (in-process, no I/O)."""

import pytest
from fastapi.testclient import TestClient

from vaani.main import create_app


@pytest.fixture()
def app_client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("VAANI_ADMIN_KEY", "test-key")
    return TestClient(create_app())


def admin_headers(client: TestClient) -> dict[str, str]:
    resp = client.post(
        "/v1/admin/tokens",
        json={"tenant": "t1", "role": "admin"},
        headers={"X-Admin-Key": "test-key"},
    )
    assert resp.status_code == 200
    return {"Authorization": f"Bearer {resp.json()['token']}"}


def test_tokens_requires_admin_key(app_client: TestClient) -> None:
    resp = app_client.post("/v1/admin/tokens", json={"tenant": "t1", "role": "admin"})
    assert resp.status_code == 403


def test_admin_crud_flow(app_client: TestClient) -> None:
    headers = admin_headers(app_client)
    created = app_client.post(
        "/v1/admin/tenants",
        json={"id": "acme", "display_name": "Acme"},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["voice"] == "default"

    dup = app_client.post(
        "/v1/admin/tenants",
        json={"id": "acme", "display_name": "Acme"},
        headers=headers,
    )
    assert dup.status_code == 409

    listed = app_client.get("/v1/admin/tenants", headers=headers)
    ids = [t["id"] for t in listed.json()]
    assert "acme" in ids and "demo-nbfc" in ids

    got = app_client.get("/v1/admin/tenants/acme", headers=headers)
    assert got.json()["display_name"] == "Acme"
    assert app_client.get("/v1/admin/tenants/ghost", headers=headers).status_code == 404

    voiced = app_client.put(
        "/v1/admin/tenants/acme/voice", json={"voice": "hi-female"}, headers=headers
    )
    assert voiced.json()["voice"] == "hi-female"
    missing = app_client.put("/v1/admin/tenants/ghost/voice", json={"voice": "x"}, headers=headers)
    assert missing.status_code == 404


def test_missing_token_rejected(app_client: TestClient) -> None:
    assert app_client.get("/v1/admin/tenants").status_code == 401


def test_bad_token_rejected(app_client: TestClient) -> None:
    assert (
        app_client.get("/v1/admin/tenants", headers={"Authorization": "Bearer junk"}).status_code
        == 401
    )


def test_viewer_cannot_manage(app_client: TestClient) -> None:
    resp = app_client.post(
        "/v1/admin/tokens",
        json={"tenant": "t1", "role": "viewer"},
        headers={"X-Admin-Key": "test-key"},
    )
    viewer = {"Authorization": f"Bearer {resp.json()['token']}"}
    assert app_client.get("/v1/admin/tenants", headers=viewer).status_code == 200
    assert (
        app_client.post(
            "/v1/admin/tenants",
            json={"id": "x", "display_name": "X"},
            headers=viewer,
        ).status_code
        == 403
    )


def test_calls_list_empty_then_populated(app_client: TestClient) -> None:
    headers = admin_headers(app_client)
    assert app_client.get("/v1/admin/calls", headers=headers).json() == []
    from vaani.ledger import CallRecord

    app_client.app.state.call_log.append(  # type: ignore[attr-defined]
        CallRecord(
            call_id="c1",
            tenant="t1",
            frames_received=2,
            frames_dropped=0,
            errors=0,
            transcript_chars=9,
            escalated=False,
        )
    )
    calls = app_client.get("/v1/admin/calls", headers=headers).json()
    assert [c["call_id"] for c in calls] == ["c1"]
