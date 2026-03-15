"""
FastAPI auth core route contract tests.
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

from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import auth


class _StubAuthService:
    def __init__(self):
        self.generated_token_for: list[tuple[str, str]] = []
        self._next_uid = 100

    def verify_password(self, password: str, password_hash: str) -> bool:
        return password_hash == f"hashed::{password}"

    def hash_password(self, password: str) -> str:
        return f"hashed::{password}"

    def generate_user_id(self) -> str:
        self._next_uid += 1
        return f"user-{self._next_uid}"

    def generate_token(
        self,
        user_id: str,
        username: str,
        role: str,
        external_type: str | None = None,
    ) -> str:
        _ = username, external_type
        self.generated_token_for.append((user_id, role))
        return f"token-{user_id}-{role}"


class _StubAuthDBService:
    def __init__(self):
        self.users_by_id: dict[str, dict[str, Any]] = {
            "admin-1": {
                "user_id": "admin-1",
                "username": "admin",
                "display_name": "Admin",
                "role": "admin",
                "password_hash": "hashed::admin123",
                "is_active": True,
                "external_type": None,
                "registration_status": "approved",
            },
            "member-1": {
                "user_id": "member-1",
                "username": "member",
                "display_name": "Member",
                "role": "member",
                "password_hash": "hashed::old123",
                "is_active": True,
                "external_type": None,
                "registration_status": "approved",
            },
            "pending-1": {
                "user_id": "pending-1",
                "username": "pending_user",
                "display_name": "Pending",
                "role": "viewer",
                "password_hash": "hashed::pending123",
                "is_active": False,
                "external_type": None,
                "registration_status": "pending",
            },
        }
        self.user_scopes: dict[str, dict[str, Any]] = {}

    def _by_username(self, username: str) -> dict[str, Any] | None:
        for user in self.users_by_id.values():
            if user.get("username") == username:
                return user
        return None

    def get_user_by_username_for_auth(self, username: str):
        return self._by_username(username)

    def get_user_by_username(self, username: str):
        user = self._by_username(username)
        if not user:
            return None
        if user.get("registration_status") in ("pending", "approved"):
            return user
        return None

    def create_user(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        display_name: str,
        role: str | None = None,
        is_active: bool = True,
        external_type: str | None = None,
        registration_status: str = "approved",
    ):
        user = {
            "user_id": user_id,
            "username": username,
            "display_name": display_name,
            "role": role or "viewer",
            "password_hash": password_hash,
            "is_active": is_active,
            "external_type": external_type,
            "registration_status": registration_status,
        }
        self.users_by_id[user_id] = user
        return dict(user)

    def get_user_by_id(self, user_id: str):
        user = self.users_by_id.get(user_id)
        return dict(user) if user else None

    def update_profile(self, user_id: str, display_name: str | None, avatar_url: str | None):
        user = self.users_by_id.get(user_id)
        if not user:
            return None
        if display_name is not None:
            user["display_name"] = display_name
        if avatar_url is not None:
            user["avatar_url"] = avatar_url
        return dict(user)

    def change_password(self, user_id: str, new_password_hash: str) -> bool:
        user = self.users_by_id.get(user_id)
        if not user:
            return False
        user["password_hash"] = new_password_hash
        return True

    def list_users(self, role: str | None = None, limit: int = 100, offset: int = 0, include_inactive: bool = False):
        users = list(self.users_by_id.values())
        if role:
            users = [u for u in users if u.get("role") == role]
        if not include_inactive:
            users = [u for u in users if u.get("is_active", True)]
        sliced = users[offset : offset + limit]
        return {"users": [dict(u) for u in sliced], "total": len(users)}

    def update_user(
        self,
        user_id: str,
        display_name: str | None = None,
        role: str | None = None,
        is_active: bool | None = None,
    ):
        user = self.users_by_id.get(user_id)
        if not user:
            return None
        if display_name is not None:
            user["display_name"] = display_name
        if role is not None:
            user["role"] = role
        if is_active is not None:
            user["is_active"] = is_active
        return dict(user)

    def get_registration_details(self, user_id: str):
        user = self.users_by_id.get(user_id)
        return dict(user) if user else None

    def list_scope_options(self):
        return {"products": [{"product_id": "prd-1"}], "projects": [{"project_id": "p-1"}]}

    def get_user_scopes(self, user_id: str):
        return self.user_scopes.get(user_id, {"product_scopes": [], "project_scopes": []})

    def replace_user_scopes(
        self,
        user_id: str,
        product_scopes: list[dict[str, Any]],
        project_scopes: list[dict[str, Any]],
        granted_by: str,
    ):
        self.user_scopes[user_id] = {
            "product_scopes": product_scopes,
            "project_scopes": project_scopes,
            "granted_by": granted_by,
        }
        return dict(self.user_scopes[user_id])

    def get_pending_registrations(self, status: str = "pending", limit: int = 100, offset: int = 0):
        users = [u for u in self.users_by_id.values() if u.get("registration_status") == status]
        sliced = users[offset : offset + limit]
        return {"registrations": [dict(u) for u in sliced], "total": len(users), "limit": limit, "offset": offset}

    def approve_registration(self, user_id: str, approved_by_user_id: str, role: str, external_type: str | None):
        user = self.users_by_id.get(user_id)
        if not user:
            return None
        user["registration_status"] = "approved"
        user["role"] = role
        user["external_type"] = external_type
        user["is_active"] = True
        user["approved_by"] = approved_by_user_id
        return dict(user)

    def reject_registration(self, user_id: str, rejected_by_user_id: str, rejection_reason: str):
        user = self.users_by_id.get(user_id)
        if not user:
            return None
        user["registration_status"] = "rejected"
        user["rejection_reason"] = rejection_reason
        user["rejected_by"] = rejected_by_user_id
        return dict(user)


@pytest.fixture
def fastapi_client(monkeypatch):
    db_stub = _StubAuthDBService()
    auth_stub = _StubAuthService()

    monkeypatch.setattr(auth, "db_service", db_stub)
    monkeypatch.setattr(auth, "get_auth_service", lambda: auth_stub)

    app = FastAPI()
    app.include_router(auth.router)
    app.dependency_overrides[auth.get_current_user] = lambda: {
        "user_id": "member-1",
        "role": "member",
    }
    app.dependency_overrides[auth.require_admin] = lambda: {
        "user_id": "admin-1",
        "role": "admin",
    }
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, db_stub, auth_stub


def test_login_and_pending_block(fastapi_client):
    client, _, auth_stub = fastapi_client

    success = client.post(
        "/api/v2/auth/login",
        json={"username": "member", "password": "old123", "role": "member"},
    )
    assert success.status_code == 200
    data = success.json()["data"]
    assert data["user_id"] == "member-1"
    assert data["role"] == "member"
    assert data["token"] == "token-member-1-member"
    assert auth_stub.generated_token_for == [("member-1", "member")]

    pending = client.post(
        "/api/v2/auth/login",
        json={"username": "pending_user", "password": "pending123"},
    )
    assert pending.status_code == 403
    assert "注册审核中" in pending.json()["detail"]


def test_register_success_and_duplicate(fastapi_client):
    client, db_stub, _ = fastapi_client

    first = client.post(
        "/api/v2/auth/register",
        json={"username": "new_user", "password": "new1234", "display_name": "新用户"},
    )
    assert first.status_code == 200
    body = first.json()["data"]
    assert body["registration_status"] == "pending"
    assert body["username"] == "new_user"
    assert db_stub.get_user_by_username("new_user") is not None

    duplicate = client.post(
        "/api/v2/auth/register",
        json={"username": "new_user", "password": "new1234", "display_name": "重复"},
    )
    assert duplicate.status_code == 400
    assert duplicate.json()["detail"] == "用户名已存在"


def test_me_profile_and_change_password(fastapi_client):
    client, db_stub, _ = fastapi_client

    me_resp = client.get("/api/v2/auth/me")
    assert me_resp.status_code == 200
    me_data = me_resp.json()["data"]
    assert me_data["user_id"] == "member-1"
    assert "password_hash" not in me_data

    patch_resp = client.patch(
        "/api/v2/auth/profile",
        json={"display_name": "Member New", "avatar_url": "https://example.com/a.png"},
    )
    assert patch_resp.status_code == 200
    assert patch_resp.json()["data"]["display_name"] == "Member New"

    wrong_old = client.post(
        "/api/v2/auth/profile/change-password",
        json={"old_password": "bad", "new_password": "new_pass_1"},
    )
    assert wrong_old.status_code == 400
    assert wrong_old.json()["detail"] == "当前密码不正确"

    ok = client.post(
        "/api/v2/auth/profile/change-password",
        json={"old_password": "old123", "new_password": "new_pass_1"},
    )
    assert ok.status_code == 200
    assert ok.json()["message"] == "密码修改成功"
    assert db_stub.users_by_id["member-1"]["password_hash"] == "hashed::new_pass_1"


def test_admin_user_and_scope_and_registration_flow(fastapi_client):
    client, db_stub, _ = fastapi_client

    create_user = client.post(
        "/api/v2/auth/users",
        json={
            "username": "ops_member",
            "password": "ops1234",
            "display_name": "Ops",
            "role": "member",
            "external_type": "CLIENT",
        },
    )
    assert create_user.status_code == 200
    created_id = create_user.json()["data"]["user_id"]

    scope_put = client.put(
        f"/api/v2/auth/users/{created_id}/scopes",
        json={
            "product_scopes": [{"product_id": "prd-1", "can_edit": True}],
            "project_scopes": [{"project_id": "p-1", "can_edit": False}],
        },
    )
    assert scope_put.status_code == 200
    assert scope_put.json()["data"]["product_scopes"][0]["product_id"] == "prd-1"

    scope_get = client.get(f"/api/v2/auth/users/{created_id}/scopes")
    assert scope_get.status_code == 200
    assert scope_get.json()["data"]["project_scopes"][0]["project_id"] == "p-1"

    approve = client.post(
        "/api/v2/auth/registrations/pending-1/approve",
        json={"role": "viewer", "external_type": "CONTRACTOR"},
    )
    assert approve.status_code == 200
    assert approve.json()["data"]["registration_status"] == "approved"

    # create a fresh pending user to verify reject flow
    user = db_stub.create_user(
        user_id="pending-2",
        username="pending2",
        password_hash="hashed::123456",
        display_name="Pending2",
        role="viewer",
        is_active=False,
        registration_status="pending",
    )
    assert user["user_id"] == "pending-2"

    reject = client.post(
        "/api/v2/auth/registrations/pending-2/reject",
        json={"reason": "资料不完整"},
    )
    assert reject.status_code == 200
    assert reject.json()["data"]["registration_status"] == "rejected"

