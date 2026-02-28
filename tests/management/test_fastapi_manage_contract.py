"""
FastAPI manage route contract tests.

Focus on migrated behavior and FastAPI validation semantics.
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
from backend_business.api.routers import manage
from backend_business.services.auth_service import get_auth_service


class _StubManageService:
    def __init__(self):
        self.last_set_project_session = None
        self.last_update_project_info = None
        self.last_tree_args = None

    def add_audit_log(self, **kwargs):
        return kwargs

    def set_project_session(self, project_id, session_id, updated_by=""):
        self.last_set_project_session = (project_id, session_id, updated_by)
        return {
            "project_id": project_id,
            "name": "project",
            "description": "",
            "status": "active",
            "current_session_id": session_id,
        }

    def update_project_info(self, project_id, name=None, description=None, updated_by=""):
        self.last_update_project_info = (project_id, name, description, updated_by)
        return {
            "project_id": project_id,
            "name": name or "project",
            "description": description or "",
            "status": "active",
            "current_session_id": None,
        }

    def get_requirement_tree(self, project_id, include_deleted=False):
        self.last_tree_args = (project_id, include_deleted)
        return [], []

    def list_requirements(self, project_id, include_deleted=False):
        return []


def _auth_headers() -> dict:
    token = get_auth_service().generate_token(
        user_id="manage-contract-user",
        username="manage-contract-user",
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
    stub = _StubManageService()
    monkeypatch.setattr(manage, "_service", stub)

    app = FastAPI()
    app.include_router(manage.router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub


def test_update_project_current_session_id_uses_set_project_session(fastapi_client):
    client, stub = fastapi_client
    response = client.patch(
        "/api/manage/projects/p1",
        json={"current_session_id": "s-1"},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json()["current_session_id"] == "s-1"
    assert stub.last_set_project_session == ("p1", "s-1", "manage-contract-user")
    assert stub.last_update_project_info is None


def test_update_project_null_current_session_id_is_supported(fastapi_client):
    client, stub = fastapi_client
    response = client.patch(
        "/api/manage/projects/p1",
        json={"current_session_id": None},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert stub.last_set_project_session == ("p1", None, "manage-contract-user")
    assert stub.last_update_project_info is None


def test_update_project_name_uses_update_project_info(fastapi_client):
    client, stub = fastapi_client
    response = client.patch(
        "/api/manage/projects/p1",
        json={"name": "New Name"},
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert stub.last_update_project_info == ("p1", "New Name", None, "manage-contract-user")
    assert stub.last_set_project_session is None


def test_update_project_empty_payload_returns_400(fastapi_client):
    client, _ = fastapi_client
    response = client.patch(
        "/api/manage/projects/p1",
        json={},
        headers=_auth_headers(),
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "No updatable fields provided"


def test_create_project_missing_name_returns_422(fastapi_client):
    client, _ = fastapi_client
    response = client.post(
        "/api/manage/projects",
        json={"description": "x"},
        headers=_auth_headers(),
    )
    _assert_validation_error(response, "name")


def test_list_requirements_invalid_tree_query_returns_422(fastapi_client):
    client, _ = fastapi_client
    response = client.get("/api/manage/projects/p1/requirements?tree=abc", headers=_auth_headers())
    _assert_validation_error(response, "tree", scope="query")


def test_list_requirements_tree_mode_calls_tree_service(fastapi_client):
    client, stub = fastapi_client
    response = client.get(
        "/api/manage/projects/p1/requirements?tree=true&include_deleted=true",
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    assert response.json() == {"tree": [], "orphans": []}
    assert stub.last_tree_args == ("p1", True)
