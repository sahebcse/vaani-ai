"""Unit tests for the session registry (no I/O)."""

from vaani.sessions import CallSession, InMemorySessionStore, SessionStore


def test_create_assigns_unique_ids() -> None:
    store = InMemorySessionStore()
    first = store.create("t1")
    second = store.create("t1")
    assert first.call_id != second.call_id
    assert isinstance(first, CallSession)
    assert (first.tenant, first.frames_received, first.frames_dropped) == ("t1", 0, 0)
    assert store.count() == 2


def test_get_remove_and_missing() -> None:
    store = InMemorySessionStore()
    session = store.create("t1")
    assert store.get(session.call_id) is session
    assert store.get("nope") is None
    store.remove(session.call_id)
    assert store.get(session.call_id) is None
    assert store.count() == 0
    store.remove("nope")  # no error on unknown id


def test_abstract_store_raises() -> None:
    import pytest

    store = SessionStore()
    with pytest.raises(NotImplementedError):
        store.create("t")
    with pytest.raises(NotImplementedError):
        store.get("x")
    with pytest.raises(NotImplementedError):
        store.remove("x")
    with pytest.raises(NotImplementedError):
        store.count()
