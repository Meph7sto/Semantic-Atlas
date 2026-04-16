"""
Unit tests for session controller tools — inline cross-container execution.
"""

from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.agents.session_controller.tools import (  # noqa: E402
    SessionControllerTools,
)
from backend_business.services.agent.agents.session_controller.prompt_builder import (  # noqa: E402
    infer_routing_hint,
)
from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner  # noqa: E402


class _FakeRequirementsService:
    pass


class _FakeRecorder:
    """Minimal recorder stub that tracks all stage/edge operations."""

    def __init__(self):
        self.started = []
        self.completed = []
        self.restored = []
        self.return_edges = []
        self._turn_index = 1

    def stage_node_key(self, base_key: str) -> str:
        return f"turn_{self._turn_index}__{base_key}"

    def stage_label(self, base_label: str) -> str:
        return f"{base_label} (Turn {self._turn_index})"

    @property
    def graph_id(self) -> str:
        return "test-graph-1"

    def start_stage(self, **kwargs):
        self.started.append(kwargs)

    def complete_stage(self, node_key, **kwargs):
        self.completed.append({"node_key": node_key, **kwargs})

    def create_return_edge(self, *, child_node_key, parent_node_key, created_by):
        self.return_edges.append({
            "child_node_key": child_node_key,
            "parent_node_key": parent_node_key,
            "created_by": created_by,
        })

    def restore_stage_cursor(self, *, node_key, updated_by=""):
        self.restored.append({"node_key": node_key, "updated_by": updated_by})

    def record_tool_call_result(self, node_key, *, created_by, tool_name, request_payload, result_payload):
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


class _FakeRequirementAgentService:
    """Fake that exposes run_inline_tool_loop (new API)."""

    def __init__(self, *, inline_result=None):
        self.inline_calls = []
        self._inline_result = inline_result or {
            "status": "success",
            "tool_loop_reply": "已读取需求详情",
            "resolved_requirement_id": "REQ-1",
            "write_result": None,
        }

    def run_inline_tool_loop(
        self, *, recorder, user_id, user_message, project_id,
        session_id=None, prompt_payload_format=None, context_mode=None,
        max_tool_call_rounds=None,
        requirement_id=None, container_key="requirement_agent",
        node_key_prefix="requirement_agent",
    ):
        self.inline_calls.append({
            "recorder": recorder,
            "user_id": user_id,
            "user_message": user_message,
            "project_id": project_id,
            "session_id": session_id,
            "prompt_payload_format": prompt_payload_format,
            "context_mode": context_mode,
            "max_tool_call_rounds": max_tool_call_rounds,
            "requirement_id": requirement_id,
            "container_key": container_key,
            "node_key_prefix": node_key_prefix,
        })
        # Simulate writing a tool loop round node into the recorder
        node_key = recorder.stage_node_key(f"{node_key_prefix}_tool_loop_round_1")
        recorder.start_stage(
            node_key=node_key,
            label=recorder.stage_label("Tool Loop Round 1"),
            node_type="llm",
            role_type="agent",
            container_key=container_key,
            created_by=user_id,
            input_summary={"round": 1},
            edge_type_from_previous="seq",
        )
        recorder.complete_stage(
            node_key, created_by=user_id,
            output_summary={"reply": self._inline_result.get("tool_loop_reply")},
        )
        return dict(self._inline_result)

    def stream_inline_tool_loop(
        self, *, recorder, user_id, user_message, project_id,
        session_id=None, prompt_payload_format=None, context_mode=None,
        max_tool_call_rounds=None,
        requirement_id=None, container_key="requirement_agent",
        node_key_prefix="requirement_agent",
    ):
        result = self.run_inline_tool_loop(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            project_id=project_id,
            session_id=session_id,
            prompt_payload_format=prompt_payload_format,
            context_mode=context_mode,
            max_tool_call_rounds=max_tool_call_rounds,
            requirement_id=requirement_id,
            container_key=container_key,
            node_key_prefix=node_key_prefix,
        )
        yield {
            "event": "stage",
            "data": {
                "graph_id": recorder.graph_id,
                "node_key": recorder.stage_node_key(f"{node_key_prefix}_tool_loop_round_1"),
                "status": "succeeded",
            },
        }
        return result


class _FakeConflictAgentService:
    """Fake that exposes run_inline_tool_loop."""

    def __init__(self):
        self.inline_calls = []

    def run_inline_tool_loop(
        self, *, recorder, user_id, user_message, project_id,
        max_tool_call_rounds=None,
        container_key="conflict_detection", node_key_prefix="conflict_agent",
    ):
        self.inline_calls.append({
            "recorder": recorder,
            "user_id": user_id,
            "user_message": user_message,
            "project_id": project_id,
            "max_tool_call_rounds": max_tool_call_rounds,
            "container_key": container_key,
            "node_key_prefix": node_key_prefix,
        })
        node_key = recorder.stage_node_key(f"{node_key_prefix}_tool_loop_round_1")
        recorder.start_stage(
            node_key=node_key,
            label=recorder.stage_label("Tool Loop Round 1"),
            node_type="llm",
            role_type="agent",
            container_key=container_key,
            created_by=user_id,
            input_summary={"round": 1},
            edge_type_from_previous="seq",
        )
        recorder.complete_stage(
            node_key, created_by=user_id,
            output_summary={"reply": "检测完成"},
        )
        return {"status": "success", "tool_loop_reply": "检测完成"}

    def stream_inline_tool_loop(
        self, *, recorder, user_id, user_message, project_id,
        max_tool_call_rounds=None,
        container_key="conflict_detection", node_key_prefix="conflict_agent",
    ):
        result = self.run_inline_tool_loop(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            project_id=project_id,
            max_tool_call_rounds=max_tool_call_rounds,
            container_key=container_key,
            node_key_prefix=node_key_prefix,
        )
        yield {
            "event": "stage",
            "data": {
                "graph_id": recorder.graph_id,
                "node_key": recorder.stage_node_key(f"{node_key_prefix}_tool_loop_round_1"),
                "status": "succeeded",
            },
        }
        return result


class _FakeRequirementClassificationAgentService:
    """Fake that exposes run_inline_tool_loop for requirement classification."""

    def __init__(self, *, inline_result=None):
        self.inline_calls = []
        self._inline_result = inline_result or {
            "status": "success",
            "tool_loop_reply": "已完成需求分类",
            "resolved_requirement_id": "REQ-1",
            "classification_result": {
                "requirement_id": "REQ-1",
                "level": "L2",
                "requirement_nature": "functional",
                "domain_tags": ["需求管理"],
                "priority_suggestion": "P2",
            },
        }

    def run_inline_tool_loop(
        self, *, recorder, user_id, user_message, project_id,
        requirement_id=None, container_key="requirement_classification_agent",
        node_key_prefix="requirement_classification_agent",
    ):
        self.inline_calls.append({
            "recorder": recorder,
            "user_id": user_id,
            "user_message": user_message,
            "project_id": project_id,
            "requirement_id": requirement_id,
            "container_key": container_key,
            "node_key_prefix": node_key_prefix,
        })
        node_key = recorder.stage_node_key(f"{node_key_prefix}_tool_loop_round_1")
        recorder.start_stage(
            node_key=node_key,
            label=recorder.stage_label("Tool Loop Round 1"),
            node_type="llm",
            role_type="agent",
            container_key=container_key,
            created_by=user_id,
            input_summary={"round": 1},
            edge_type_from_previous="seq",
        )
        recorder.complete_stage(
            node_key,
            created_by=user_id,
            output_summary={"reply": self._inline_result.get("tool_loop_reply")},
        )
        return dict(self._inline_result)

    def stream_inline_tool_loop(
        self, *, recorder, user_id, user_message, project_id,
        requirement_id=None, container_key="requirement_classification_agent",
        node_key_prefix="requirement_classification_agent",
    ):
        result = self.run_inline_tool_loop(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            project_id=project_id,
            requirement_id=requirement_id,
            container_key=container_key,
            node_key_prefix=node_key_prefix,
        )
        yield {
            "event": "stage",
            "data": {
                "graph_id": recorder.graph_id,
                "node_key": recorder.stage_node_key(f"{node_key_prefix}_tool_loop_round_1"),
                "status": "succeeded",
            },
        }
        return result


def _make_tools():
    return SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=_FakeRequirementAgentService(),
        conflict_agent_service=_FakeConflictAgentService(),
        requirement_classification_agent_service=_FakeRequirementClassificationAgentService(),
    )


def test_invoke_requirement_agent_records_expanded_nodes():
    """Requirement agent inline call should produce start + tool_loop + end nodes."""
    tools = _make_tools()
    recorder = _FakeRecorder()
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
        "session_id": "sess-1",
        "_graph_recorder": recorder,
        "_active_stage_node_key": "turn_1__session_controller_tool_loop_round_1",
        "tool_results": [],
        "dispatched_agents": [],
    }

    result = tools.execute(
        "invoke_requirement_agent",
        {"task_description": "读取 REQ-1 的详情", "requirement_id": "REQ-1"},
        context,
    )

    assert result["status"] == "success"
    assert result["resolved_requirement_id"] == "REQ-1"
    assert context["dispatched_agents"] == ["requirement_agent"]

    # Should have 3 nodes: start + tool_loop_round_1 + end
    assert len(recorder.started) == 3

    # First node: start with call edge
    start = recorder.started[0]
    assert start["container_key"] == "requirement_agent"
    assert start["node_type"] == "start"
    assert start["edge_type_from_previous"] == "call"
    assert "req_agent_1_start" in start["node_key"]

    # Second node: tool loop round (created by fake service)
    tool_loop = recorder.started[1]
    assert tool_loop["container_key"] == "requirement_agent"
    assert tool_loop["node_type"] == "llm"
    assert tool_loop["edge_type_from_previous"] == "seq"

    # Third node: end
    end = recorder.started[2]
    assert end["container_key"] == "requirement_agent"
    assert end["node_type"] == "end"
    assert end["edge_type_from_previous"] == "seq"
    assert "req_agent_1_end" in end["node_key"]

    # Return edge from end back to parent
    assert len(recorder.return_edges) == 1
    assert recorder.return_edges[0]["parent_node_key"] == "turn_1__session_controller_tool_loop_round_1"
    assert "req_agent_1_end" in recorder.return_edges[0]["child_node_key"]

    # Cursor restored to parent
    assert recorder.restored == [
        {"node_key": "turn_1__session_controller_tool_loop_round_1", "updated_by": "u-1"},
    ]


def test_invoke_requirement_agent_propagates_approval_pending_context():
    recorder = _FakeRecorder()
    tools = SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=_FakeRequirementAgentService(
            inline_result={
                "status": "success",
                "tool_loop_reply": "已发起审批",
                "resolved_requirement_id": "REQ-1",
                "write_result": None,
                "approval_pending": True,
                "approval_result": {
                    "approval_request_id": "apr-1",
                    "push_message_id": "msg-1",
                },
            }
        ),
        conflict_agent_service=_FakeConflictAgentService(),
    )
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
        "session_id": "sess-1",
        "_graph_recorder": recorder,
        "_active_stage_node_key": "turn_1__session_controller_tool_loop_round_1",
        "tool_results": [],
        "dispatched_agents": [],
    }

    result = tools.execute(
        "invoke_requirement_agent",
        {"task_description": "把 REQ-1 优先级改为高", "requirement_id": "REQ-1"},
        context,
    )

    assert result["approval_pending"] is True
    assert result["approval_result"]["approval_request_id"] == "apr-1"
    assert context["last_approval_result"]["push_message_id"] == "msg-1"
    assert "approval_pending" not in context


def test_invoke_requirement_agent_returns_clarification_contract():
    recorder = _FakeRecorder()
    tools = SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=_FakeRequirementAgentService(
            inline_result={
                "status": "success",
                "tool_loop_reply": "我发现两条标题相同的需求，请确认要修改哪一条。",
                "resolved_requirement_id": None,
                "write_result": None,
                "mode": "clarification",
                "clarification_required": True,
                "approval_pending": False,
                "approval_result": None,
            }
        ),
        conflict_agent_service=_FakeConflictAgentService(),
    )
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
        "session_id": "sess-1",
        "_graph_recorder": recorder,
        "_active_stage_node_key": "turn_1__session_controller_tool_loop_round_1",
        "tool_results": [],
        "dispatched_agents": [],
    }

    result = tools.execute(
        "invoke_requirement_agent",
        {"task_description": "把这条需求的优先级改成高"},
        context,
    )

    assert result["clarification_required"] is True
    assert result["mode"] == "clarify"
    assert result["clarification_question"] == "我发现两条标题相同的需求，请确认要修改哪一条。"
    assert "clarification_required" not in context
    assert "last_clarification_reply" not in context


def test_invoke_requirement_agent_passes_correct_params_to_inline():
    """Ensure run_inline_tool_loop receives the right parameters."""
    fake_service = _FakeRequirementAgentService()
    tools = SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=fake_service,
        conflict_agent_service=_FakeConflictAgentService(),
        requirement_classification_agent_service=_FakeRequirementClassificationAgentService(),
    )
    recorder = _FakeRecorder()
    context = {
        "project_id": "p-2",
        "user_id": "u-2",
        "session_id": "sess-2",
        "_graph_recorder": recorder,
        "_active_stage_node_key": "turn_1__session_controller_tool_loop_round_1",
        "tool_results": [],
        "dispatched_agents": [],
    }

    tools.execute(
        "invoke_requirement_agent",
        {"task_description": "修改 REQ-2 的标题", "requirement_id": "REQ-2"},
        context,
    )

    assert len(fake_service.inline_calls) == 1
    call = fake_service.inline_calls[0]
    assert call["user_id"] == "u-2"
    assert call["project_id"] == "p-2"
    assert call["session_id"] == "sess-2"
    assert call["prompt_payload_format"] == "markdown"
    assert call["context_mode"] == "full"
    assert call["max_tool_call_rounds"] == 15
    assert call["user_message"] == "修改 REQ-2 的标题"
    assert call["requirement_id"] == "REQ-2"
    assert call["container_key"] == "requirement_agent"
    assert call["node_key_prefix"] == "req_agent_1"


def test_invoke_requirement_agent_falls_back_to_resolved_requirement_id():
    fake_service = _FakeRequirementAgentService()
    tools = SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=fake_service,
        conflict_agent_service=_FakeConflictAgentService(),
    )
    recorder = _FakeRecorder()
    context = {
        "project_id": "p-2",
        "user_id": "u-2",
        "session_id": "sess-2",
        "resolved_requirement_id": "REQ-9",
        "_graph_recorder": recorder,
        "_active_stage_node_key": "turn_1__session_controller_tool_loop_round_1",
        "tool_results": [],
        "dispatched_agents": [],
    }

    tools.execute(
        "invoke_requirement_agent",
        {"task_description": "把这个需求的优先级改成低"},
        context,
    )

    assert len(fake_service.inline_calls) == 1
    assert fake_service.inline_calls[0]["requirement_id"] == "REQ-9"


def test_streaming_invoke_requirement_agent_yields_nested_stage_events():
    tools = _make_tools()
    recorder = _FakeRecorder()
    context = {
        "project_id": "p-3",
        "user_id": "u-3",
        "session_id": "sess-3",
        "graph_id": recorder.graph_id,
        "_graph_recorder": recorder,
        "_active_stage_node_key": "turn_1__session_controller_tool_loop_round_1",
        "tool_results": [],
        "dispatched_agents": [],
    }

    gen = tools.execute_streaming(
        "invoke_requirement_agent",
        {"task_description": "读取 REQ-3", "requirement_id": "REQ-3"},
        context,
    )

    events = []
    result = None
    try:
        while True:
            events.append(next(gen))
    except StopIteration as stop:
        result = stop.value

    assert result["status"] == "success"
    assert [event["data"]["node_key"] for event in events] == [
        "turn_1__req_agent_1_start",
        "turn_1__req_agent_1_tool_loop_round_1",
        "turn_1__req_agent_1_end",
    ]
    assert all(event["event"] == "stage" for event in events)
    assert all(event["data"]["status"] == "succeeded" for event in events)


def test_invoke_conflict_detection_records_expanded_nodes():
    """Conflict detection inline call should produce start + tool_loop + end nodes."""
    tools = _make_tools()
    recorder = _FakeRecorder()
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
        "session_id": "sess-1",
        "_graph_recorder": recorder,
        "_active_stage_node_key": "turn_2__session_controller_tool_loop_round_1",
        "tool_results": [{"tool_name": "list_requirements"}],
        "dispatched_agents": [],
    }

    result = tools.execute(
        "invoke_conflict_detection",
        {"task_description": "检测 REQ-1 和 REQ-2 是否冲突"},
        context,
    )

    assert result["status"] == "success"
    assert result["reply"] == "检测完成"
    assert context["dispatched_agents"] == ["conflict_detection"]

    # Should have 3 nodes: start + tool_loop_round_1 + end
    assert len(recorder.started) == 3

    start = recorder.started[0]
    assert start["container_key"] == "conflict_detection"
    assert start["node_type"] == "start"
    assert start["edge_type_from_previous"] == "call"
    assert "conflict_agent_2_start" in start["node_key"]

    end = recorder.started[2]
    assert end["container_key"] == "conflict_detection"
    assert end["node_type"] == "end"
    assert "conflict_agent_2_end" in end["node_key"]

    assert len(recorder.return_edges) == 1
    assert recorder.return_edges[0]["parent_node_key"] == "turn_2__session_controller_tool_loop_round_1"
    assert tools._conflict_agent_service.inline_calls[0]["max_tool_call_rounds"] == 15


def test_invoke_requirement_classification_agent_records_expanded_nodes():
    tools = _make_tools()
    recorder = _FakeRecorder()
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
        "_graph_recorder": recorder,
        "_active_stage_node_key": "turn_1__session_controller_tool_loop_round_1",
        "tool_results": [],
        "dispatched_agents": [],
    }

    result = tools.execute(
        "invoke_requirement_classification_agent",
        {"task_description": "分类 REQ-1", "requirement_id": "REQ-1"},
        context,
    )

    assert result["status"] == "success"
    assert result["resolved_requirement_id"] == "REQ-1"
    assert result["classification_result"]["level"] == "L2"
    assert context["dispatched_agents"] == ["requirement_classification_agent"]

    assert len(recorder.started) == 3
    start = recorder.started[0]
    assert start["container_key"] == "requirement_classification_agent"
    assert start["node_type"] == "start"
    assert start["edge_type_from_previous"] == "call"
    assert "classification_agent_1_start" in start["node_key"]

    tool_loop = recorder.started[1]
    assert tool_loop["container_key"] == "requirement_classification_agent"
    assert tool_loop["node_type"] == "llm"

    end = recorder.started[2]
    assert end["container_key"] == "requirement_classification_agent"
    assert end["node_type"] == "end"
    assert "classification_agent_1_end" in end["node_key"]

    assert len(recorder.return_edges) == 1
    assert recorder.return_edges[0]["parent_node_key"] == "turn_1__session_controller_tool_loop_round_1"
    assert recorder.restored == [
        {"node_key": "turn_1__session_controller_tool_loop_round_1", "updated_by": "u-1"},
    ]


def test_invoke_requirement_classification_agent_passes_correct_params_to_inline():
    fake_service = _FakeRequirementClassificationAgentService()
    tools = SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=_FakeRequirementAgentService(),
        conflict_agent_service=_FakeConflictAgentService(),
        requirement_classification_agent_service=fake_service,
    )
    recorder = _FakeRecorder()
    context = {
        "project_id": "p-2",
        "user_id": "u-2",
        "_graph_recorder": recorder,
        "_active_stage_node_key": "turn_1__session_controller_tool_loop_round_1",
        "tool_results": [],
        "dispatched_agents": [],
    }

    tools.execute(
        "invoke_requirement_classification_agent",
        {"task_description": "分类 REQ-2", "requirement_id": "REQ-2"},
        context,
    )

    assert len(fake_service.inline_calls) == 1
    call = fake_service.inline_calls[0]
    assert call["user_id"] == "u-2"
    assert call["project_id"] == "p-2"
    assert call["user_message"] == "分类 REQ-2"
    assert call["requirement_id"] == "REQ-2"
    assert call["container_key"] == "requirement_classification_agent"
    assert call["node_key_prefix"] == "classification_agent_1"


def test_invoke_requirement_agent_handles_inline_error():
    """If the inline tool loop raises, proper error nodes and return edges are recorded."""
    class _FailingService:
        def run_inline_tool_loop(self, **kwargs):
            raise RuntimeError("LLM 连接失败")

        def stream_inline_tool_loop(self, **kwargs):
            raise RuntimeError("LLM 连接失败")

    tools = SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=_FailingService(),
        conflict_agent_service=_FakeConflictAgentService(),
        requirement_classification_agent_service=_FakeRequirementClassificationAgentService(),
    )
    recorder = _FakeRecorder()
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
        "session_id": "sess-1",
        "_graph_recorder": recorder,
        "_active_stage_node_key": "turn_1__session_controller_tool_loop_round_1",
        "tool_results": [],
        "dispatched_agents": [],
    }

    result = tools.execute(
        "invoke_requirement_agent",
        {"task_description": "测试错误"},
        context,
    )

    assert result["status"] == "error"
    assert "LLM 连接失败" in result["error"]

    # Should have start + error-end nodes
    assert len(recorder.started) == 2
    assert recorder.started[0]["node_type"] == "start"
    assert recorder.started[1]["node_type"] == "end"

    # End node should be failed
    end_completed = recorder.completed[1]
    assert end_completed["success"] is False

    # Return edge and cursor restore still happen
    assert len(recorder.return_edges) == 1
    assert len(recorder.restored) == 1


def test_no_recorder_returns_error():
    """When no recorder is available, return an error dict."""
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

    assert result["status"] == "error"
    assert "recorder" in result["error"].lower()


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
        "_graph_recorder": recorder,
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

    stage_events = [
        event for event in events
        if event["event"] == "stage"
        and event["data"]["node_key"] in {
            "turn_1__req_agent_1_start",
            "turn_1__req_agent_1_tool_loop_round_1",
            "turn_1__req_agent_1_end",
        }
    ]

    assert [event["data"]["node_key"] for event in stage_events] == [
        "turn_1__req_agent_1_start",
        "turn_1__req_agent_1_tool_loop_round_1",
        "turn_1__req_agent_1_end",
    ]
    assert runner.ai_proxy.calls == 2
    assert result.tool_loop_reply == "已读取需求详情"
