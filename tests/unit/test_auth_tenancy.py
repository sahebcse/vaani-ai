"""Unit tests for tokens, tenants, and the call ledger."""

import time

import pytest

from vaani.auth import (
    ADMIN_ROLE,
    VIEWER_ROLE,
    AuthError,
    issue_token,
    verify_token,
)
from vaani.ledger import CallLog, CallRecord
from vaani.tenancy import DuplicateTenantError, InMemoryTenantStore, Tenant, TenantStore


def test_token_roundtrip() -> None:
    token = issue_token("t1", ADMIN_ROLE, "secret")
    principal = verify_token(token, "secret")
    assert (principal.tenant, principal.role) == ("t1", ADMIN_ROLE)


def test_token_wrong_secret_rejected() -> None:
    token = issue_token("t1", VIEWER_ROLE, "secret")
    with pytest.raises(AuthError, match="bad signature"):
        verify_token(token, "other")


def test_token_malformed_rejected() -> None:
    for bad in ("", "a.b", "a.b.c.d"):
        with pytest.raises(AuthError, match="malformed"):
            verify_token(bad, "secret")


def test_token_tampered_payload_rejected() -> None:
    token = issue_token("t1", VIEWER_ROLE, "secret")
    head, _, sig = token.split(".")
    import base64

    payload = base64.urlsafe_b64encode(b'{"role":"admin"}').decode().rstrip("=")
    with pytest.raises(AuthError, match="bad signature"):
        verify_token(f"{head}.{payload}.{sig}", "secret")


def test_token_expired_rejected() -> None:
    token = issue_token("t1", VIEWER_ROLE, "secret", ttl_seconds=-1)
    with pytest.raises(AuthError, match="expired"):
        verify_token(token, "secret")


def test_token_unknown_role_rejected() -> None:
    token = issue_token("t1", "root", "secret")
    with pytest.raises(AuthError, match="unknown role"):
        verify_token(token, "secret")


def test_token_garbage_payload_rejected() -> None:
    import base64
    import hashlib
    import hmac
    import json

    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(b"not-json").decode().rstrip("=")
    sig = (
        base64.urlsafe_b64encode(
            hmac.new(b"s", f"{header}.{payload}".encode(), hashlib.sha256).digest()
        )
        .decode()
        .rstrip("=")
    )
    with pytest.raises(AuthError, match="bad payload"):
        verify_token(f"{header}.{payload}.{sig}", "s")


def test_token_non_dict_payload_rejected() -> None:
    import base64
    import hashlib
    import hmac
    import json

    header = base64.urlsafe_b64encode(json.dumps({"alg": "HS256"}).encode()).decode().rstrip("=")
    payload = base64.urlsafe_b64encode(b"123").decode().rstrip("=")
    sig = (
        base64.urlsafe_b64encode(
            hmac.new(b"s", f"{header}.{payload}".encode(), hashlib.sha256).digest()
        )
        .decode()
        .rstrip("=")
    )
    with pytest.raises(AuthError, match="bad payload"):
        verify_token(f"{header}.{payload}.{sig}", "s")


def test_token_expiry_is_now_plus_ttl() -> None:
    import base64
    import json

    before = int(time.time())
    token = issue_token("t1", VIEWER_ROLE, "secret", ttl_seconds=100)
    claims = json.loads(base64.urlsafe_b64decode(token.split(".")[1] + "=="))
    assert before + 90 <= int(claims["exp"]) <= int(time.time()) + 100


def test_tenant_store_crud() -> None:
    store = InMemoryTenantStore()
    assert store.list_all() == []
    assert store.get("x") is None
    assert store.set_voice("x", "v") is None
    created = store.create(Tenant(id="b", display_name="B"))
    store.create(Tenant(id="a", display_name="A"))
    assert [t.id for t in store.list_all()] == ["a", "b"]
    assert store.get("b") == created
    updated = store.set_voice("b", "en-female")
    assert updated is not None and updated.voice == "en-female"
    with pytest.raises(DuplicateTenantError):
        store.create(Tenant(id="a", display_name="dup"))


def test_tenant_defaults() -> None:
    tenant = Tenant(id="x", display_name="X")
    assert tenant.allowed_languages == ["hi", "en"]
    assert tenant.voice == "default"


def test_abstract_store_raises() -> None:
    store = TenantStore()
    with pytest.raises(NotImplementedError):
        store.get("x")
    with pytest.raises(NotImplementedError):
        store.list_all()
    with pytest.raises(NotImplementedError):
        store.create(Tenant(id="x", display_name="X"))
    with pytest.raises(NotImplementedError):
        store.set_voice("x", "v")


def record(call_id: str = "c1") -> CallRecord:
    return CallRecord(
        call_id=call_id,
        tenant="t1",
        frames_received=3,
        frames_dropped=1,
        errors=0,
        transcript_chars=12,
        escalated=False,
    )


def test_ledger_append_list_count() -> None:
    log = CallLog()
    assert log.count() == 0
    log.append(record("c1"))
    log.append(record("c2"))
    assert log.count() == 2
    assert [r.call_id for r in log.list_recent()] == ["c2", "c1"]
    assert [r.call_id for r in log.list_recent(limit=1)] == ["c2"]


def test_ledger_evicts_beyond_limit() -> None:
    log = CallLog(limit=2)
    log.append(record("c1"))
    log.append(record("c2"))
    log.append(record("c3"))
    assert log.count() == 2
    assert [r.call_id for r in log.list_recent()] == ["c3", "c2"]
