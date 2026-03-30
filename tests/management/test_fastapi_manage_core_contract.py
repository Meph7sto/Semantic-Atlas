"""
FastAPI manage core route contract tests.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError


from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import manage


class _StubManageDB:
    def __init__(self):
        self.scope_calls: list[dict[str, Any]] = []

    def get_user_by_id(self, user_id: str):
        return {"user_id": user_id, "role": "member"}

    def can_access_project(self, project_id: str, user_id: str, user: dict):
        _ = project_id, user_id, user
        return True

    def can_edit_project(self, project_id: str, user_id: str, user: dict):
        _ = project_id, user_id, user
        return True

    def get_accessible_projects(self, user_id: str, user: dict | None = None):
        _ = user_id, user
        return ["p-1"]

    def upsert_user_project_scope(self, user_id: str, project_id: str, can_edit: bool, granted_by: str):
        self.scope_calls.append(
            {
                "user_id": user_id,
                "project_id": project_id,
                "can_edit": can_edit,
                "granted_by": granted_by,
            }
        )


class _StubManageService:
    def __init__(self):
        self.projects: dict[str, dict[str, Any]] = {
            "p-1": {"project_id": "p-1", "name": "P1", "description": "", "status": "active"},
            "p-2": {"project_id": "p-2", "name": "P2", "description": "", "status": "active"},
        }
        self.requirements: dict[str, dict[str, Any]] = {
            "r-1": {
                "req_id": "r-1",
                "project_id": "p-1",
                "title": "old",
                "description": "",
                "status": "draft",
                "order_index": 0,
            }
        }
        self.audit_logs: list[dict[str, Any]] = []
        self._next_project = 2
        self._next_req = 1

    def add_audit_log(self, **kwargs):
        self.audit_logs.append(kwargs)

    def create_project(self, name: str, description: str, created_by: str):
        self._next_project += 1
        pid = f"p-{self._next_project}"
        project = {
            "project_id": pid,
            "name": name,
            "description": description,
            "status": "active",
            "created_by": created_by,
        }
        self.projects[pid] = project
        return dict(project)

    def list_projects(self):
        return [dict(v) for v in self.projects.values()]

    def get_project(self, project_id: str):
        proj = self.projects.get(project_id)
        if not proj or proj.get("status") == "archived":
            return None
        return dict(proj)

    def archive_project(self, project_id: str, updated_by: str):
        _ = updated_by
        proj = self.projects.get(project_id)
        if not proj or proj.get("status") == "archived":
            return 0
        proj["status"] = "archived"
        return 1

    def create_requirement(self, project_id: str, **kwargs):
        self._next_req += 1
        rid = f"r-{self._next_req}"
        req = {
            "req_id": rid,
            "project_id": project_id,
            "title": kwargs["title"],
            "description": kwargs.get("description", ""),
            "status": kwargs.get("status", "draft"),
            "order_index": kwargs.get("order_index", 0),
            "parent_id": kwargs.get("parent_id"),
        }
        self.requirements[rid] = req
        return dict(req)

    def list_requirements(self, project_id: str, include_deleted: bool = False):
        rows = [r for r in self.requirements.values() if r["project_id"] == project_id]
        if not include_deleted:
            rows = [r for r in rows if not r.get("deleted")]
        return [dict(r) for r in rows]

    def get_requirement(self, req_id: str):
        req = self.requirements.get(req_id)
        if not req:
            return None
        if req.get("deleted"):
            return None
        return dict(req)

    def update_requirement(self, req_id: str, update_data: dict[str, Any], updated_by: str):
        _ = updated_by
        req = self.requirements.get(req_id)
        if not req:
            raise ValueError("需求不存在")
        req.update(update_data)
        return dict(req)

    def bulk_update_requirement_status(self, req_ids: list[str], status: str, updated_by: str):
        _ = updated_by
        updated = 0
        for rid in req_ids:
            if rid in self.requirements and not self.requirements[rid].get("deleted"):
                self.requirements[rid]["status"] = status
                updated += 1
        return {"updated": updated, "skipped": len(req_ids) - updated}

    def move_requirement(self, req_id: str, parent_id: str | None, order_index: int, updated_by: str):
        _ = updated_by
        req = self.requirements.get(req_id)
        if not req:
            raise ValueError("需求不存在")
        req["parent_id"] = parent_id
        req["order_index"] = order_index

    def delete_requirement(self, req_id: str, cascade: bool = False, updated_by: str = ""):
        _ = cascade, updated_by
        req = self.requirements.get(req_id)
        if not req:
            raise ValueError("需求不存在")
        req["deleted"] = True
        return 1


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub_db = _StubManageDB()
    stub_service = _StubManageService()
    current_user = {"user_id": "admin-1", "role": "admin"}

    monkeypatch.setattr(manage, "_service", stub_service)
    monkeypatch.setattr(manage, "db_service", stub_db)

    app = build_test_app(manage.router)
    app.dependency_overrides[manage.get_current_user] = lambda: dict(current_user)

    async with async_client(app) as client:
        yield client, stub_db, stub_service, current_user


async def test_project_core_flow_with_role_gate(fastapi_client):
    client, stub_db, _, current_user = fastapi_client

    created = await client.post(
        "/api/v2/manage/projects",
        json={"name": "Core Project", "description": "desc"},
    )
    assert created.status_code == 200
    project_id = created.json()["project_id"]
    assert created.json()["name"] == "Core Project"
    assert stub_db.scope_calls[-1]["project_id"] == project_id

    # non-admin cannot create project
    current_user["role"] = "member"
    denied = await client.post("/api/v2/manage/projects", json={"name": "Denied"})
    assert denied.status_code == 403
    assert denied.json()["detail"] == "Permission denied"

    # member can list/get
    listed = await client.get("/api/v2/manage/projects")
    assert listed.status_code == 200
    ids = [p["project_id"] for p in listed.json()["projects"]]
    assert ids == ["p-1"]

    detail = await client.get("/api/v2/manage/projects/p-1")
    assert detail.status_code == 200
    assert detail.json()["project_id"] == "p-1"

    # switch back to admin for delete
    current_user["role"] = "admin"
    deleted = await client.delete("/api/v2/manage/projects/p-1")
    assert deleted.status_code == 200
    assert deleted.json() == {"success": True, "archived": 1}


async def test_requirement_core_crud_flow(fastapi_client):
    client, _, stub_service, _ = fastapi_client

    create_req = await client.post(
        "/api/v2/manage/projects/p-1/requirements",
        json={
            "requirement_type": "top_level",
            "title": "Need login",
            "description": "desc",
            "status": "draft",
        },
    )
    assert create_req.status_code == 200
    req_id = create_req.json()["req_id"]

    list_req = await client.get("/api/v2/manage/projects/p-1/requirements")
    assert list_req.status_code == 200
    assert any(item["req_id"] == req_id for item in list_req.json()["requirements"])

    update_req = await client.patch(
        f"/api/v2/manage/requirements/{req_id}",
        json={"status": "confirmed", "title": "Need login v2"},
    )
    assert update_req.status_code == 200
    assert update_req.json()["status"] == "confirmed"

    bulk = await client.post(
        "/api/v2/manage/requirements/bulk-status",
        json={"req_ids": [req_id], "status": "completed"},
    )
    assert bulk.status_code == 200
    assert bulk.json()["updated"] == 1

    moved = await client.post(
        f"/api/v2/manage/requirements/{req_id}/move",
        json={"parent_id": "r-1", "order_index": 3},
    )
    assert moved.status_code == 200
    assert moved.json()["success"] is True
    assert stub_service.requirements[req_id]["parent_id"] == "r-1"
    assert stub_service.requirements[req_id]["order_index"] == 3

    deleted = await client.delete(f"/api/v2/manage/requirements/{req_id}?cascade=true")
    assert deleted.status_code == 200
    assert deleted.json()["deleted"] == 1
    assert stub_service.requirements[req_id]["deleted"] is True


async def test_requirement_missing_required_field_returns_422(fastapi_client):
    client, _, _, _ = fastapi_client

    response = await client.post(
        "/api/v2/manage/projects/p-1/requirements",
        json={
            "title": "bad status",
            "status": "draft",
        },
    )
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item.get("loc") == ["body", "requirement_type"] for item in detail)
