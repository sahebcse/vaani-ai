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


def test_experiment_flow_and_report(app_client: TestClient) -> None:
    headers = admin_headers(app_client)
    assert app_client.get("/v1/admin/eval-report", headers=headers).status_code == 404
    resp = app_client.post(
        "/v1/admin/experiments",
        json={"name": "tone", "prompts": ["concise", "detailed"]},
        headers=headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["winner"] in ("concise", "detailed")
    assert body["runs"] == 3 * 2  # 3 fixture cases x 2 prompts
    assert set(body["means"]) == {"concise", "detailed"}
    report = app_client.get("/v1/admin/eval-report", headers=headers).json()
    assert report["name"] == "tone"


def test_experiment_needs_two_prompts(app_client: TestClient) -> None:
    headers = admin_headers(app_client)
    resp = app_client.post(
        "/v1/admin/experiments", json={"name": "x", "prompts": ["only"]}, headers=headers
    )
    assert resp.status_code == 422


def test_experiment_empty_dataset_rejected(
    app_client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("VAANI_EVAL_DATASET_PATH", "/nonexistent/d.jsonl")
    headers = admin_headers(app_client)
    resp = app_client.post(
        "/v1/admin/experiments",
        json={"name": "x", "prompts": ["a", "b"]},
        headers=headers,
    )
    assert resp.status_code == 400


def test_experiment_requires_admin(app_client: TestClient) -> None:
    resp = app_client.post(
        "/v1/admin/experiments",
        json={"name": "x", "prompts": ["a", "b"]},
    )
    assert resp.status_code == 401


def test_feedback_roundtrip(app_client: TestClient) -> None:
    headers = admin_headers(app_client)
    created = app_client.post(
        "/v1/admin/feedback",
        json={"call_id": "c9", "tenant": "t1", "helpful": True, "note": "great"},
        headers=headers,
    )
    assert created.status_code == 201
    listed = app_client.get("/v1/admin/feedback", headers=headers).json()
    assert [(f["call_id"], f["helpful"]) for f in listed] == [("c9", True)]


def test_viewer_can_use_feedback_but_not_experiments(app_client: TestClient) -> None:
    resp = app_client.post(
        "/v1/admin/tokens",
        json={"tenant": "t1", "role": "viewer"},
        headers={"X-Admin-Key": "test-key"},
    )
    viewer = {"Authorization": f"Bearer {resp.json()['token']}"}
    assert app_client.get("/v1/admin/feedback", headers=viewer).status_code == 200
    assert (
        app_client.post(
            "/v1/admin/experiments",
            json={"name": "x", "prompts": ["a", "b"]},
            headers=viewer,
        ).status_code
        == 403
    )
