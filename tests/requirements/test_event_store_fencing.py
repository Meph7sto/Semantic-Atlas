"""Unit coverage for the durable actor fencing barrier."""

from __future__ import annotations

from typing import Any

import pytest
from backend_business.services.event_store.event_store import (
    EventStore,
    StaleActorLeaseError,
)


class _Cursor:
    def __init__(self, rows: list[Any]) -> None:
        self.rows = list(rows)
        self.executions: list[tuple[str, tuple[Any, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self.executions.append((sql, params))

    def fetchone(self):
        return self.rows.pop(0)


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor
        self.commits = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self, **_kwargs):
        return self._cursor

    def commit(self) -> None:
        self.commits += 1


def test_claim_actor_fence_requires_a_strictly_newer_token(monkeypatch):
    cursor = _Cursor([(12,)])
    connection = _Connection(cursor)
    store = EventStore("unused")
    monkeypatch.setattr(store, "_connect", lambda: connection)

    assert store.claim_actor_fence("req-claim", 12) == 12
    sql, params = cursor.executions[0]
    assert "requirement_actor_fences.fencing_token < EXCLUDED.fencing_token" in sql
    assert params == ("req-claim", 12)
    assert connection.commits == 1


def test_claim_actor_fence_rejects_a_stale_token(monkeypatch):
    cursor = _Cursor([None])
    store = EventStore("unused")
    monkeypatch.setattr(store, "_connect", lambda: _Connection(cursor))

    with pytest.raises(StaleActorLeaseError):
        store.claim_actor_fence("req-stale", 4)


def test_event_writes_require_the_exact_claimed_fence():
    cursor = _Cursor([None])

    with pytest.raises(StaleActorLeaseError):
        EventStore._assert_actor_fence(cursor, "req-write", 8)

    sql, params = cursor.executions[0]
    assert "fencing_token = %s" in sql
    assert params == ("req-write", 8)
