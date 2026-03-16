"""
FastAPI strict contract tests for permission routes.
It ensures we do not keep compatibility coercions for legacy callers.
"""

import pytest

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

    @staticmethod
    def get_user_by_id(user_id):
        return {"user_id": user_id}

    @staticmethod
    def can_access_project(project_id, user_id, user):
        _ = project_id, user_id, user
        return True

    def list_project_members(self, project_id, include_roles=False):
        _ = project_id
        self.last_include_roles = include_roles
        return {"members": [], "total": 0}

    def list_project_baselines(self, project_id, include_locked=True):
        _ = project_id
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
async def fastapi_client(monkeypatch):
    stub = _StubPermissionDBService()
    monkeypatch.setattr(permission, "db_service", stub)

    app = build_test_app(permission.router)
    async with async_client(app) as client:
        yield client, stub


async def test_missing_token_uses_fastapi_error_shape(fastapi_client):
    client, _ = fastapi_client
    response = await client.get("/api/v2/permission/projects/p1/members")
    assert response.status_code == 401
    assert response.json()["detail"] == "未提供认证 Token"


async def test_invalid_token_uses_fastapi_error_shape(fastapi_client):
    client, _ = fastapi_client
    response = await client.get(
        "/api/v2/permission/projects/p1/members",
        headers={"Authorization": "Bearer invalid_token"},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Token 无效或已过期"


@pytest.mark.parametrize(
    ("method", "path", "payload", "field"),
    [
        ("post", "/api/v2/permission/projects/p1/members", None, "body"),
        ("post", "/api/v2/permission/projects/p1/members", {"user_id": ""}, "user_id"),
        ("put", "/api/v2/permission/projects/p1/members/u1/roles", None, "body"),
        ("put", "/api/v2/permission/projects/p1/members/u1/roles", {"roles": "PO"}, "roles"),
        ("post", "/api/v2/permission/requirements/r1/reviews", None, "body"),
        ("post", "/api/v2/permission/requirements/r1/reviews", {"seq": 1}, "reviewer_id"),
    ],
)
async def test_validation_errors_follow_fastapi_422(
    fastapi_client, method, path, payload, field
):
    client, _ = fastapi_client
    headers = _auth_headers()

    if payload is None:
        response = await getattr(client, method)(
            path,
            content="null",
            headers={**headers, "Content-Type": "application/json"},
        )
    else:
        response = await getattr(client, method)(path, json=payload, headers=headers)

    if field == "body":
        assert response.status_code == 422
        assert isinstance(response.json()["detail"], list)
    else:
        _assert_validation_error(response, field)


async def test_invalid_include_roles_is_rejected_instead_of_legacy_coercion(
    fastapi_client,
):
    client, stub = fastapi_client
    response = await client.get(
        "/api/v2/permission/projects/p1/members?include_roles=abc",
        headers=_auth_headers(),
    )
    _assert_validation_error(response, "include_roles", scope="query")
    assert stub.last_include_roles is None


async def test_invalid_include_locked_is_rejected_instead_of_legacy_coercion(
    fastapi_client,
):
    client, stub = fastapi_client
    response = await client.get(
        "/api/v2/permission/projects/p1/baselines?include_locked=abc",
        headers=_auth_headers(),
    )
    _assert_validation_error(response, "include_locked", scope="query")
    assert stub.last_include_locked is None


async def test_valid_bool_query_values_are_forwarded(fastapi_client):
    client, stub = fastapi_client
    headers = _auth_headers()

    members_resp = await client.get(
        "/api/v2/permission/projects/p1/members?include_roles=true",
        headers=headers,
    )
    baselines_resp = await client.get(
        "/api/v2/permission/projects/p1/baselines?include_locked=false",
        headers=headers,
    )

    assert members_resp.status_code == 200
    assert baselines_resp.status_code == 200
    assert stub.last_include_roles is True
    assert stub.last_include_locked is False
