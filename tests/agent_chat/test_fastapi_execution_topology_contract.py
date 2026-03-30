"""
FastAPI contract tests for execution topology runtime execution endpoint.
"""

from __future__ import annotations


import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError


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
async def fastapi_client(monkeypatch):
    stub = _StubTopologyExecutionService()
    monkeypatch.setattr(execution_graph, "_topology_execution_service", stub)

    app = build_test_app(execution_graph.router)

    async with async_client(app) as client:
        yield client, stub


async def test_execute_topology_returns_runtime_execution_result(fastapi_client):
    client, stub = fastapi_client

    response = await client.post(
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


async def test_execute_topology_rejects_invalid_max_steps(fastapi_client):
    client, _ = fastapi_client

    response = await client.post(
        "/api/v2/execution-topology/template-1/execute",
        json={"max_steps": 0},
        headers=_auth_headers(),
    )

    assert response.status_code == 422
