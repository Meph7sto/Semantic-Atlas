"""Unit tests for SessionController graph-only tool delegation."""

from __future__ import annotations

import os
import sys

import pytest

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.agents.session_controller.prompt_builder import (  # noqa: E402
    infer_routing_hint,
)
from backend_business.services.agent.agents.session_controller.tools import (  # noqa: E402
    SessionControllerTools,
)
from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner  # noqa: E402


class _FakeRequirementsService:
    pass


class _FakeChildAgentService:
    def __init__(self):
        self.tools = object()


class _FakeRecorder:
    def __init__(self):
        self.started = []
        self.completed = []
        self._turn_index = 1

    @property
    def graph_id(self) -> str:
        return "test-graph-1"

    def stage_node_key(self, base_key: str) -> str:
        return f"turn_{self._turn_index}__{base_key}"

    def stage_label(self, base_label: str) -> str:
        return f"{base_label} (Turn {self._turn_index})"

    def start_stage(self, **kwargs):
        self.started.append(kwargs)

    def complete_stage(self, node_key, **kwargs):
        self.completed.append({"node_key": node_key, **kwargs})

    def record_tool_call_result(
        self,
        node_key,
        *,
        created_by,
        tool_name,
        request_payload,
        result_payload,
    ):
        pass

    def build_stage_event_data(self, node_key, *, status, **extra):
        payload = {
            "graph_id": self.graph_id,
            "node_key": node_key,
            "status": status,
        }
        payload.update(extra)
        return payload

    def build_tool_result_event_data(self, node_key, *, tool, tool_call_id, result):
        return {
            "graph_id": self.graph_id,
            "node_key": node_key,
            "tool": tool,
            "tool_call_id": tool_call_id,
            "result": result,
        }


def _make_tools():
    return SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=_FakeChildAgentService(),
        conflict_agent_service=_FakeChildAgentService(),
        requirement_classification_agent_service=_FakeChildAgentService(),
    )


def test_invoke_requirement_agent_returns_native_payload():
    tools = _make_tools()
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
        "session_id": "sess-1",
        "dispatched_agents": [],
    }

    result = tools.execute(
        "invoke_requirement_agent",
        {"task_description": "读取 REQ-1 的详情", "requirement_id": "REQ-1"},
        context,
    )

    assert result == {
        "status": "accepted",
        "native_invoke": True,
        "delegated_agent": "requirement_agent",
        "invoke_route_key": "invoke_requirement",
        "task_description": "读取 REQ-1 的详情",
        "requirement_id": "REQ-1",
        "max_tool_call_rounds": 15,
        "prompt_payload_format": "markdown",
        "context_mode": "full",
    }
    assert context["dispatched_agents"] == ["requirement_agent"]
    assert context["resolved_requirement_id"] == "REQ-1"


def test_invoke_requirement_agent_falls_back_to_resolved_requirement_id():
    tools = _make_tools()
    context = {
        "project_id": "p-2",
        "user_id": "u-2",
        "resolved_requirement_id": "REQ-9",
        "delegated_prompt_payload_format": "json",
        "delegated_context_mode": "compact",
        "delegated_max_tool_call_rounds": "51",
        "dispatched_agents": [],
    }

    result = tools.execute(
        "invoke_requirement_agent",
        {"task_description": "把这个需求的优先级改成低"},
        context,
    )

    assert result["requirement_id"] == "REQ-9"
    assert result["prompt_payload_format"] == "json"
    assert result["context_mode"] == "compact"
    assert result["max_tool_call_rounds"] == 50


def test_invoke_conflict_detection_returns_native_payload():
    tools = _make_tools()
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
        "delegated_max_tool_call_rounds": "bad-value",
        "dispatched_agents": [],
    }

    result = tools.execute(
        "invoke_conflict_detection",
        {"task_description": "检测 REQ-1 和 REQ-2 是否冲突"},
        context,
    )

    assert result == {
        "status": "accepted",
        "native_invoke": True,
        "delegated_agent": "conflict_detection",
        "invoke_route_key": "invoke_conflict",
        "task_description": "检测 REQ-1 和 REQ-2 是否冲突",
        "max_tool_call_rounds": 15,
    }
    assert context["dispatched_agents"] == ["conflict_detection"]


def test_invoke_requirement_classification_agent_returns_native_payload():
    tools = _make_tools()
    context = {"project_id": "p-1", "user_id": "u-1", "dispatched_agents": []}

    result = tools.execute(
        "invoke_requirement_classification_agent",
        {"task_description": "分类 REQ-1", "requirement_id": "REQ-1"},
        context,
    )

    assert result["status"] == "accepted"
    assert result["native_invoke"] is True
    assert result["delegated_agent"] == "requirement_classification_agent"
    assert result["invoke_route_key"] == "invoke_classification"
    assert result["requirement_id"] == "REQ-1"
    assert context["dispatched_agents"] == ["requirement_classification_agent"]
    assert context["resolved_requirement_id"] == "REQ-1"


def test_streaming_delegation_returns_native_payload_without_child_events():
    tools = _make_tools()
    context = {
        "project_id": "p-3",
        "user_id": "u-3",
        "graph_id": "test-graph-1",
        "dispatched_agents": [],
    }

    result = tools.execute_streaming(
        "invoke_requirement_agent",
        {"task_description": "读取 REQ-3", "requirement_id": "REQ-3"},
        context,
    )

    assert isinstance(result, dict)
    assert result["native_invoke"] is True
    assert result["delegated_agent"] == "requirement_agent"
    assert context["dispatched_agents"] == ["requirement_agent"]


def test_delegation_requires_task_description():
    tools = _make_tools()

    with pytest.raises(ValueError, match="task_description"):
        tools.execute("invoke_requirement_agent", {"task_description": " "}, {})


def test_delegation_does_not_require_graph_recorder():
    tools = _make_tools()
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
        "tool_results": [],
        "dispatched_agents": [],
    }

    result = tools.execute(
        "invoke_requirement_agent",
        {"task_description": "一些任务"},
        context,
    )

    assert result["status"] == "accepted"
    assert result["native_invoke"] is True


def test_resolve_runtime_tool_executor_uses_container_key_instead_of_scope_context():
    tools = _make_tools()

    assert tools.resolve_runtime_tool_executor(container_key="conductor") is tools
    assert tools.resolve_runtime_tool_executor(container_key="session_controller") is tools
    assert (
        tools.resolve_runtime_tool_executor(container_key="requirement_agent")
        is tools._requirement_agent_service.tools
    )
    assert (
        tools.resolve_runtime_tool_executor(container_key="conflict_detection")
        is tools._conflict_agent_service.tools
    )
    assert (
        tools.resolve_runtime_tool_executor(
            container_key="requirement_classification_agent"
        )
        is tools._requirement_classification_agent_service.tools
    )
    assert tools.resolve_runtime_tool_executor(container_key="unknown") is None


def test_infer_routing_hint_prefers_requirement_agent_for_priority_updates():
    hint = infer_routing_hint(
        "10. 冲突检测引擎 shall 将检测到的冲突结果输出到指定数据结构，这条需求的优先级改为low"
    )

    assert hint is not None
    assert hint["preferred_tool"] == "invoke_requirement_agent"


def test_infer_routing_hint_prefers_conflict_agent_for_explicit_checks():
    hint = infer_routing_hint("请检查 REQ-1 和 REQ-2 是否冲突")

    assert hint is not None
    assert hint["preferred_tool"] == "invoke_conflict_detection"


def test_tools_do_not_stop_parent_tool_loop():
    class _PromptBuilder:
        def build_system_prompt(self, *, context):
            return "system"

        def build_user_message(self, *, user_message, context):
            return user_message

        def build_round_input_summary(self, *, round_index, messages, context):
            return {"round": round_index}

    class _AIProxy:
        def __init__(self):
            self.calls = 0

        def chat_completion_with_tools(self, **kwargs):
            self.calls += 1
            if self.calls == 1:
                return {
                    "content": "",
                    "finish_reason": "tool_calls",
                    "tool_calls": [
                        {
                            "id": "tool-1",
                            "function": {
                                "name": "invoke_requirement_agent",
                                "arguments": "{\"task_description\":\"读取 REQ-9\"}",
                            },
                        }
                    ],
                }
            return {
                "content": "已读取需求详情",
                "finish_reason": "stop",
                "tool_calls": [],
            }

    tools = _make_tools()
    runner = ToolLoopRunner(
        ai_proxy_client=_AIProxy(),
        tool_executor=tools,
        prompt_builder=_PromptBuilder(),
        max_tool_call_rounds=2,
        stage_container_key="conductor",
        stage_node_key_builder=lambda round_index: f"session_controller_tool_loop_round_{round_index}",
        stage_label_builder=lambda round_index: f"Tool Loop Round {round_index}",
    )
    recorder = _FakeRecorder()
    context = {
        "project_id": "p-9",
        "user_id": "u-9",
        "session_id": "s-9",
        "graph_id": recorder.graph_id,
        "tool_results": [],
        "dispatched_agents": [],
    }

    events = []
    gen = runner.run(
        recorder=recorder,
        user_id="u-9",
        user_message="帮我看 REQ-9",
        context=context,
    )

    result = None
    try:
        while True:
            events.append(next(gen))
    except StopIteration as stop:
        result = stop.value

    child_stage_events = [
        event for event in events
        if event["event"] == "stage" and "__req_agent_" in event["data"]["node_key"]
    ]

    assert child_stage_events == []
    assert runner.ai_proxy.calls == 2
    assert result.tool_loop_reply == "已读取需求详情"
    assert context["dispatched_agents"] == ["requirement_agent"]
