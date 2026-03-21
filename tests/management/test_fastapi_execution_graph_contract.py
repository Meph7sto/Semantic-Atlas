"""
FastAPI execution-topology route contract tests.
"""

from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError


from backend_business.api.http.errors import (
    error_response_handler,
    validation_error_handler,
)
from backend_business.api.routers import execution_graph


class _FakeContainerObj:
    def __init__(self, container_id: str, label: str):
        self.container_id = container_id
        self.label = label

    def to_dict(self):
        return {"container_id": self.container_id, "label": self.label}


class _FakeEdgeObj:
    def __init__(self, source: str, target: str):
        self.source = source
        self.target = target

    def to_dict(self):
        return {"source": self.source, "target": self.target}


class _FakeStructure:
    def __init__(self, graph_id: str):
        self.graph_id = graph_id
        self.graph_name = "demo-graph"
        self.containers = [_FakeContainerObj("c1", "A"), _FakeContainerObj("c2", "B")]
        self.edges = [_FakeEdgeObj("c1", "c2")]
        self.start_containers = [self.containers[0]]
        self.end_containers = [self.containers[1]]
        self.validation_status = "unknown"
        self.validation_errors = []


class _FakeValidation:
    def __init__(self):
        self.is_valid = True
        self.errors: list[str] = []
        self.warnings: list[str] = []


class _FakeGraphStructureBuilder:
    def __init__(self, _db_service):
        pass

    def load_topology(self, graph_id: str, graph: dict, nodes: list, edges: list, containers: list):
        _ = graph, nodes, edges, containers
        return _FakeStructure(graph_id)


class _FakeStructureValidator:
    def validate(self, _structure):
        return _FakeValidation()


class _FakeTopologySerializer:
    def export_for_agent(self, structure: _FakeStructure):
        return {
            "graph_id": structure.graph_id,
            "container_count": len(structure.containers),
            "edge_count": len(structure.edges),
        }


class _StubExecutionGraphService:
    def __init__(self):
        self.last_create_graph: tuple[str, str] | None = None
        self.last_update_status: str | None = None
        self.last_actor: str | None = None
        self.last_node_filter_graph: str | None = None

    def create_execution_graph(self, project_id: str, name: str, description: str, created_by: str):
        self.last_create_graph = (project_id, name)
        self.last_actor = created_by
        return {
            "graph_id": "g-new",
            "project_id": project_id,
            "name": name,
            "description": description,
            "status": "draft",
            "created_by": created_by,
        }

    def list_execution_graphs(self, project_id: str):
        return [{"graph_id": "g1", "project_id": project_id}]

    def get_execution_graph(self, graph_id: str):
        if graph_id.startswith("missing"):
            return None
        return {"graph_id": graph_id, "name": "graph-name"}

    def update_execution_graph(
        self,
        graph_id: str,
        name: str | None = None,
        description: str | None = None,
        status: str | None = None,
        layout_json: dict[str, Any] | None = None,
        meta_json: dict[str, Any] | None = None,
        updated_by: str = "system",
    ):
        _ = description, layout_json, meta_json
        if graph_id.startswith("missing"):
            return None
        self.last_update_status = status
        self.last_actor = updated_by
        return {"graph_id": graph_id, "name": name or "name", "status": status or "draft"}

    def delete_execution_graph(self, graph_id: str, updated_by: str):
        _ = updated_by
        return not graph_id.startswith("missing")

    def create_container(
        self,
        graph_id: str,
        container_key: str,
        label: str,
        role_type: str,
        config_json: dict[str, Any] | None,
        order_index: int,
        created_by: str,
    ):
        _ = graph_id, config_json, order_index
        self.last_actor = created_by
        return {"container_id": "c-new", "container_key": container_key, "label": label, "role_type": role_type}

    def update_container(
        self,
        container_id: str,
        label: str | None = None,
        role_type: str | None = None,
        config_json: dict[str, Any] | None = None,
        order_index: int | None = None,
        updated_by: str = "system",
    ):
        _ = config_json, order_index, updated_by
        if container_id.startswith("missing"):
            return None
        return {"container_id": container_id, "label": label or "label", "role_type": role_type or "human"}

    def delete_container(self, container_id: str, updated_by: str):
        _ = updated_by
        return not container_id.startswith("missing")

    def create_node(
        self,
        graph_id: str,
        node_key: str,
        label: str,
        node_type: str,
        role_type: str,
        container_id: str | None,
        config_json: dict[str, Any] | None,
        input_schema_json: list[Any] | None,
        output_schema_json: list[Any] | None,
        order_index: int,
        created_by: str,
    ):
        _ = graph_id, container_id, config_json, input_schema_json, output_schema_json, order_index, created_by
        return {"node_id": "n-new", "node_key": node_key, "label": label, "node_type": node_type, "role_type": role_type}

    def update_node(
        self,
        node_id: str,
        container_id: str | None = None,
        label: str | None = None,
        node_type: str | None = None,
        role_type: str | None = None,
        config_json: dict[str, Any] | None = None,
        input_schema_json: list[Any] | None = None,
        output_schema_json: list[Any] | None = None,
        order_index: int | None = None,
        updated_by: str = "system",
    ):
        _ = container_id, config_json, input_schema_json, output_schema_json, order_index, updated_by
        if node_id.startswith("missing"):
            return None
        return {"node_id": node_id, "label": label or "node", "node_type": node_type or "node", "role_type": role_type or "human"}

    def delete_node(self, node_id: str, updated_by: str):
        _ = updated_by
        return not node_id.startswith("missing")

    def create_edge(
        self,
        graph_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        label: str | None = None,
        condition_expr: str | None = None,
        config_json: dict[str, Any] | None = None,
        order_index: int = 0,
        created_by: str = "system",
    ):
        _ = graph_id, condition_expr, config_json, order_index, created_by
        return {"edge_id": "e-new", "source_node_id": source_node_id, "target_node_id": target_node_id, "edge_type": edge_type, "label": label}

    def update_edge(
        self,
        edge_id: str,
        label: str | None = None,
        edge_type: str | None = None,
        condition_expr: str | None = None,
        config_json: dict[str, Any] | None = None,
        order_index: int | None = None,
        updated_by: str = "system",
    ):
        _ = condition_expr, config_json, order_index, updated_by
        if edge_id.startswith("missing"):
            return None
        return {"edge_id": edge_id, "label": label, "edge_type": edge_type or "call"}

    def delete_edge(self, edge_id: str, updated_by: str):
        _ = updated_by
        return not edge_id.startswith("missing")

    def get_graph_detail(self, graph_id: str):
        if graph_id.startswith("missing"):
            return {"graph": None, "containers": [], "nodes": [], "edges": []}
        return {"graph": {"graph_id": graph_id}, "containers": [{"container_id": "c1"}], "nodes": [{"node_id": "n1"}], "edges": [{"edge_id": "e1"}]}

    def list_execution_nodes(self, graph_id: str):
        self.last_node_filter_graph = graph_id
        return [
            {"node_id": "n1", "container_id": "c1", "node_type": "start"},
            {"node_id": "n2", "container_id": "c2", "node_type": "end"},
        ]

    def list_execution_containers(self, graph_id: str):
        _ = graph_id
        return [
            {"container_id": "c1", "role_type": "human"},
            {"container_id": "c2", "role_type": "agent"},
        ]

    def list_execution_edges(self, graph_id: str):
        _ = graph_id
        return [{"edge_id": "e1"}]


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub_service = _StubExecutionGraphService()
    monkeypatch.setattr(execution_graph, "_service", stub_service)
    monkeypatch.setattr(execution_graph, "GraphStructureBuilder", _FakeGraphStructureBuilder)
    monkeypatch.setattr(execution_graph, "StructureValidator", _FakeStructureValidator)
    monkeypatch.setattr(execution_graph, "TopologyStructureSerializer", _FakeTopologySerializer)

    app = build_test_app(execution_graph.router)
    app.dependency_overrides[execution_graph.get_current_user] = lambda: {
        "user_id": "tester",
        "role": "admin",
    }

    async with async_client(app) as client:
        yield client, stub_service


async def test_graph_crud_contract(fastapi_client):
    client, stub_service = fastapi_client

    create_resp = await client.post(
        "/api/v2/execution-topology/projects/p1",
        json={"name": "main-graph", "description": "desc"},
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["graph_id"] == "g-new"
    assert stub_service.last_create_graph == ("p1", "main-graph")
    assert stub_service.last_actor == "tester"

    list_resp = await client.get("/api/v2/execution-topology/projects/p1")
    assert list_resp.status_code == 200
    assert list_resp.json()["graphs"][0]["project_id"] == "p1"

    get_resp = await client.get("/api/v2/execution-topology/g1")
    assert get_resp.status_code == 200
    assert get_resp.json()["graph_id"] == "g1"

    get_missing_resp = await client.get("/api/v2/execution-topology/missing-g")
    assert get_missing_resp.status_code == 404

    update_resp = await client.patch(
        "/api/v2/execution-topology/g1",
        json={"name": "after", "status": "ACTIVE"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["status"] == "active"
    assert stub_service.last_update_status == "active"

    delete_resp = await client.delete("/api/v2/execution-topology/g1")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["message"] == "删除成功"


async def test_container_crud_contract(fastapi_client):
    client, _ = fastapi_client

    create_resp = await client.post(
        "/api/v2/execution-topology/g1/containers",
        json={
            "container_key": "runtime",
            "label": "Runtime",
            "role_type": "AGENT",
        },
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["container_id"] == "c-new"
    assert create_resp.json()["role_type"] == "agent"

    update_resp = await client.patch(
        "/api/v2/execution-topology/containers/c1",
        json={"label": "Runtime-2"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["container_id"] == "c1"

    update_missing_resp = await client.patch(
        "/api/v2/execution-topology/containers/missing-c",
        json={"label": "x"},
    )
    assert update_missing_resp.status_code == 404

    delete_resp = await client.delete("/api/v2/execution-topology/containers/c1")
    assert delete_resp.status_code == 200


async def test_node_crud_and_validation_contract(fastapi_client):
    client, _ = fastapi_client

    invalid_resp = await client.post(
        "/api/v2/execution-topology/g1/nodes",
        json={
            "label": "bad",
            "node_key": "",
            "node_type": "node",
            "role_type": "agent",
        },
    )
    assert invalid_resp.status_code == 422

    create_resp = await client.post(
        "/api/v2/execution-topology/g1/nodes",
        json={
            "node_key": "n1",
            "label": "Node 1",
            "node_type": "LLM",
            "role_type": "HUMAN",
            "input_schema_json": [
                {"field": "anchor", "type": "string"},
            ],
            "output_schema_json": [
                {"field": "summary", "type": "object"},
            ],
        },
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["node_type"] == "llm"
    assert create_resp.json()["role_type"] == "human"

    update_resp = await client.patch(
        "/api/v2/execution-topology/nodes/n1",
        json={"node_type": "END"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["node_type"] == "end"

    delete_missing_resp = await client.delete("/api/v2/execution-topology/nodes/missing-n")
    assert delete_missing_resp.status_code == 404


async def test_edge_crud_contract(fastapi_client):
    client, _ = fastapi_client

    create_resp = await client.post(
        "/api/v2/execution-topology/g1/edges",
        json={
            "source_node_id": "n1",
            "target_node_id": "n2",
            "edge_type": "CALL",
        },
    )
    assert create_resp.status_code == 200
    assert create_resp.json()["edge_type"] == "call"

    update_resp = await client.patch(
        "/api/v2/execution-topology/edges/e1",
        json={"edge_type": "RETRY", "label": "retry-edge"},
    )
    assert update_resp.status_code == 200
    assert update_resp.json()["edge_type"] == "retry"

    delete_resp = await client.delete("/api/v2/execution-topology/edges/e1")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["message"] == "删除成功"


async def test_detail_structure_validate_and_export_contract(fastapi_client):
    client, stub_service = fastapi_client

    detail_resp = await client.get("/api/v2/execution-topology/g1/detail")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["graph"]["graph_id"] == "g1"

    structure_resp = await client.get("/api/v2/execution-topology/g1/structure")
    assert structure_resp.status_code == 200
    structure = structure_resp.json()["structure"]
    assert structure["validation_status"] == "valid"
    assert structure["start_containers"] == ["c1"]
    assert structure["end_containers"] == ["c2"]

    validate_resp = await client.post("/api/v2/execution-topology/g1/validate")
    assert validate_resp.status_code == 200
    result = validate_resp.json()["result"]
    assert result["is_valid"] is True
    assert result["errors"] == []

    container_filter_resp = await client.get(
        "/api/v2/execution-topology/g1/containers?role_type=agent&node_type=end"
    )
    assert container_filter_resp.status_code == 200
    containers = container_filter_resp.json()["containers"]
    assert len(containers) == 1
    assert containers[0]["container_id"] == "c2"
    assert stub_service.last_node_filter_graph == "g1"

    export_resp = await client.get("/api/v2/execution-topology/g1/export?format=json")
    assert export_resp.status_code == 200
    assert export_resp.json()["exported"]["graph_id"] == "g1"

    export_bad_resp = await client.get("/api/v2/execution-topology/g1/export?format=yaml")
    assert export_bad_resp.status_code == 400
    assert "Only 'json' format is supported" in export_bad_resp.json()["detail"]
