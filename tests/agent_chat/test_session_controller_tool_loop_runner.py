"""Tests for SessionControllerToolLoopRunner integration behavior."""

from __future__ import annotations

import os
import sys

import pytest

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.agents.session_controller.contracts import (  # noqa: E402
    SessionControllerDecisionMode,
)
from backend_business.services.agent.agents.session_controller.prompt_builder import (  # noqa: E402
    SessionControllerPromptBuilder,
)
from backend_business.services.agent.agents.session_controller.tool_loop_runner import (  # noqa: E402
    SessionControllerToolLoopRunner,
)


class _FakeAIProxy:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self._responses = [
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc-1",
                        "type": "function",
                        "function": {
                            "name": "invoke_requirement_agent",
                            "arguments": '{"task_description":"读取 REQ-9"}',
                        },
                    }
                ],
                "finish_reason": "tool_calls",
            },
            {
                "content": (
                    '{"mode":"delegate_requirement","tool_loop_reply":"已读取需求详情并准备向用户汇总。",'
                    '"assistant_reply_seed":"这是一个需求的完整信息摘要",'
                    '"delegated_agent":"requirement_agent",'
                    '"resolved_requirement_id":"REQ-9",'
                    '"dispatched_agents":["requirement_agent"],'
                    '"should_suspend":false,"approval_pending":false}'
                ),
                "tool_calls": [],
                "finish_reason": "stop",
            },
        ]

    def chat_completion_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("unexpected chat_completion_with_tools call")
        return self._responses.pop(0)


class _FakeTools:
    def __init__(self) -> None:
        self.executions: list[dict] = []

    @staticmethod
    def get_tools_list() -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "invoke_requirement_agent",
                    "parameters": {"type": "object"},
                },
            }
        ]

    def execute(self, tool_name, arguments, context):
        self.executions.append(
            {
                "tool_name": tool_name,
                "arguments": dict(arguments),
                "context_keys": sorted(context.keys()),
            }
        )
        context["resolved_requirement_id"] = "REQ-9"
        context.setdefault("dispatched_agents", []).append("requirement_agent")
        return {
            "status": "success",
            "tool_loop_reply": "已读取需求详情",
            "resolved_requirement_id": "REQ-9",
        }


class _FakeExecutionGraphService:
    def __init__(self) -> None:
        self.graphs = {
            "graph-1": {
                "graph_id": "graph-1",
                "meta_json": {},
            }
        }

    def get_execution_graph(self, graph_id: str):
        return dict(self.graphs.get(graph_id) or {})

    def patch_graph_meta(self, graph_id: str, meta_patch, updated_by: str = "") -> None:
        graph = self.graphs[graph_id]
        merged = dict(graph.get("meta_json") or {})
        merged.update(meta_patch or {})
        graph["meta_json"] = merged


class _FakeRecorder:
    graph_id = "graph-1"
    historical_node_context = None

    def __init__(self) -> None:
        self.started: list[dict] = []
        self.completed: list[dict] = []
        self.tool_calls: list[dict] = []

    @staticmethod
    def stage_node_key(base_key: str) -> str:
        return f"turn_1__{base_key}"

    @staticmethod
    def stage_label(base_label: str) -> str:
        return base_label

    def start_stage(self, **kwargs) -> None:
        self.started.append(kwargs)

    def complete_stage(self, node_key, **kwargs) -> None:
        self.completed.append({"node_key": node_key, **kwargs})

    def record_tool_call_result(self, node_key, **kwargs) -> None:
        self.tool_calls.append({"node_key": node_key, **kwargs})

    def build_stage_event_data(self, node_key, *, status, **extra):
        payload = {"graph_id": self.graph_id, "node_key": node_key, "status": status}
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


def test_session_controller_tool_loop_runner_requires_structured_finish_after_delegation():
    ai_proxy = _FakeAIProxy()
    tools = _FakeTools()
    graph_service = _FakeExecutionGraphService()
    recorder = _FakeRecorder()
    runner = SessionControllerToolLoopRunner(
        ai_proxy_client=ai_proxy,
        tools=tools,
        execution_graph_service=graph_service,
        prompt_builder=SessionControllerPromptBuilder(),
        max_tool_call_rounds=4,
    )

    gen = runner.run(
        recorder=recorder,
        user_id="u-1",
        user_message="给我 REQ-9 的完整信息",
        project_id="p-1",
        session_id="sess-1",
    )
    events = []
    try:
        while True:
            events.append(next(gen))
    except StopIteration as stop:
        result = stop.value

    stage_running_events = [
        event for event in events if event["event"] == "stage" and event["data"]["status"] == "running"
    ]
    assert len(stage_running_events) == 2
    assert len(ai_proxy.calls) == 2
    assert len(tools.executions) == 1
    assert result.mode == SessionControllerDecisionMode.DELEGATE_REQUIREMENT
    assert result.delegated_agent == "requirement_agent"
    assert result.resolved_requirement_id == "REQ-9"
    assert result.tool_loop_reply == "已读取需求详情并准备向用户汇总。"
    assert "_stop_after_tool_round" not in result.context
    assert "_forced_tool_loop_reply" not in result.context


def test_session_controller_tool_loop_runner_surfaces_empty_model_reply_diagnostics():
    class _EmptyAIProxy:
        def __init__(self) -> None:
            self.calls: list[dict] = []

        def chat_completion_with_tools(self, **kwargs):
            self.calls.append(kwargs)
            return {
                "content": "",
                "tool_calls": [],
                "reasoning_content": "模型只返回了思维链片段。",
                "finish_reason": "stop",
            }

    runner = SessionControllerToolLoopRunner(
        ai_proxy_client=_EmptyAIProxy(),
        tools=_FakeTools(),
        execution_graph_service=_FakeExecutionGraphService(),
        prompt_builder=SessionControllerPromptBuilder(),
        max_tool_call_rounds=2,
    )

    generator = runner.run(
        recorder=_FakeRecorder(),
        user_id="u-1",
        user_message="给我 REQ-9 的完整信息",
        project_id="p-1",
        session_id="sess-1",
    )

    assert next(generator)["event"] == "stage"
    with pytest.raises(ValueError) as exc_info:
        next(generator)

    error_text = str(exc_info.value)
    assert "模型未返回文本或工具调用" in error_text
    assert "finish_reason='stop'" in error_text
    assert "reasoning_content_present=True" in error_text
    assert "tool_call_count=0" in error_text
