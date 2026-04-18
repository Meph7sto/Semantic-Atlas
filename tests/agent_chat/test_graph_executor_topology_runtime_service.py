"""Tests for the REST GraphExecutor adapter service."""

from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.execution.graph_executor import ExecutionResult
from backend_business.services.agent.execution.graph_executor_topology_service import (
    GraphExecutorTopologyRuntimeService,
)
from backend_business.services.agent.runtime.state_contract import (
    RUN_STATE_SOURCE_OF_TRUTH,
    SCRATCHPAD_STATE_BACKEND,
)


class _StubGraphService:
    def __init__(self) -> None:
        self.graphs = {
            "template-1": {
                "graph_id": "template-1",
                "project_id": "proj-1",
                "name": "Template",
                "description": "Template Description",
                "graph_type": "execution_topology_template",
                "status": "draft",
            },
            "runtime-1": {
                "graph_id": "runtime-1",
                "project_id": "proj-1",
                "name": "Runtime Demo",
                "description": "Runtime Description",
                "graph_type": "agent_runtime_execution",
                "status": "succeeded",
                "meta_json": {},
            },
        }
        self._detail = {
            "graph": self.graphs["template-1"],
            "containers": [
                {
                    "container_id": "c-1",
                    "container_key": "main",
                    "label": "Main",
                    "role_type": "agent",
                    "config_json": {},
                    "order_index": 0,
                }
            ],
            "nodes": [],
            "edges": [],
            "subgraphs": [],
        }
        self.created_containers = []

    def get_graph_detail(self, graph_id: str):
        if graph_id == "template-1":
            return self._detail
        return {
            "graph": self.graphs.get(graph_id),
            "containers": [],
            "nodes": [],
            "edges": [],
            "subgraphs": [],
        }

    def get_execution_graph(self, graph_id: str):
        return self.graphs.get(graph_id)

    def create_runtime_graph(
        self,
        *,
        project_id,
        name,
        description="",
        created_by="",
        meta_json=None,
        status="running",
    ):
        _ = created_by
        graph = self.graphs["runtime-1"]
        graph.update(
            {
                "project_id": project_id,
                "name": name,
                "description": description,
                "meta_json": meta_json or {},
                "status": status,
            }
        )
        return graph

    def create_container(
        self,
        *,
        graph_id,
        container_key,
        label,
        role_type,
        config_json=None,
        order_index=0,
        created_by="",
    ):
        _ = config_json, created_by
        container = {
            "container_id": f"{container_key}-runtime",
            "graph_id": graph_id,
            "container_key": container_key,
            "label": label,
            "role_type": role_type,
            "order_index": order_index,
        }
        self.created_containers.append(container)
        return container


class _StubExecutor:
    def __init__(self) -> None:
        self.last_execute_kwargs = None

    def execute(self, **kwargs):
        self.last_execute_kwargs = kwargs
        if False:
            yield {}
        return ExecutionResult(
            status="succeeded",
            graph_id="runtime-1",
            final_output="done",
        )


def test_execute_template_routes_rest_execution_through_graph_executor():
    graph_service = _StubGraphService()
    executor = _StubExecutor()
    service = GraphExecutorTopologyRuntimeService(
        execution_graph_service=graph_service,
        graph_executor=executor,
        ai_proxy_client=object(),
    )

    result = service.execute_template(
        template_graph_id="template-1",
        input_payload={
            "message": "run this topology",
            "approval_id": "ap-1",
        },
        actor="tester",
        max_steps=12,
        runtime_graph_name="Runtime Demo",
        runtime_graph_description="Runtime Description",
    )

    assert result["status"] == "succeeded"
    assert result["runtime_graph"]["graph_id"] == "runtime-1"
    assert result["final_output"] == "done"
    assert executor.last_execute_kwargs["template_graph_id"] == "template-1"
    assert executor.last_execute_kwargs["project_id"] == "proj-1"
    assert executor.last_execute_kwargs["user_message"] == (
        "run this topology\n\n附加输入:\n{\n"
        '  "approval_id": "ap-1"\n'
        "}"
    )
    assert executor.last_execute_kwargs["runtime_graph_id"] == "runtime-1"
    assert graph_service.created_containers == []
    assert result["runtime_graph"]["meta_json"]["scratchpad_state_backend"] == (
        SCRATCHPAD_STATE_BACKEND
    )
    assert result["runtime_graph"]["meta_json"]["run_state_source_of_truth"] == (
        RUN_STATE_SOURCE_OF_TRUTH
    )
