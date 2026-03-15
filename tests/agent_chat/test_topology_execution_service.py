"""
Tests for topology template execution service.
"""

from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.execution.topology_execution_service import (
    TopologyExecutionService,
)


class _StubExecutionGraphService:
    def __init__(self, detail: dict):
        self._detail_by_graph_id = {detail["graph"]["graph_id"]: detail}
        self.runtime_graphs: dict[str, dict] = {}
        self._runtime_index = 0

    def get_graph_detail(self, graph_id: str, include_deleted: bool = False):
        if graph_id in self.runtime_graphs:
            return self.runtime_graphs[graph_id]
        return self._detail_by_graph_id.get(graph_id)

    def create_runtime_graph(
        self,
        project_id: str,
        name: str,
        description: str = "",
        created_by: str = "",
        meta_json: dict | None = None,
        layout_json: dict | None = None,
        status: str = "running",
    ):
        self._runtime_index += 1
        graph_id = f"runtime-{self._runtime_index}"
        graph = {
            "graph_id": graph_id,
            "project_id": project_id,
            "name": name,
            "description": description,
            "graph_type": "agent_runtime_execution",
            "status": status,
            "layout_json": layout_json,
            "meta_json": meta_json or {},
        }
        self.runtime_graphs[graph_id] = {
            "graph": graph,
            "containers": [],
            "nodes": [],
            "edges": [],
        }
        return graph

    def create_container(
        self,
        graph_id: str,
        container_key: str,
        label: str,
        role_type: str,
        config_json: dict | None = None,
        order_index: int = 0,
        created_by: str = "",
    ):
        container = {
            "container_id": f"{graph_id}-container-{len(self.runtime_graphs[graph_id]['containers']) + 1}",
            "graph_id": graph_id,
            "container_key": container_key,
            "label": label,
            "role_type": role_type,
            "config_json": config_json or {},
            "order_index": order_index,
        }
        self.runtime_graphs[graph_id]["containers"].append(container)
        return container

    def create_node(
        self,
        graph_id: str,
        node_key: str,
        label: str,
        node_type: str,
        role_type: str,
        container_id: str | None = None,
        config_json: dict | None = None,
        input_schema_json: list | None = None,
        output_schema_json: list | None = None,
        order_index: int = 0,
        created_by: str = "",
    ):
        node = {
            "node_id": f"{graph_id}-node-{len(self.runtime_graphs[graph_id]['nodes']) + 1}",
            "graph_id": graph_id,
            "container_id": container_id,
            "node_key": node_key,
            "label": label,
            "node_type": node_type,
            "role_type": role_type,
            "config_json": config_json or {},
            "input_schema_json": input_schema_json or [],
            "output_schema_json": output_schema_json or [],
            "order_index": order_index,
        }
        self.runtime_graphs[graph_id]["nodes"].append(node)
        return node

    def create_edge(
        self,
        graph_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        label: str | None = None,
        condition_expr: str | None = None,
        config_json: dict | None = None,
        order_index: int = 0,
        created_by: str = "",
    ):
        edge = {
            "edge_id": f"{graph_id}-edge-{len(self.runtime_graphs[graph_id]['edges']) + 1}",
            "graph_id": graph_id,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "edge_type": edge_type,
            "label": label,
            "condition_expr": condition_expr,
            "config_json": config_json or {},
            "order_index": order_index,
        }
        self.runtime_graphs[graph_id]["edges"].append(edge)
        return edge

    def update_node(
        self,
        node_id: str,
        container_id: str | None = None,
        label: str | None = None,
        node_type: str | None = None,
        role_type: str | None = None,
        config_json: dict | None = None,
        input_schema_json: list | None = None,
        output_schema_json: list | None = None,
        order_index: int | None = None,
        updated_by: str = "",
    ):
        for detail in self.runtime_graphs.values():
            for node in detail["nodes"]:
                if node["node_id"] != node_id:
                    continue
                if container_id is not None:
                    node["container_id"] = container_id
                if label is not None:
                    node["label"] = label
                if node_type is not None:
                    node["node_type"] = node_type
                if role_type is not None:
                    node["role_type"] = role_type
                if config_json is not None:
                    node["config_json"] = config_json
                if input_schema_json is not None:
                    node["input_schema_json"] = input_schema_json
                if output_schema_json is not None:
                    node["output_schema_json"] = output_schema_json
                if order_index is not None:
                    node["order_index"] = order_index
                return node
        raise AssertionError(f"node not found: {node_id}")

    def patch_graph_meta(
        self,
        graph_id: str,
        meta_patch: dict,
        status: str | None = None,
        updated_by: str = "",
    ):
        graph = self.runtime_graphs[graph_id]["graph"]
        graph["meta_json"] = {
            **(graph.get("meta_json") or {}),
            **(meta_patch or {}),
        }
        if status is not None:
            graph["status"] = status
        return graph


def _build_template_detail(*, handoff: bool = False, approved: bool = True) -> dict:
    graph = {
        "graph_id": "template-1",
        "project_id": "project-1",
        "name": "Topology Template",
        "description": "demo",
        "graph_type": "execution_topology_template",
        "status": "draft",
        "layout_json": {},
        "meta_json": {},
    }
    containers = [
        {
            "container_id": "container-1",
            "graph_id": "template-1",
            "container_key": "planner",
            "label": "Planner",
            "role_type": "agent",
            "config_json": {},
            "order_index": 0,
        }
    ]
    nodes = [
        {
            "node_id": "node-start",
            "graph_id": "template-1",
            "container_id": "container-1",
            "node_key": "start",
            "label": "Start",
            "node_type": "start",
            "role_type": "agent",
            "config_json": {},
            "input_schema_json": [],
            "output_schema_json": [],
            "order_index": 0,
        },
        {
            "node_id": "node-plan",
            "graph_id": "template-1",
            "container_id": "container-1",
            "node_key": "plan",
            "label": "Plan",
            "node_type": "llm",
            "role_type": "agent",
            "config_json": {"output": {"approved": approved, "message": "planned"}},
            "input_schema_json": [],
            "output_schema_json": [],
            "order_index": 1,
        },
    ]
    edges = [
        {
            "edge_id": "edge-1",
            "graph_id": "template-1",
            "source_node_id": "node-start",
            "target_node_id": "node-plan",
            "edge_type": "call",
            "label": "start->plan",
            "condition_expr": None,
            "config_json": {},
            "order_index": 0,
        }
    ]

    if handoff:
        nodes.extend(
            [
                {
                    "node_id": "node-handoff",
                    "graph_id": "template-1",
                    "container_id": "container-1",
                    "node_key": "clarify",
                    "label": "Clarify",
                    "node_type": "handoff",
                    "role_type": "human",
                    "config_json": {"message": "need approval"},
                    "input_schema_json": [],
                    "output_schema_json": [],
                    "order_index": 2,
                },
                {
                    "node_id": "node-end",
                    "graph_id": "template-1",
                    "container_id": "container-1",
                    "node_key": "finish",
                    "label": "Finish",
                    "node_type": "end",
                    "role_type": "agent",
                    "config_json": {"output": {"status": "done"}},
                    "input_schema_json": [],
                    "output_schema_json": [],
                    "order_index": 3,
                },
            ]
        )
        edges.extend(
            [
                {
                    "edge_id": "edge-2",
                    "graph_id": "template-1",
                    "source_node_id": "node-plan",
                    "target_node_id": "node-handoff",
                    "edge_type": "call",
                    "label": "plan->handoff",
                    "condition_expr": "approved == False",
                    "config_json": {},
                    "order_index": 1,
                },
                {
                    "edge_id": "edge-3",
                    "graph_id": "template-1",
                    "source_node_id": "node-plan",
                    "target_node_id": "node-end",
                    "edge_type": "call",
                    "label": "plan->end",
                    "condition_expr": "approved == True",
                    "config_json": {},
                    "order_index": 2,
                },
            ]
        )
    else:
        nodes.append(
            {
                "node_id": "node-end",
                "graph_id": "template-1",
                "container_id": "container-1",
                "node_key": "finish",
                "label": "Finish",
                "node_type": "end",
                "role_type": "agent",
                "config_json": {"output": {"status": "done"}},
                "input_schema_json": [],
                "output_schema_json": [],
                "order_index": 2,
            }
        )
        edges.append(
            {
                "edge_id": "edge-2",
                "graph_id": "template-1",
                "source_node_id": "node-plan",
                "target_node_id": "node-end",
                "edge_type": "call",
                "label": "plan->end",
                "condition_expr": "approved == True",
                "config_json": {},
                "order_index": 1,
            }
        )

    return {
        "graph": graph,
        "containers": containers,
        "nodes": nodes,
        "edges": edges,
    }


def test_execute_template_creates_runtime_graph_and_completes():
    stub = _StubExecutionGraphService(_build_template_detail())
    service = TopologyExecutionService(execution_graph_service=stub)

    result = service.execute_template(
        template_graph_id="template-1",
        input_payload={"request": "plan feature"},
        actor="tester",
    )

    assert result["status"] == "succeeded"
    assert result["runtime_graph"]["graph_type"] == "agent_runtime_execution"
    assert result["runtime_graph"]["meta_json"]["template_graph_id"] == "template-1"
    assert result["final_output"] == {"status": "done"}
    assert [entry["node_key"] for entry in result["trace"]] == ["start", "plan", "finish"]


def test_execute_template_suspends_on_handoff():
    stub = _StubExecutionGraphService(_build_template_detail(handoff=True, approved=False))
    service = TopologyExecutionService(execution_graph_service=stub)

    result = service.execute_template(
        template_graph_id="template-1",
        input_payload={"request": "need manual confirm"},
        actor="tester",
    )

    assert result["status"] == "suspended"
    assert result["suspended_node"]["node_key"] == "clarify"
    assert result["runtime_graph"]["status"] == "suspended"
    assert result["trace"][-1]["node_type"] == "handoff"


def test_execute_template_rejects_multiple_start_nodes_before_creating_runtime_graph():
    detail = _build_template_detail()
    detail["nodes"].insert(
        1,
        {
            "node_id": "node-start-2",
            "graph_id": "template-1",
            "container_id": "container-1",
            "node_key": "start_2",
            "label": "Start 2",
            "node_type": "start",
            "role_type": "agent",
            "config_json": {},
            "input_schema_json": [],
            "output_schema_json": [],
            "order_index": 1,
        },
    )
    stub = _StubExecutionGraphService(detail)
    service = TopologyExecutionService(execution_graph_service=stub)

    try:
        service.execute_template(
            template_graph_id="template-1",
            input_payload={"request": "plan feature"},
            actor="tester",
        )
    except ValueError as exc:
        assert "单一 start 节点" in str(exc)
    else:
        raise AssertionError("expected ValueError for multiple start nodes")

    assert stub.runtime_graphs == {}


def test_execute_template_marks_runtime_graph_failed_when_condition_variables_are_missing():
    detail = _build_template_detail()
    detail["nodes"][1]["config_json"] = {"output": {"message": "planned"}}
    stub = _StubExecutionGraphService(detail)
    service = TopologyExecutionService(execution_graph_service=stub)

    try:
        service.execute_template(
            template_graph_id="template-1",
            input_payload={"request": "plan feature"},
            actor="tester",
        )
    except ValueError as exc:
        assert "Undefined variable" in str(exc)
    else:
        raise AssertionError("expected ValueError for missing condition variable")

    assert len(stub.runtime_graphs) == 1
    runtime_detail = next(iter(stub.runtime_graphs.values()))
    assert runtime_detail["graph"]["status"] == "failed"
    assert "Undefined variable" in runtime_detail["graph"]["meta_json"]["error"]


def test_execute_template_prefers_matching_condition_before_default_edge():
    detail = _build_template_detail()
    detail["nodes"].insert(
        2,
        {
            "node_id": "node-default-end",
            "graph_id": "template-1",
            "container_id": "container-1",
            "node_key": "fallback",
            "label": "Fallback",
            "node_type": "end",
            "role_type": "agent",
            "config_json": {"output": {"status": "fallback"}},
            "input_schema_json": [],
            "output_schema_json": [],
            "order_index": 2,
        },
    )
    detail["nodes"][-1]["order_index"] = 3
    detail["edges"] = [
        detail["edges"][0],
        {
            "edge_id": "edge-default",
            "graph_id": "template-1",
            "source_node_id": "node-plan",
            "target_node_id": "node-default-end",
            "edge_type": "call",
            "label": "plan->fallback",
            "condition_expr": None,
            "config_json": {},
            "order_index": 0,
        },
        {
            "edge_id": "edge-approved",
            "graph_id": "template-1",
            "source_node_id": "node-plan",
            "target_node_id": "node-end",
            "edge_type": "call",
            "label": "plan->end",
            "condition_expr": "approved == True",
            "config_json": {},
            "order_index": 1,
        },
    ]
    stub = _StubExecutionGraphService(detail)
    service = TopologyExecutionService(execution_graph_service=stub)

    result = service.execute_template(
        template_graph_id="template-1",
        input_payload={"request": "plan feature"},
        actor="tester",
    )

    assert result["status"] == "succeeded"
    assert result["final_output"] == {"status": "done"}
    assert [entry["node_key"] for entry in result["trace"]] == ["start", "plan", "finish"]
