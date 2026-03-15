"""
FastAPI contract tests for execution topology runtime execution endpoint.
"""

from __future__ import annotations

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
from backend_business.api.routers import execution_graph
from backend_business.services.auth_service import get_auth_service


class _StubTopologyExecutionService:
    def __init__(self):
        self.last_execute_args = None

    def execute_template(
        self,
        *,
        template_graph_id: str,
        input_payload: dict | None,
        actor: str,
        max_steps: int = 100,
        runtime_graph_name: str | None = None,
        runtime_graph_description: str | None = None,
    ):
        self.last_execute_args = {
            "template_graph_id": template_graph_id,
            "input_payload": input_payload,
            "actor": actor,
            "max_steps": max_steps,
            "runtime_graph_name": runtime_graph_name,
            "runtime_graph_description": runtime_graph_description,
        }
        return {
            "status": "succeeded",
            "runtime_graph": {
                "graph_id": "runtime-1",
                "graph_type": "agent_runtime_execution",
                "status": "succeeded",
            },
            "final_output": {"ok": True},
            "trace": [],
            "suspended_node": None,
        }


def _auth_headers() -> dict:
    token = get_auth_service().generate_token(
        user_id="topology-contract-user",
        username="topology-contract-user",
        role="member",
        external_type=None,
    )
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def fastapi_client(monkeypatch):
    stub = _StubTopologyExecutionService()
    monkeypatch.setattr(execution_graph, "_topology_execution_service", stub)

    app = FastAPI()
    app.include_router(execution_graph.router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub


def test_execute_topology_returns_runtime_execution_result(fastapi_client):
    client, stub = fastapi_client

    response = client.post(
        "/api/v2/execution-topology/template-1/execute",
        json={
            "input_payload": {"message": "run this topology"},
            "max_steps": 12,
            "runtime_graph_name": "Runtime Demo",
        },
        headers=_auth_headers(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "succeeded"
    assert body["runtime_graph"]["graph_id"] == "runtime-1"
    assert stub.last_execute_args == {
        "template_graph_id": "template-1",
        "input_payload": {"message": "run this topology"},
        "actor": "topology-contract-user",
        "max_steps": 12,
        "runtime_graph_name": "Runtime Demo",
        "runtime_graph_description": None,
    }


def test_execute_topology_rejects_invalid_max_steps(fastapi_client):
    client, _ = fastapi_client

    response = client.post(
        "/api/v2/execution-topology/template-1/execute",
        json={"max_steps": 0},
        headers=_auth_headers(),
    )

    assert response.status_code == 422
