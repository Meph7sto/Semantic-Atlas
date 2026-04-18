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
from backend_business.services.agent.runtime.graph_recorder import (
    ContainerConfig,
    RuntimeGraphRecorder,
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
