"""Unit tests for generic agent runtime infrastructure."""

from __future__ import annotations

import asyncio
import os
import sys
import threading
from typing import Any

import pytest

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.actor.actor_runtime import AgentActorRuntime
from backend_business.services.agent.agents.requirement_agent.actor_runtime import (
    RequirementAgentActorRuntime,
)
from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
from backend_business.services.agent.runtime import LocalAgentRuntime, RunRequest
from backend_business.services.agent.runtime.graph_recorder import (
    ContainerConfig,
    RuntimeGraphRecorder,
)
from backend_business.services.agent.runtime.state_contract import (
    RUN_STATE_SOURCE_OF_TRUTH,
    RUN_STATE_VERSION,
    SCRATCHPAD_STATE_BACKEND,
    SCRATCHPAD_STATE_VERSION,
)


class _FakeExecutionGraphService:
    def __init__(self):
        self.graph_counter = 0
        self.container_counter = 0
        self.node_counter = 0
        self.edge_counter = 0
        self.graphs: dict[str, dict[str, Any]] = {}
        self.containers: dict[str, dict[str, Any]] = {}
        self.nodes: dict[str, dict[str, Any]] = {}
        self.edges: dict[str, dict[str, Any]] = {}
        self.agent_runs: dict[str, dict[str, Any]] = {}

    def create_runtime_graph(
        self,
        project_id: str,
        name: str,
        description: str = "",
        created_by: str = "",
        meta_json=None,
        layout_json=None,
        status: str = "running",
    ):
        self.graph_counter += 1
        graph_id = f"graph-{self.graph_counter}"
        graph = {
            "graph_id": graph_id,
            "project_id": project_id,
            "name": name,
            "description": description,
            "graph_type": "agent_runtime_execution",
            "status": status,
            "meta_json": meta_json or {},
            "layout_json": layout_json,
            "created_by": created_by,
            "updated_by": created_by,
        }
        self.graphs[graph_id] = graph
        return dict(graph)

    def patch_graph_meta(
        self,
        graph_id: str,
        meta_patch,
        status: str | None = None,
        updated_by: str = "",
    ):
        graph = self.graphs[graph_id]
        merged = dict(graph.get("meta_json") or {})
        merged.update(meta_patch or {})
        graph["meta_json"] = merged
        if status is not None:
            graph["status"] = status
        if updated_by:
            graph["updated_by"] = updated_by
        return dict(graph)

    def get_execution_graph(self, graph_id: str):
        graph = self.graphs.get(graph_id)
        return dict(graph) if graph else None

    def get_graph_detail(self, graph_id: str):
        return {
            "graph": self.get_execution_graph(graph_id),
            "containers": [item for item in self.containers.values() if item["graph_id"] == graph_id],
            "nodes": [item for item in self.nodes.values() if item["graph_id"] == graph_id],
            "edges": [item for item in self.edges.values() if item["graph_id"] == graph_id],
        }

    def create_container(
        self,
        graph_id: str,
        container_key: str,
        label: str,
        role_type: str,
        config_json=None,
        order_index: int = 0,
        created_by: str = "",
    ):
        self.container_counter += 1
        container_id = f"container-{self.container_counter}"
        container = {
            "container_id": container_id,
            "graph_id": graph_id,
            "container_key": container_key,
            "label": label,
            "role_type": role_type,
            "config_json": config_json or {},
            "order_index": order_index,
            "created_by": created_by,
        }
        self.containers[container_id] = container
        return dict(container)

    def create_node(
        self,
        graph_id: str,
        node_key: str,
        label: str,
        node_type: str,
        role_type: str,
        container_id: str = None,
        config_json=None,
        input_schema_json=None,
        output_schema_json=None,
        order_index: int = 0,
        created_by: str = "",
    ):
        self.node_counter += 1
        node_id = f"node-{self.node_counter}"
        node = {
            "node_id": node_id,
            "graph_id": graph_id,
            "container_id": container_id,
            "node_key": node_key,
            "label": label,
            "node_type": node_type,
            "role_type": role_type,
            "config_json": config_json or {},
            "input_schema_json": input_schema_json,
            "output_schema_json": output_schema_json,
            "order_index": order_index,
            "created_by": created_by,
        }
        self.nodes[node_id] = node
        return dict(node)

    def get_node(self, node_id: str):
        return dict(self.nodes[node_id])

    def update_node(self, node_id: str, config_json=None, updated_by: str = "", **kwargs):
        node = self.nodes[node_id]
        if config_json is not None:
            node["config_json"] = config_json
        node.update({k: v for k, v in kwargs.items() if v is not None})
        if updated_by:
            node["updated_by"] = updated_by
        return dict(node)

    def create_edge(
        self,
        graph_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        label: str = None,
        condition_expr: str = None,
        config_json=None,
        order_index: int = 0,
        created_by: str = "",
    ):
        self.edge_counter += 1
        edge_id = f"edge-{self.edge_counter}"
        edge = {
            "edge_id": edge_id,
            "graph_id": graph_id,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "edge_type": edge_type,
            "label": label,
            "condition_expr": condition_expr,
            "config_json": config_json or {},
            "order_index": order_index,
            "created_by": created_by,
        }
        self.edges[edge_id] = edge
        return dict(edge)

    def create_agent_run(self, **kwargs):
        row = dict(kwargs)
        self.agent_runs[row["run_id"]] = row
        return dict(row)

    def update_agent_run(self, run_id: str, **kwargs):
        row = self.agent_runs[run_id]
        row.update({k: v for k, v in kwargs.items() if v is not None})
        return dict(row)


class _FakeToolExecutor:
    def __init__(self, handlers: list[Any]) -> None:
        self._handlers = list(handlers)
        self.calls: list[tuple[str, dict[str, Any], dict[str, Any]]] = []

    def get_tools_list(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {"name": "dummy", "parameters": {"type": "object"}},
            }
        ]

    def get_tool_execution_metadata(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "read_only": True,
            "idempotent": True,
            "resource_key": str(arguments.get("resource") or tool_name),
            "concurrency_group": "test-tools",
        }

    def execute(self, tool_name: str, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, arguments, dict(context)))
        if not self._handlers:
            return {"ok": True}
        return self._handlers.pop(0)(tool_name, arguments, context)


class _BarrierToolExecutor:
    def __init__(self) -> None:
        self._barrier = threading.Barrier(2, timeout=1.0)

    def get_tools_list(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {"name": "dummy", "parameters": {"type": "object"}},
            }
        ]

    def get_tool_execution_metadata(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "read_only": True,
            "idempotent": True,
            "resource_key": str(arguments.get("value") or tool_name),
            "concurrency_group": "test-tools",
        }

    def execute(self, tool_name: str, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        self._barrier.wait()
        return {"ok": True, "value": arguments.get("value")}


class _FakePromptBuilder:
    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        return f"system:{context.get('project_id')}"

    def build_user_message(self, *, user_message: str, context: dict[str, Any]) -> str:
        return f"user:{user_message}"

    def build_round_input_summary(
        self,
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "round": round_index,
            "message_count": len(messages),
            "resolved_requirement_id": context.get("resolved_requirement_id"),
        }


class _FakeAiProxy:
    def __init__(self, responses: list[dict[str, Any]]) -> None:
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat_completion_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("unexpected tool completion call")
        return self._responses.pop(0)


class _FakeActorManager:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def send_command(self, entity_id: str, command: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((entity_id, dict(command)))
        await asyncio.sleep(0)
        return {"status": "success", "entity_id": entity_id, "command": command}


def _shutdown_actor_runtime(runtime: AgentActorRuntime) -> None:
    loop = getattr(runtime, "_actor_loop", None)
    thread = getattr(runtime, "_actor_loop_thread", None)
    if loop and loop.is_running():
        loop.call_soon_threadsafe(loop.stop)
    if thread and thread.is_alive():
        thread.join(timeout=1.5)
    if loop and not loop.is_closed():
        loop.close()


def _run_tool_loop_to_completion(generator):
    events = []
    while True:
        try:
            events.append(next(generator))
        except StopIteration as stop:
            return events, stop.value


def test_runtime_graph_recorder_supports_configurable_containers_and_task_context():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[
            ContainerConfig("human_input", "Human Input", "human"),
            ContainerConfig("agent_main", "Agent Main", "agent"),
        ],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="hello",
        initial_graph_meta={"intent": "pending", "domain": "generic"},
        task_context={"domain": "generic", "scope": "unit-test"},
    )

    node_key = recorder.stage_node_key("analysis")
    recorder.start_stage(
        node_key=node_key,
        label=recorder.stage_label("Analysis"),
        node_type="llm",
        role_type="agent",
        container_key="agent_main",
        created_by="u-1",
        input_summary={"step": 1},
    )
    recorder.complete_stage(
        node_key,
        created_by="u-1",
        output_summary={"ok": True},
    )

    assert sorted(c["container_key"] for c in graph_service.containers.values()) == [
        "agent_main",
        "human_input",
    ]
    node = next(item for item in graph_service.nodes.values() if item["node_key"] == node_key)
    assert node["config_json"]["input"][0]["kind"] == "task"
    assert node["config_json"]["input"][0]["value"]["domain"] == "generic"
    assert node["config_json"]["input"][0]["value"]["scope"] == "unit-test"
    assert recorder.last_node_key == node_key
    assert graph_service.graphs[recorder.graph_id]["meta_json"]["domain"] == "generic"
    assert graph_service.graphs[recorder.graph_id]["meta_json"]["scratchpad_state_version"] == (
        SCRATCHPAD_STATE_VERSION
    )
    assert graph_service.graphs[recorder.graph_id]["meta_json"]["scratchpad_state_backend"] == (
        SCRATCHPAD_STATE_BACKEND
    )
    assert graph_service.graphs[recorder.graph_id]["meta_json"]["run_state_version"] == (
        RUN_STATE_VERSION
    )
    assert graph_service.graphs[recorder.graph_id]["meta_json"]["run_state_source_of_truth"] == (
        RUN_STATE_SOURCE_OF_TRUTH
    )


def test_tool_loop_stage_binds_agent_run_ref_into_trace():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[
            ContainerConfig(
                container_key="agent",
                label="Agent",
                role_type="agent",
            )
        ],
        project_id="proj-1",
        user_id="u-1",
        session_id="s-1",
        user_message="hello",
    )
    runner = ToolLoopRunner(
        ai_proxy_client=_FakeAiProxy(
            responses=[
                {
                    "content": "done",
                    "finish_reason": "stop",
                }
            ]
        ),
        tool_executor=_FakeToolExecutor([]),
        prompt_builder=_FakePromptBuilder(),
    )

    events = list(
        runner.run(
            user_message="hello",
            recorder=recorder,
            user_id="u-1",
            context={
                "graph_id": recorder.graph_id,
                "user_id": "u-1",
                "_graph_recorder": recorder,
                "_agent_run_ref": {
                    "run_id": "run-123",
                    "runtime_id": "rt-local",
                    "source_of_truth": RUN_STATE_SOURCE_OF_TRUTH,
                },
            },
        )
    )

    stage_events = [item for item in events if item.get("event") == "stage"]
    assert stage_events
    node_key = stage_events[0]["data"]["node_key"]
    node = next(item for item in graph_service.nodes.values() if item["node_key"] == node_key)
    assert node["config_json"]["run_ref"] == {
        "run_id": "run-123",
        "runtime_id": "rt-local",
        "source_of_truth": RUN_STATE_SOURCE_OF_TRUTH,
    }


def test_runtime_graph_recorder_rehydrates_history_and_increments_turn():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[
            ContainerConfig("human_input", "Human Input", "human"),
            ContainerConfig("agent_main", "Agent Main", "agent"),
        ],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="first",
    )
    first_node_key = recorder.stage_node_key("analysis")
    recorder.start_stage(
        node_key=first_node_key,
        label=recorder.stage_label("Analysis"),
        node_type="llm",
        role_type="agent",
        container_key="agent_main",
        created_by="u-1",
        input_summary={"round": 1},
    )
    recorder.complete_stage(first_node_key, created_by="u-1", output_summary={"summary": "ok"})

    recorder2 = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[
            ContainerConfig("human_input", "Human Input", "human"),
            ContainerConfig("agent_main", "Agent Main", "agent"),
        ],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="second",
        graph_id=recorder.graph_id,
    )
    second_node_key = recorder2.stage_node_key("analysis")
    recorder2.start_stage(
        node_key=second_node_key,
        label=recorder2.stage_label("Analysis"),
        node_type="llm",
        role_type="agent",
        container_key="agent_main",
        created_by="u-1",
        input_summary={"round": 2},
    )

    assert recorder2.turn_index == 2
    assert recorder2.historical_node_context[-1]["node_key"] == first_node_key
    assert graph_service.edges


def test_runtime_graph_recorder_rejects_unknown_container_key():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="hello",
    )

    with pytest.raises(KeyError):
        recorder.start_stage(
            node_key=recorder.stage_node_key("x"),
            label=recorder.stage_label("X"),
            node_type="llm",
            role_type="agent",
            container_key="unknown",
            created_by="u-1",
            input_summary={},
        )


def test_runtime_graph_recorder_attach_only_reuses_existing_topology_containers():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="hello",
    )
    initial_container_ids = sorted(graph_service.containers)

    attached = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="follow-up",
        graph_id=recorder.graph_id,
        attach_only=True,
    )
    node_key = attached.stage_node_key("analysis")
    attached.start_stage(
        node_key=node_key,
        label=attached.stage_label("Analysis"),
        node_type="llm",
        role_type="agent",
        container_key="agent_main",
        created_by="u-1",
        input_summary={"round": 2},
    )

    assert sorted(graph_service.containers) == initial_container_ids
    started_node = next(
        node for node in graph_service.nodes.values() if node["node_key"] == node_key
    )
    assert started_node["container_id"] == next(iter(graph_service.containers))


def test_runtime_graph_recorder_attach_only_rejects_missing_container_instead_of_creating():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="hello",
    )
    initial_container_count = len(graph_service.containers)

    attached = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[ContainerConfig("other_agent", "Other Agent", "agent")],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="follow-up",
        graph_id=recorder.graph_id,
        attach_only=True,
    )

    with pytest.raises(KeyError, match="other_agent"):
        attached.start_stage(
            node_key=attached.stage_node_key("analysis"),
            label=attached.stage_label("Analysis"),
            node_type="llm",
            role_type="agent",
            container_key="other_agent",
            created_by="u-1",
            input_summary={"round": 2},
        )

    assert len(graph_service.containers) == initial_container_count


def test_tool_loop_runner_executes_multi_round_and_patches_meta():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="hello",
    )
    meta_patches: list[tuple[str, dict[str, Any], str]] = []
    runner = ToolLoopRunner(
        ai_proxy_client=_FakeAiProxy(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "type": "function",
                            "function": {"name": "dummy", "arguments": "{\"keyword\":\"x\"}"},
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
                {"content": "done", "tool_calls": [], "finish_reason": "stop"},
            ]
        ),
        tool_executor=_FakeToolExecutor(
            [
                lambda _tool_name, _arguments, context: (
                    context.update({"resolved_requirement_id": "r-1"}) or {"ok": True}
                )
            ]
        ),
        prompt_builder=_FakePromptBuilder(),
        max_tool_call_rounds=3,
        stage_container_key="agent_main",
        graph_meta_patcher=lambda graph_id, meta_patch, updated_by: meta_patches.append(
            (graph_id, dict(meta_patch), updated_by)
        ),
        graph_meta_patch_builder=lambda context: {
            "resolved_requirement_id": context.get("resolved_requirement_id")
        },
    )

    events, result = _run_tool_loop_to_completion(
        runner.run(
            recorder=recorder,
            user_id="u-1",
            user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        )
    )

    assert [event["event"] for event in events] == [
        "stage",
        "tool_call",
        "tool_result",
        "stage",
        "stage",
        "stage",
    ]
    assert result.tool_loop_reply == "done"
    assert result.rounds == 2
    assert result.context["resolved_requirement_id"] == "r-1"
    assert len(result.context["tool_results"]) == 1
    assert len(meta_patches) == 2
    assert meta_patches[-1][1]["resolved_requirement_id"] == "r-1"


def test_tool_loop_runner_executes_same_round_tool_calls_concurrently():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="hello",
    )
    runner = ToolLoopRunner(
        ai_proxy_client=_FakeAiProxy(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "type": "function",
                            "function": {"name": "dummy", "arguments": "{\"value\":\"a\"}"},
                        },
                        {
                            "id": "tc-2",
                            "type": "function",
                            "function": {"name": "dummy", "arguments": "{\"value\":\"b\"}"},
                        },
                    ],
                    "finish_reason": "tool_calls",
                },
                {"content": "done", "tool_calls": [], "finish_reason": "stop"},
            ]
        ),
        tool_executor=_BarrierToolExecutor(),
        prompt_builder=_FakePromptBuilder(),
        max_tool_call_rounds=3,
        stage_container_key="agent_main",
    )

    events, result = _run_tool_loop_to_completion(
        runner.run(
            recorder=recorder,
            user_id="u-1",
            user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        )
    )

    tool_results = result.context["tool_results"]
    assert len(tool_results) == 2
    assert [item["result"]["value"] for item in tool_results] == ["a", "b"]
    assert sum(1 for event in events if event["event"] == "tool_call") == 2
    assert sum(1 for event in events if event["event"] == "tool_result") == 2


def test_tool_loop_runner_uses_snapshot_isolation_and_deterministic_merge_for_parallel_calls():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="hello",
    )
    second_tool_finished = threading.Event()
    observed_contexts: list[tuple[str, str | None, str | None]] = []

    def _first_handler(_tool_name, _arguments, context):
        observed_contexts.append(
            (
                "first",
                context.get("shared_value"),
                context.get("second_visible"),
            )
        )
        context["shared_value"] = "from-first"
        context["first_visible"] = "yes"
        second_tool_finished.wait(timeout=1.0)
        return {"ok": True, "worker": "first"}

    def _second_handler(_tool_name, _arguments, context):
        observed_contexts.append(
            (
                "second",
                context.get("shared_value"),
                context.get("first_visible"),
            )
        )
        context["shared_value"] = "from-second"
        context["second_visible"] = "yes"
        second_tool_finished.set()
        return {"ok": True, "worker": "second"}

    runner = ToolLoopRunner(
        ai_proxy_client=_FakeAiProxy(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "type": "function",
                            "function": {"name": "dummy", "arguments": "{}"},
                        },
                        {
                            "id": "tc-2",
                            "type": "function",
                            "function": {"name": "dummy", "arguments": "{}"},
                        },
                    ],
                    "finish_reason": "tool_calls",
                },
                {"content": "done", "tool_calls": [], "finish_reason": "stop"},
            ]
        ),
        tool_executor=_FakeToolExecutor([_first_handler, _second_handler]),
        prompt_builder=_FakePromptBuilder(),
        max_tool_call_rounds=3,
        stage_container_key="agent_main",
    )

    _events, result = _run_tool_loop_to_completion(
        runner.run(
            recorder=recorder,
            user_id="u-1",
            user_message="hello",
            context={"project_id": "p-1", "tool_results": [], "shared_value": "initial"},
        )
    )

    assert observed_contexts == [
        ("first", "initial", None),
        ("second", "initial", None),
    ]
    assert result.context["shared_value"] == "from-second"
    assert result.context["first_visible"] == "yes"
    assert result.context["second_visible"] == "yes"
    assert [
        item["result"]["worker"] for item in result.context["tool_results"]
    ] == ["first", "second"]


def test_tool_loop_runner_rejects_empty_model_reply_without_tool_calls():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="hello",
    )
    runner = ToolLoopRunner(
        ai_proxy_client=_FakeAiProxy(
            [
                {
                    "content": "",
                    "tool_calls": [],
                    "reasoning_content": "我还在想，但没有给出最终输出。",
                    "finish_reason": "stop",
                }
            ]
        ),
        tool_executor=_FakeToolExecutor([]),
        prompt_builder=_FakePromptBuilder(),
        stage_container_key="agent_main",
    )

    generator = runner.run(
        recorder=recorder,
        user_id="u-1",
        user_message="hello",
        context={"project_id": "p-1", "tool_results": []},
    )
    assert next(generator)["event"] == "stage"
    with pytest.raises(ValueError) as exc_info:
        next(generator)
    error_text = str(exc_info.value)
    assert "模型未返回文本或工具调用" in error_text
    assert "finish_reason='stop'" in error_text
    assert "reasoning_content_present=True" in error_text
    assert "tool_call_count=0" in error_text


def test_tool_loop_runner_raises_when_round_limit_exceeded():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="hello",
    )
    runner = ToolLoopRunner(
        ai_proxy_client=_FakeAiProxy(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {"id": "tc-1", "type": "function", "function": {"name": "dummy", "arguments": "{}"}}
                    ],
                    "finish_reason": "tool_calls",
                },
                {
                    "content": "",
                    "tool_calls": [
                        {"id": "tc-2", "type": "function", "function": {"name": "dummy", "arguments": "{}"}}
                    ],
                    "finish_reason": "tool_calls",
                },
            ]
        ),
        tool_executor=_FakeToolExecutor([lambda *_args: {"ok": True}, lambda *_args: {"ok": True}]),
        prompt_builder=_FakePromptBuilder(),
        max_tool_call_rounds=2,
        stage_container_key="agent_main",
    )

    with pytest.raises(RuntimeError, match="工具调用轮数超过上限 2"):
        for _ in runner.run(
            recorder=recorder,
            user_id="u-1",
            user_message="hello",
            context={"project_id": "p-1", "tool_results": []},
        ):
            pass


def test_local_agent_runtime_cancel_marks_run_cancelled_without_waiting_for_runner_lock():
    graph_service = _FakeExecutionGraphService()
    runtime = LocalAgentRuntime(
        runtime_id="local::test",
        execution_graph_service=graph_service,
    )
    runtime_context: dict[str, Any] = {}
    runner_started = threading.Event()
    result_holder: dict[str, Any] = {}

    def _runner():
        runner_started.set()
        while not runtime_context["_runtime_cancel_event"].is_set():
            yield {"event": "heartbeat"}
            threading.Event().wait(0.01)
        return {"cancel_observed": True}

    run_id = runtime.submit(
        RunRequest(
            graph_id="graph-1",
            subgraph_id="sg-1",
            container_key="agent_main",
            agent_type="agent_main",
            input_payload={
                "runner": _runner,
                "runtime_context": runtime_context,
                "input_ref": {"source_edge_id": "edge-1"},
            },
        )
    )

    await_thread = threading.Thread(
        target=lambda: result_holder.setdefault("result", runtime.await_result(run_id)),
        daemon=True,
    )
    await_thread.start()
    assert runner_started.wait(timeout=1.0) is True

    runtime.cancel(run_id)
    await_thread.join(timeout=1.0)

    assert result_holder["result"].status == "cancelled"
    assert graph_service.agent_runs[run_id]["status"] == "cancelled"
    assert graph_service.agent_runs[run_id]["error_code"] == "cancelled"


def test_local_agent_runtime_cancel_stops_tool_loop_before_next_round():
    graph_service = _FakeExecutionGraphService()
    recorder = RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        container_configs=[ContainerConfig("agent_main", "Agent Main", "agent")],
        project_id="p-1",
        user_id="u-1",
        session_id="s-1",
        user_message="hello",
    )
    runtime = LocalAgentRuntime(
        runtime_id="local::test",
        execution_graph_service=graph_service,
    )
    runtime_context: dict[str, Any] = {
        "project_id": "p-1",
        "tool_results": [],
    }
    tool_started = threading.Event()
    tool_release = threading.Event()

    def _blocking_tool(*_args):
        tool_started.set()
        tool_release.wait(timeout=5.0)
        return {"ok": True}

    ai_proxy = _FakeAiProxy(
        [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc-1",
                        "type": "function",
                        "function": {"name": "dummy", "arguments": "{}"},
                    }
                ],
                "finish_reason": "tool_calls",
            },
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc-2",
                        "type": "function",
                        "function": {"name": "dummy", "arguments": "{}"},
                    }
                ],
                "finish_reason": "tool_calls",
            },
        ]
    )
    tool_executor = _FakeToolExecutor(
        [_blocking_tool, lambda *_args: {"unexpected": True}]
    )
    tool_loop = ToolLoopRunner(
        ai_proxy_client=ai_proxy,
        tool_executor=tool_executor,
        prompt_builder=_FakePromptBuilder(),
        max_tool_call_rounds=3,
        stage_container_key="agent_main",
    )

    def _runner():
        return (
            yield from tool_loop.run(
                recorder=recorder,
                user_id="u-1",
                user_message="hello",
                context=runtime_context,
            )
        )

    run_id = runtime.submit(
        RunRequest(
            graph_id=recorder.graph_id,
            subgraph_id="sg-1",
            container_key="agent_main",
            agent_type="agent_main",
            input_payload={
                "runner": _runner,
                "runtime_context": runtime_context,
            },
        )
    )
    stream_thread = threading.Thread(
        target=lambda: list(runtime.stream(run_id)),
        daemon=True,
    )
    stream_thread.start()
    assert tool_started.wait(timeout=1.0) is True

    runtime.cancel(run_id)
    tool_release.set()
    stream_thread.join(timeout=1.0)

    assert stream_thread.is_alive() is False
    assert runtime.await_result(run_id).status == "cancelled"
    assert len(ai_proxy.calls) == 1
    assert len(tool_executor.calls) == 1


def test_agent_actor_runtime_supports_query_and_write():
    runtime = AgentActorRuntime(query_source="unit_test_source", loop_thread_name="unit-test-loop")
    actor_manager = _FakeActorManager()
    try:
        first = runtime.ensure_actor_loop()
        second = runtime.ensure_actor_loop()
        assert first is second

        query_result = runtime.actor_query(actor_manager, "entity-1")
        write_result = runtime.actor_write(actor_manager, "entity-1", {"type": "UpdateSomething"})

        assert query_result["status"] == "success"
        assert write_result["status"] == "success"
        assert actor_manager.calls[0] == (
            "entity-1",
            {"type": "QueryState", "source": "unit_test_source"},
        )
        assert actor_manager.calls[1] == ("entity-1", {"type": "UpdateSomething"})
    finally:
        _shutdown_actor_runtime(runtime)


def test_requirement_agent_actor_runtime_uses_requirement_specific_query_source():
    runtime = RequirementAgentActorRuntime()
    actor_manager = _FakeActorManager()
    try:
        runtime.actor_query(actor_manager, "req-1")
        assert actor_manager.calls[0] == (
            "req-1",
            {"type": "QueryState", "source": "requirement_agent_chat"},
        )
    finally:
        _shutdown_actor_runtime(runtime)


def test_agent_actor_runtime_instances_share_one_loop_across_caller_threads():
    first_runtime = AgentActorRuntime(loop_thread_name="shared-actor-loop-a")
    second_runtime = AgentActorRuntime(loop_thread_name="shared-actor-loop-b")
    results: list[tuple[int, int]] = []
    errors: list[BaseException] = []

    def _capture_broker_context() -> tuple[int, int]:
        return id(asyncio.get_running_loop()), threading.get_ident()

    def _call_from_thread(runtime: AgentActorRuntime) -> None:
        async def _run() -> None:
            results.append(
                await runtime.await_actor_call(_capture_broker_context)
            )

        try:
            asyncio.run(_run())
        except BaseException as exc:
            errors.append(exc)

    first_thread = threading.Thread(target=_call_from_thread, args=(first_runtime,))
    second_thread = threading.Thread(target=_call_from_thread, args=(second_runtime,))
    try:
        first_thread.start()
        second_thread.start()
        first_thread.join(timeout=3.0)
        second_thread.join(timeout=3.0)

        assert first_thread.is_alive() is False
        assert second_thread.is_alive() is False
        assert errors == []
        assert len(results) == 2
        assert results[0] == results[1]
        assert first_runtime.ensure_actor_loop() is second_runtime.ensure_actor_loop()
    finally:
        _shutdown_actor_runtime(first_runtime)
