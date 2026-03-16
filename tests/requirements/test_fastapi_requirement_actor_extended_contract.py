"""
FastAPI requirement-actor extended contract tests.
"""

import datetime as dt
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError


from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import requirement_actor


class _StubActorManager:
    def __init__(self):
        self.command_calls: list[dict[str, Any]] = []
        self.cleanup_calls: list[int] = []
        self.stats = {
            "total_actors": 1,
            "active_actors": 1,
            "faulted_actors": 0,
            "actor_ids": ["r-1"],
            "mailbox_sizes": {"r-1": 1},
        }

    async def send_command(self, requirement_id: str, command: dict):
        self.command_calls.append({"requirement_id": requirement_id, "command": dict(command)})
        return {"status": "success", "requirement_id": requirement_id, "command": command}

    async def activate_actor(self, requirement_id: str):
        _ = requirement_id

    async def force_passivate(self, requirement_id: str):
        _ = requirement_id

    async def passivate_idle_actors(self, idle_timeout: int):
        self.cleanup_calls.append(idle_timeout)

    def get_stats(self):
        return dict(self.stats)


class _FakeEventStore:
    EVENTS: dict[str, list[dict[str, Any]]] = {}
    SNAPSHOTS: dict[str, dict[str, Any]] = {}

    def __init__(self, dsn: str):
        _ = dsn

    def get_events_by_requirement(self, requirement_id: str, limit: int = 100, offset: int = 0):
        rows = self.EVENTS.get(requirement_id, [])
        return rows[offset : offset + limit]

    def get_latest_snapshot(self, requirement_id: str):
        return self.SNAPSHOTS.get(requirement_id)


@pytest.fixture
async def fastapi_client(monkeypatch):
    manager = _StubActorManager()
    monkeypatch.setattr(requirement_actor, "_get_actor_manager", lambda: manager)

    import backend_business.services.event_store.event_store as event_store_module

    monkeypatch.setattr(event_store_module, "EventStore", _FakeEventStore)

    now = dt.datetime(2026, 3, 9, 10, 0, tzinfo=dt.timezone.utc)
    _FakeEventStore.EVENTS = {
        "r-1": [
            {
                "event_id": "e-1",
                "event_sequence": 1,
                "event_type": "RequirementCreated",
                "event_data": {
                    "title": "Title V1",
                    "description": "Desc",
                    "status": "Draft",
                    "priority": "medium",
                },
                "source": "u-1",
                "occurred_at": now,
            },
            {
                "event_id": "e-2",
                "event_sequence": 2,
                "event_type": "RequirementContentUpdated",
                "event_data": {"updates": {"title": "Title V2"}},
                "source": "u-1",
                "occurred_at": now + dt.timedelta(minutes=1),
            },
            {
                "event_id": "e-3",
                "event_sequence": 3,
                "event_type": "RequirementStatusChanged",
                "event_data": {"new_status": "confirmed"},
                "source": "u-2",
                "occurred_at": now + dt.timedelta(minutes=2),
            },
        ]
    }
    _FakeEventStore.SNAPSHOTS = {
        "r-1": {"requirement_id": "r-1", "current_version": 3, "title": "Title V2"}
    }

    app = build_test_app(requirement_actor.router)
    app.include_router(requirement_actor.internals_router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "actor-user"}

    async with async_client(app) as client:
        yield client, manager


async def test_command_endpoints_attach_source_and_dispatch(fastapi_client):
    client, manager = fastapi_client

    generic = await client.post(
        "/api/v2/requirement-actor/command",
        params={"requirement_id": "r-1"},
        json={"type": "UpdateRequirementContent", "updates": {"title": "X"}},
    )
    assert generic.status_code == 200
    assert generic.json()["command"]["source"] == "actor-user"

    create = await client.post(
        "/api/v2/requirement-actor/command/create",
        params={"requirement_id": "r-2", "status": "Draft", "priority": "high"},
        json={"content": {"title": "new"}},
    )
    assert create.status_code == 200
    assert create.json()["command"]["type"] == "CreateRequirement"

    change_status = await client.post(
        "/api/v2/requirement-actor/command/change-status",
        params={"requirement_id": "r-2", "new_status": "confirmed"},
    )
    assert change_status.status_code == 200
    assert change_status.json()["command"]["type"] == "ChangeStatus"

    quality = await client.post(
        "/api/v2/requirement-actor/command/add-quality-marker",
        params={"requirement_id": "r-2", "marker_type": "consistency", "marker_value": "good"},
    )
    assert quality.status_code == 200
    assert quality.json()["command"]["type"] == "AddQualityMarker"

    query_state = await client.post(
        "/api/v2/requirement-actor/command/query-state",
        params={"requirement_id": "r-2"},
    )
    assert query_state.status_code == 200
    assert query_state.json()["command"]["type"] == "QueryState"

    assert len(manager.command_calls) == 5


async def test_events_snapshot_versions_and_replay(fastapi_client):
    client, _ = fastapi_client

    events = await client.get("/api/v2/requirement-actor/events/r-1?limit=10&offset=0")
    assert events.status_code == 200
    assert events.json()["requirement_id"] == "r-1"
    assert events.json()["total"] == 3

    snapshot = await client.get("/api/v2/requirement-actor/snapshot/r-1")
    assert snapshot.status_code == 200
    assert snapshot.json()["current_version"] == 3

    versions = await client.get("/api/v2/requirement-actor/versions/r-1?limit=20")
    assert versions.status_code == 200
    assert len(versions.json()["versions"]) == 3
    assert versions.json()["versions"][0]["event_type"] == "RequirementCreated"

    replay = await client.get("/api/v2/requirement-actor/replay/r-1/3")
    assert replay.status_code == 200
    state = replay.json()["state"]
    assert state["title"] == "Title V2"
    assert state["status"] == "confirmed"
    assert replay.json()["events_count"] == 3


async def test_snapshot_not_found_and_cleanup_and_transitions(fastapi_client):
    client, manager = fastapi_client

    _FakeEventStore.SNAPSHOTS = {}
    missing_snapshot = await client.get("/api/v2/requirement-actor/snapshot/r-404")
    assert missing_snapshot.status_code == 404
    assert missing_snapshot.json()["detail"] == "快照不存在"

    cleanup = await client.post("/api/v2/requirement-actor/cleanup?idle_timeout=120")
    assert cleanup.status_code == 200
    assert cleanup.json()["status"] == "cleanup_complete"
    assert manager.cleanup_calls == [120]

    transitions = await client.get("/api/v2/requirement-actor/transitions")
    assert transitions.status_code == 200
    body = transitions.json()
    assert "status_enum" in body
    assert "transitions" in body
    assert "Draft" in body["transitions"]
