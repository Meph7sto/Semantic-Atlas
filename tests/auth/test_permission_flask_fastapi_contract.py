"""
FastAPI strict contract tests for permission routes.

Despite the filename, this suite no longer compares against Flask behavior.
It ensures we do not keep compatibility coercions for legacy callers.
"""

import os
import sys

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import permission
from backend_business.services.auth_service import get_auth_service


class _StubPermissionDBService:
    def __init__(self):
        self.last_include_roles = None
        self.last_include_locked = None

    @staticmethod
    def check_permission(*args, **kwargs):
        return True

    @staticmethod
    def is_project_member(*args, **kwargs):
        return True

    def list_project_members(self, project_id, include_roles=False):
        self.last_include_roles = include_roles
        return {"members": [], "total": 0}

    def list_project_baselines(self, project_id, include_locked=True):
        self.last_include_locked = include_locked
        return []


def _auth_headers() -> dict:
    token = get_auth_service().generate_token(
        user_id="contract-user",
        username="contract-user",
        role="member",
        external_type=None,
    )
    return {"Authorization": f"Bearer {token}"}


def _assert_validation_error(response, field: str, scope: str = "body"):
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any(item.get("loc") == [scope, field] for item in detail)


@pytest.fixture
def fastapi_client(monkeypatch):
    stub = _StubPermissionDBService()
    monkeypatch.setattr(permission, "db_service", stub)

    app = FastAPI()
    app.include_router(permission.router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub


def test_missing_token_uses_fastapi_error_shape(fastapi_client):
    client, _ = fastapi_client
    response = client.get("/api/permission/projects/p1/members")
    assert response.status_code == 401
    assert response.json()["detail"] == "未提供认证 Token"


def test_invalid_token_uses_fastapi_error_shape(fastapi_client):
    client, _ = fastapi_client
    response = client.get(
        "/api/permission/projects/p1/members",
        headers={"Authorization": "Bearer invalid_token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Token 无效或已过期"


@pytest.mark.parametrize(
    ("method", "path", "payload", "field"),
    [
        ("post", "/api/permission/projects/p1/members", None, "body"),
        ("post", "/api/permission/projects/p1/members", {"user_id": ""}, "user_id"),
        ("put", "/api/permission/projects/p1/members/u1/roles", None, "body"),
        ("put", "/api/permission/projects/p1/members/u1/roles", {"roles": "PO"}, "roles"),
        ("post", "/api/permission/requirements/r1/reviews", None, "body"),
        ("post", "/api/permission/requirements/r1/reviews", {"seq": 1}, "reviewer_id"),
    ],
)
def test_validation_errors_follow_fastapi_422(fastapi_client, method, path, payload, field):
    client, _ = fastapi_client
    headers = _auth_headers()

    if payload is None:
        response = getattr(client, method)(
            path,
            content="null",
            headers={**headers, "Content-Type": "application/json"},
        )
    else:
        response = getattr(client, method)(path, json=payload, headers=headers)

    if field == "body":
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)
    else:
        _assert_validation_error(response, field)


def test_invalid_include_roles_is_rejected_instead_of_legacy_coercion(fastapi_client):
    client, stub = fastapi_client
    response = client.get(
        "/api/permission/projects/p1/members?include_roles=abc",
        headers=_auth_headers(),
    )
    _assert_validation_error(response, "include_roles", scope="query")
    assert stub.last_include_roles is None


def test_invalid_include_locked_is_rejected_instead_of_legacy_coercion(fastapi_client):
    client, stub = fastapi_client
    response = client.get(
        "/api/permission/projects/p1/baselines?include_locked=abc",
        headers=_auth_headers(),
    )
    _assert_validation_error(response, "include_locked", scope="query")
    assert stub.last_include_locked is None


def test_valid_bool_query_values_are_forwarded(fastapi_client):
    client, stub = fastapi_client
    headers = _auth_headers()

    members_resp = client.get(
        "/api/permission/projects/p1/members?include_roles=true",
        headers=headers,
    )
    baselines_resp = client.get(
        "/api/permission/projects/p1/baselines?include_locked=false",
        headers=headers,
    )

    assert members_resp.status_code == 200
    assert baselines_resp.status_code == 200
    assert stub.last_include_roles is True
    assert stub.last_include_locked is False
