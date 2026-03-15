"""
FastAPI permission route contract tests.

These tests enforce FastAPI-native request/response semantics.
"""

import os
import sys

import pytest
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.main import app
from backend_business.services.auth_service import get_auth_service


def _get_valid_token() -> str:
    auth_service = get_auth_service()
    return auth_service.generate_token(
        user_id="test-user",
        username="test",
        role="member",
        external_type=None,
    )


def _assert_validation_error(response, loc_field: str, loc_scope: str = "body") -> None:
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any(item.get("loc") == [loc_scope, loc_field] for item in detail)


def _send(client: TestClient, method: str, url: str, headers: dict, payload):
    if method == "POST":
        return client.post(url, headers=headers, json=payload)
    if method == "GET":
        return client.get(url, headers=headers)
    if method == "DELETE":
        return client.delete(url, headers=headers)
    if method == "PUT":
        return client.put(url, headers=headers, json=payload)
    raise AssertionError(f"Unsupported method: {method}")


@pytest.fixture
def client():
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c


@pytest.fixture
def auth_headers():
    return {"Authorization": f"Bearer {_get_valid_token()}"}


@pytest.mark.parametrize(
    ("method", "path", "payload", "field"),
    [
        ("POST", "/api/permission/projects/p1/members", {"user_id": ""}, "user_id"),
        ("PUT", "/api/permission/projects/p1/members/u1/roles", {"roles": "PO"}, "roles"),
        ("POST", "/api/permission/requirements/r1/reviews", {"seq": 1}, "reviewer_id"),
        ("POST", "/api/permission/projects/p1/baselines", {"locked": False}, "version"),
        (
            "POST",
            "/api/permission/requirements/r1/change-requests",
            {"reason": "r", "change_summary": "s"},
            "baseline_id",
        ),
        (
            "POST",
            "/api/permission/requirements/r1/change-requests",
            {"baseline_id": 1, "change_summary": "s"},
            "reason",
        ),
        (
            "POST",
            "/api/permission/requirements/r1/change-requests",
            {"baseline_id": 1, "reason": "r"},
            "change_summary",
        ),
    ],
)
def test_request_validation_errors_are_422(client, auth_headers, method, path, payload, field):
    response = _send(client, method, path, auth_headers, payload)
    _assert_validation_error(response, field)


def test_unauthorized_without_token(client):
    response = client.get("/api/permission/projects/p1/members")
    assert response.status_code == 401
    assert response.json()["detail"] == "未提供认证 Token"


def test_invalid_token(client):
    response = client.get(
        "/api/permission/projects/p1/members",
        headers={"Authorization": "Bearer invalid_token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Token 无效或已过期"


def test_valid_token_hits_business_error_when_db_is_uninitialized(client, auth_headers):
    response = client.get(
        "/api/permission/projects/p1/members",
        headers=auth_headers,
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "数据库服务未初始化"


def test_health_check(client):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "business_backend_ok"


@pytest.mark.parametrize(
    ("method", "url", "payload"),
    [
        ("POST", "/api/permission/projects/p1/members", {"user_id": "u1"}),
        ("GET", "/api/permission/projects/p1/members", None),
        ("DELETE", "/api/permission/projects/p1/members/u2", None),
        ("PUT", "/api/permission/projects/p1/members/u1/roles", {"roles": ["PO"]}),
        ("POST", "/api/permission/requirements/r1/reviews", {"reviewer_id": "u1", "seq": 1}),
        ("GET", "/api/permission/requirements/r1/reviews", None),
        ("POST", "/api/permission/reviews/1/approve", {"comment": "ok"}),
        ("POST", "/api/permission/reviews/1/reject", {"comment": "no"}),
        ("POST", "/api/permission/reviews/1/withdraw", None),
        ("GET", "/api/permission/user/pending-reviews", None),
        ("POST", "/api/permission/projects/p1/baselines", {"version": "1.0.0", "locked": False}),
        ("GET", "/api/permission/projects/p1/baselines", None),
        ("POST", "/api/permission/baselines/1/lock", None),
        ("POST", "/api/permission/baselines/1/unlock", None),
        (
            "POST",
            "/api/permission/requirements/r1/change-requests",
            {"baseline_id": 1, "reason": "change", "change_summary": "summary"},
        ),
        ("GET", "/api/permission/requirements/r1/change-requests", None),
        ("POST", "/api/permission/change-requests/1/approve", {"review_comment": "ok"}),
        ("POST", "/api/permission/change-requests/1/reject", {"review_comment": "no"}),
        ("GET", "/api/permission/change-requests/pending", None),
        ("GET", "/api/permission/projects/p1/context", None),
    ],
)
def test_permission_endpoints_registered(client, auth_headers, method, url, payload):
    response = _send(client, method, url, auth_headers, payload)
    assert response.status_code == 500
    assert response.json()["detail"] == "数据库服务未初始化"


def test_invalid_include_roles_query_fails_with_422(client, auth_headers):
    response = client.get(
        "/api/permission/projects/p1/members?include_roles=abc",
        headers=auth_headers,
    )
    _assert_validation_error(response, "include_roles", loc_scope="query")


def test_invalid_include_locked_query_fails_with_422(client, auth_headers):
    response = client.get(
        "/api/permission/projects/p1/baselines?include_locked=abc",
        headers=auth_headers,
    )
    _assert_validation_error(response, "include_locked", loc_scope="query")
