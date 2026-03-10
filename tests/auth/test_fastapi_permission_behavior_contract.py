"""
FastAPI permission behavior contract tests.
"""

import os
import sys
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import permission


class _StubPermissionDB:
    def __init__(self):
        self.members: dict[str, list[dict[str, Any]]] = {
            "p1": [{"user_id": "u-op", "roles": ["owner"]}]
        }
        self.permissions: dict[tuple[str, str], set[str]] = {
            ("p1", "u-op"): {"proj:add_member", "proj:remove_member", "req:baseline_manage", "req:change_approve", "req:change_request"},
            ("p-block", "u-op"): set(),
        }
        self.baselines_by_project = {"p1": [{"id": 11, "project_id": "p1", "version": "1.0.0", "locked": False}]}
        self.change_requests = {
            "c1": {"request_id": "c1", "project_id": "p1", "status": "pending"}
        }
        self.assigned_roles: list[tuple[str, str, str, str]] = []

    def get_user_by_id(self, user_id: str):
        if user_id in {"u-op", "u-target"}:
            return {"user_id": user_id, "username": user_id}
        return None

    def can_access_project(self, project_id: str, user_id: str, user: dict):
        _ = user
        return bool(self.permissions.get((project_id, user_id)))

    def check_permission(self, project_id: str, user_id: str, permission_code: str):
        perms = self.permissions.get((project_id, user_id), set())
        return permission_code in perms

    def add_project_member(self, project_id: str, target_user_id: str, operator_id: str):
        _ = operator_id
        self.members.setdefault(project_id, [])
        if any(m["user_id"] == target_user_id for m in self.members[project_id]):
            return None
        member = {"user_id": target_user_id, "roles": []}
        self.members[project_id].append(member)
        return member

    def assign_role(self, project_id: str, user_id: str, role_id: str, operator_id: str):
        self.assigned_roles.append((project_id, user_id, role_id, operator_id))
        for member in self.members.get(project_id, []):
            if member["user_id"] == user_id:
                member.setdefault("roles", []).append(role_id)

    def list_project_members(self, project_id: str, include_roles: bool = False):
        members = self.members.get(project_id, [])
        rows = [{"user_id": m["user_id"]} for m in members]
        if include_roles:
            rows = [{"user_id": m["user_id"], "roles": m.get("roles", [])} for m in members]
        return {"members": rows, "total": len(rows)}

    def remove_project_member(self, project_id: str, user_id: str):
        before = len(self.members.get(project_id, []))
        self.members[project_id] = [m for m in self.members.get(project_id, []) if m["user_id"] != user_id]
        return len(self.members[project_id]) < before

    def set_user_roles(self, project_id: str, user_id: str, roles: list[str], operator_id: str):
        _ = operator_id
        for member in self.members.get(project_id, []):
            if member["user_id"] == user_id:
                member["roles"] = list(roles)
                return {"user_id": user_id, "roles": list(roles)}
        return {"error": "成员不存在"}

    def get_baseline_by_version(self, project_id: str, version: str):
        for baseline in self.baselines_by_project.get(project_id, []):
            if baseline["version"] == version:
                return baseline
        return None

    def create_baseline(self, project_id: str, version: str, user_id: str, locked: bool):
        baseline = {"id": 12, "project_id": project_id, "version": version, "created_by": user_id, "locked": locked}
        self.baselines_by_project.setdefault(project_id, []).append(baseline)
        return baseline

    def get_change_request(self, request_id: str):
        return self.change_requests.get(request_id)

    def approve_change_request(self, request_id: str, user_id: str, review_comment: str | None):
        req = self.change_requests.get(request_id)
        if not req:
            return None
        req = dict(req)
        req["status"] = "approved"
        req["approved_by"] = user_id
        req["review_comment"] = review_comment
        return req

    def get_user_context(self, project_id: str, user_id: str, user: dict):
        _ = user
        return {"project_id": project_id, "user_id": user_id, "permissions": sorted(self.permissions.get((project_id, user_id), set()))}


@pytest.fixture
def fastapi_client(monkeypatch):
    stub = _StubPermissionDB()
    monkeypatch.setattr(permission, "db_service", stub)

    app = FastAPI()
    app.include_router(permission.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-op", "role": "member"}
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub


def test_add_member_and_set_roles_flow(fastapi_client):
    client, stub = fastapi_client

    add_resp = client.post(
        "/api/v2/permission/projects/p1/members",
        json={"user_id": "u-target", "member_roles": ["PO", "DEV"]},
    )
    assert add_resp.status_code == 200
    assert add_resp.json()["user_id"] == "u-target"
    assert "PO" in add_resp.json()["roles"]
    assert len(stub.assigned_roles) == 2

    set_roles = client.put(
        "/api/v2/permission/projects/p1/members/u-target/roles",
        json={"roles": ["QA"]},
    )
    assert set_roles.status_code == 200
    assert set_roles.json()["roles"] == ["QA"]


def test_remove_self_forbidden(fastapi_client):
    client, _ = fastapi_client

    response = client.delete("/api/v2/permission/projects/p1/members/u-op")
    assert response.status_code == 400
    assert response.json()["detail"] == "不能移除自己"


def test_baseline_duplicate_version_returns_400(fastapi_client):
    client, _ = fastapi_client

    response = client.post(
        "/api/v2/permission/projects/p1/baselines",
        json={"version": "1.0.0", "locked": False},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "版本号已存在"


def test_change_approve_permission_and_context_access(fastapi_client):
    client, stub = fastapi_client

    approve = client.post(
        "/api/v2/permission/change-requests/c1/approve",
        json={"review_comment": "ok"},
    )
    assert approve.status_code == 200
    assert approve.json()["status"] == "approved"

    # revoke approve permission and check 403
    stub.permissions[("p1", "u-op")].remove("req:change_approve")
    denied = client.post(
        "/api/v2/permission/change-requests/c1/approve",
        json={"review_comment": "again"},
    )
    assert denied.status_code == 403

    allowed_context = client.get("/api/v2/permission/projects/p1/context")
    assert allowed_context.status_code == 200
    assert allowed_context.json()["project_id"] == "p1"

    denied_context = client.get("/api/v2/permission/projects/p-block/context")
    assert denied_context.status_code == 403
    assert denied_context.json()["detail"] == "无访问项目权限"

