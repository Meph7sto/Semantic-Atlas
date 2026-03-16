"""
FastAPI auth admin/profile route contract tests.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError

from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import auth


class _StubAuthDB:
    def __init__(self):
        self.users = {
            "admin-1": {
                "user_id": "admin-1",
                "username": "admin",
                "display_name": "Admin",
                "role": "admin",
                "is_active": True,
                "password_hash": "hashed::x",
            },
            "u-1": {
                "user_id": "u-1",
                "username": "u1",
                "display_name": "User1",
                "role": "member",
                "is_active": True,
                "password_hash": "hashed::x",
            },
            "pending-1": {
                "user_id": "pending-1",
                "username": "pending1",
                "display_name": "Pending",
                "role": "viewer",
                "is_active": False,
                "registration_status": "pending",
                "password_hash": "hashed::x",
            },
        }

    def get_user_by_id(self, user_id: str):
        user = self.users.get(user_id)
        return dict(user) if user else None

    def list_users(self, role: str | None = None, limit: int = 100, offset: int = 0, include_inactive: bool = False):
        rows = list(self.users.values())
        if role:
            rows = [u for u in rows if u.get("role") == role]
        if not include_inactive:
            rows = [u for u in rows if u.get("is_active", True)]
        rows = rows[offset : offset + limit]
        return {"users": [dict(u) for u in rows], "total": len(rows)}

    def update_user(self, user_id: str, display_name: str | None = None, role: str | None = None, is_active: bool | None = None):
        user = self.users.get(user_id)
        if not user:
            return None
        if display_name is not None:
            user["display_name"] = display_name
        if role is not None:
            user["role"] = role
        if is_active is not None:
            user["is_active"] = is_active
        return dict(user)

    def list_scope_options(self):
        return {"products": [{"product_id": "prd-1"}], "projects": [{"project_id": "p-1"}]}

    def get_registration_details(self, user_id: str):
        user = self.users.get(user_id)
        return dict(user) if user else None

    def get_pending_registrations(self, status: str = "pending", limit: int = 100, offset: int = 0):
        rows = [u for u in self.users.values() if u.get("registration_status") == status]
        rows = rows[offset : offset + limit]
        return {"registrations": [dict(u) for u in rows], "total": len(rows), "limit": limit, "offset": offset}


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub = _StubAuthDB()
    monkeypatch.setattr(auth, "db_service", stub)

    app = build_test_app(auth.router)
    app.dependency_overrides[auth.get_current_user] = lambda: {"user_id": "u-1", "role": "member"}
    app.dependency_overrides[auth.require_admin] = lambda: {"user_id": "admin-1", "role": "admin"}

    async with async_client(app) as client:
        yield client, stub


async def test_logout_and_profile_and_directory(fastapi_client):
    client, _ = fastapi_client

    logout_resp = await client.post("/api/v2/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json()["message"] == "登出成功"

    profile_resp = await client.get("/api/v2/auth/profile")
    assert profile_resp.status_code == 200
    assert profile_resp.json()["data"]["user_id"] == "u-1"

    directory_resp = await client.get("/api/v2/auth/user-directory?role=member&limit=10&offset=0")
    assert directory_resp.status_code == 200
    data = directory_resp.json()["data"]
    assert data["users"][0]["username"] == "u1"
    assert data["limit"] == 10


async def test_admin_user_list_patch_scope_and_registration_endpoints(fastapi_client):
    client, _ = fastapi_client

    users_resp = await client.get("/api/v2/auth/users?limit=10&offset=0")
    assert users_resp.status_code == 200
    assert "users" in users_resp.json()["data"]

    patch_resp = await client.patch(
        "/api/v2/auth/users/u-1",
        json={"display_name": "U1-New", "role": "viewer", "is_active": False},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["display_name"] == "U1-New"
    assert patch_resp.json()["data"]["role"] == "viewer"
    assert patch_resp.json()["data"]["is_active"] is False

    scope_options = await client.get("/api/v2/auth/scope-options")
    assert scope_options.status_code == 200
    assert scope_options.json()["data"]["products"][0]["product_id"] == "prd-1"

    reg_list = await client.get("/api/v2/auth/registrations?status=pending&limit=10&offset=0")
    assert reg_list.status_code == 200
    assert reg_list.json()["total"] == 1

    reg_detail = await client.get("/api/v2/auth/registrations/pending-1")
    assert reg_detail.status_code == 200
    assert reg_detail.json()["user_id"] == "pending-1"

    pending_count = await client.get("/api/v2/auth/registrations/pending/count")
    assert pending_count.status_code == 200
    assert pending_count.json()["count"] == 1

