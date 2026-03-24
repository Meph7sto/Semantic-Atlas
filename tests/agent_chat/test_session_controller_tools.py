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
        requirement_id=None, container_key="requirement_agent",
        node_key_prefix="requirement_agent",
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


class _FakeConflictAgentService:
    """Fake that exposes run_inline_tool_loop."""

    def __init__(self):
        self.inline_calls = []

    def run_inline_tool_loop(
        self, *, recorder, user_id, user_message, project_id,
        container_key="conflict_detection", node_key_prefix="conflict_agent",
    ):
        self.inline_calls.append({
            "recorder": recorder,
            "user_id": user_id,
            "user_message": user_message,
            "project_id": project_id,
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


def _make_tools():
    return SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=_FakeRequirementAgentService(),
        conflict_agent_service=_FakeConflictAgentService(),
    )


def test_invoke_requirement_agent_records_expanded_nodes():
    """Requirement agent inline call should produce start + tool_loop + end nodes."""
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


def test_invoke_requirement_agent_passes_correct_params_to_inline():
    """Ensure run_inline_tool_loop receives the right parameters."""
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
    assert call["user_message"] == "修改 REQ-2 的标题"
    assert call["requirement_id"] == "REQ-2"
    assert call["container_key"] == "requirement_agent"
    assert call["node_key_prefix"] == "req_agent_1"


def test_invoke_conflict_detection_records_expanded_nodes():
    """Conflict detection inline call should produce start + tool_loop + end nodes."""
    tools = _make_tools()
    recorder = _FakeRecorder()
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
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


def test_invoke_requirement_agent_handles_inline_error():
    """If the inline tool loop raises, proper error nodes and return edges are recorded."""
    class _FailingService:
        def run_inline_tool_loop(self, **kwargs):
            raise RuntimeError("LLM 连接失败")

    tools = SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=_FailingService(),
        conflict_agent_service=_FakeConflictAgentService(),
    )
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
