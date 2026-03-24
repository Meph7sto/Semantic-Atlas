"""
Unit tests for session controller tools.
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
    def __init__(self):
        self.started = []
        self.completed = []
        self.restored = []

    def start_stage(self, **kwargs):
        self.started.append(kwargs)

    def complete_stage(self, node_key, **kwargs):
        self.completed.append({"node_key": node_key, **kwargs})

    def restore_stage_cursor(self, *, node_key, updated_by=""):
        self.restored.append({"node_key": node_key, "updated_by": updated_by})


class _FakeRequirementAgentService:
    def __init__(self):
        self.create_calls = []
        self.stream_calls = []

    def create_session(self, *, user_id, project_id, title):
        self.create_calls.append(
            {"user_id": user_id, "project_id": project_id, "title": title}
        )
        return {"session_id": "sub-sess-1"}

    def stream_requirement_agent_reply(
        self,
        *,
        session_id,
        user_id,
        project_id,
        user_message,
        requirement_id,
    ):
        self.stream_calls.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "project_id": project_id,
                "user_message": user_message,
                "requirement_id": requirement_id,
            }
        )
        yield {"event": "assistant_message", "data": {"content": "子 agent 已处理"}}
        yield {
            "event": "result",
            "data": {
                "graph_id": "sub-graph-1",
                "mode": "read",
                "resolved_requirement_id": "REQ-1",
                "write_result": None,
            },
        }


class _FakeConflictAgentService:
    def __init__(self):
        self.create_calls = []
        self.stream_calls = []

    def create_session(self, *, user_id, project_id, title):
        self.create_calls.append(
            {"user_id": user_id, "project_id": project_id, "title": title}
        )
        return {"session_id": "sub-sess-2"}

    def stream_conflict_agent_reply(
        self,
        *,
        session_id,
        user_id,
        project_id,
        user_message,
    ):
        self.stream_calls.append(
            {
                "session_id": session_id,
                "user_id": user_id,
                "project_id": project_id,
                "user_message": user_message,
            }
        )
        yield {"event": "assistant_message", "data": {"content": "检测完成"}}
        yield {"event": "result", "data": {"graph_id": "sub-graph-2"}}


def _make_tools():
    return SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=_FakeRequirementAgentService(),
        conflict_agent_service=_FakeConflictAgentService(),
    )


def test_invoke_requirement_agent_records_visible_child_stage_and_dispatch():
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
    assert result["sub_graph_id"] == "sub-graph-1"
    assert context["dispatched_agents"] == ["requirement_agent"]
    assert recorder.started[0]["container_key"] == "requirement_agent"
    assert recorder.started[0]["edge_type_from_previous"] == "call"
    assert recorder.completed[0]["node_key"].endswith("__delegate_requirement_agent_1")
    assert recorder.completed[0]["output_summary"]["sub_graph_id"] == "sub-graph-1"
    assert recorder.restored == [
        {
            "node_key": "turn_1__session_controller_tool_loop_round_1",
            "updated_by": "u-1",
        }
    ]


def test_invoke_conflict_detection_records_visible_child_stage_and_dispatch():
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

    assert result == {
        "status": "success",
        "reply": "检测完成",
        "sub_graph_id": "sub-graph-2",
    }
    assert context["dispatched_agents"] == ["conflict_detection"]
    assert recorder.started[0]["container_key"] == "conflict_detection"
    assert recorder.started[0]["node_key"].endswith("__delegate_conflict_detection_2")
    assert recorder.completed[0]["output_summary"]["sub_graph_id"] == "sub-graph-2"
