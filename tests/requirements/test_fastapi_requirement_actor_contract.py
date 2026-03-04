"""
RequirementActor router contract tests for P0 fixes.
"""

import os
import sys
from typing import Any

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import requirement_actor
from backend_business.services.actor.actors.requirement_actor import DomainException


class _StubProjection:
    def __init__(self, *, wait_result: bool = True, requirement: dict[str, Any] | None = None):
        self.wait_result = wait_result
        self.requirement = requirement or {}
        self.wait_calls: list[dict[str, Any]] = []
        self.get_calls: list[str] = []

    async def wait_for_version(self, requirement_id: str, min_version: int, timeout: float = 5.0) -> bool:
        self.wait_calls.append(
            {
                "requirement_id": requirement_id,
                "min_version": min_version,
                "timeout": timeout,
            }
        )
        return self.wait_result

    def get_requirement(self, requirement_id: str):
        self.get_calls.append(requirement_id)
        return self.requirement


class _StubManager:
    def __init__(self):
        self.activate_calls: list[str] = []
        self.stats_data = {
            "total_actors": 0,
            "active_actors": 0,
            "faulted_actors": 0,
            "actor_ids": [],
            "mailbox_sizes": {},
        }

    async def activate_actor(self, requirement_id: str):
        self.activate_calls.append(requirement_id)

    async def send_command(self, requirement_id: str, command: dict):
        return {"status": "success", "requirement_id": requirement_id, "command": command}

    def get_stats(self):
        return self.stats_data


class _DomainErrorManager(_StubManager):
    async def send_command(self, requirement_id: str, command: dict):
        raise DomainException("禁止修改已基线需求")


def _build_client():
    app = FastAPI()
    app.include_router(requirement_actor.router)
    app.include_router(requirement_actor.internals_router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-1"}
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)
    return TestClient(app, raise_server_exceptions=False)


def test_query_requirement_waits_for_min_version_and_returns_read_model(monkeypatch):
    projection = _StubProjection(
        wait_result=True,
        requirement={"req_id": "r-1", "current_version": 42, "title": "t"},
    )
    monkeypatch.setattr(requirement_actor, "_projection", projection)

    with _build_client() as client:
        response = client.get(
            "/api/v2/requirement-actor/query",
            params={"requirement_id": "r-1", "min_version": 42, "timeout": 3},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "success"
    assert body["source"] == "read_model"
    assert body["requirement"]["current_version"] == 42
    assert projection.wait_calls == [{"requirement_id": "r-1", "min_version": 42, "timeout": 3.0}]
    assert projection.get_calls == ["r-1"]


def test_query_requirement_min_version_timeout_returns_503(monkeypatch):
    projection = _StubProjection(wait_result=False, requirement={"req_id": "r-1"})
    monkeypatch.setattr(requirement_actor, "_projection", projection)

    with _build_client() as client:
        response = client.get(
            "/api/v2/requirement-actor/query",
            params={"requirement_id": "r-1", "min_version": 99, "timeout": 1},
        )

    assert response.status_code == 503
    assert "读模型尚未追上指定版本" in response.json()["detail"]


def test_force_activate_uses_actor_manager(monkeypatch):
    manager = _StubManager()
    monkeypatch.setattr(requirement_actor, "_actor_manager", manager)

    with _build_client() as client:
        response = client.post("/api/v2/requirement-actor/force-activate/r-1")

    assert response.status_code == 200
    assert response.json()["status"] == "activated"
    assert manager.activate_calls == ["r-1"]


def test_command_domain_exception_returns_409(monkeypatch):
    manager = _DomainErrorManager()
    monkeypatch.setattr(requirement_actor, "_actor_manager", manager)

    with _build_client() as client:
        response = client.post(
            "/api/v2/requirement-actor/command/update-content",
            params={"requirement_id": "r-1"},
            json={"updates": {"title": "next"}},
        )

    assert response.status_code == 409
    assert "已基线需求" in response.json()["detail"]


def test_internals_stats_route_returns_actor_stats(monkeypatch):
    manager = _StubManager()
    manager.stats_data = {
        "total_actors": 2,
        "active_actors": 1,
        "faulted_actors": 1,
        "actor_ids": ["r-1", "r-2"],
        "mailbox_sizes": {"r-1": 3, "r-2": 0},
    }
    monkeypatch.setattr(requirement_actor, "_actor_manager", manager)

    with _build_client() as client:
        response = client.get("/api/v2/_internals/actors/stats")

    assert response.status_code == 200
    assert response.json()["total_actors"] == 2
    assert response.json()["mailbox_sizes"]["r-1"] == 3
