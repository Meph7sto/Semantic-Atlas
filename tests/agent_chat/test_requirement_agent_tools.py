"""
Unit tests for requirement agent tools.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.tools import RequirementAgentTools  # noqa: E402


class _FakeRequirementsService:
    def __init__(self):
        self.requirements = {
            "r-1": {
                "req_id": "r-1",
                "project_id": "p-1",
                "deleted": False,
                "title": "登录性能",
                "description": "系统在 3 秒内完成登录",
            }
        }
        self.list_calls = []
        self.search_calls = []

    def list_requirements_window(self, project_id, start_index, count, include_deleted=False):
        self.list_calls.append((project_id, start_index, count, include_deleted))
        return {
            "total": 2,
            "start_index": start_index,
            "count": 2,
            "has_more": False,
            "items": [
                {
                    "req_id": "r-1",
                    "title": "登录性能",
                    "status": "draft",
                    "priority": "high",
                    "parent_id": None,
                    "order_index": 1,
                    "description": "系统在 3 秒内完成登录",
                },
                {
                    "req_id": "r-2",
                    "title": "注册",
                    "status": "draft",
                    "priority": "medium",
                    "parent_id": None,
                    "order_index": 2,
                    "description": "用户可以注册账号",
                },
            ],
        }

    def search_requirements(self, project_id, keyword, start_index, count, include_deleted=False):
        self.search_calls.append((project_id, keyword, start_index, count, include_deleted))
        return {
            "total": 1,
            "start_index": start_index,
            "count": 1,
            "has_more": False,
            "items": [
                {
                    "req_id": "r-1",
                    "title": "登录性能",
                    "status": "draft",
                    "priority": "high",
                    "parent_id": None,
                    "order_index": 1,
                    "description": "系统在 3 秒内完成登录",
                }
            ],
        }

    def get_requirement(self, requirement_id):
        return self.requirements.get(requirement_id)


def test_get_tools_list_contains_expected_schemas():
    tools = RequirementAgentTools.get_tools_list()
    tool_names = [tool["function"]["name"] for tool in tools]

    assert tool_names == [
        "search_requirements",
        "list_requirements",
        "get_requirement_state",
        "update_requirement_content",
    ]

    search_schema = tools[0]["function"]["parameters"]
    assert search_schema["required"] == ["keyword"]
    assert search_schema["properties"]["start_index"]["default"] == 1
    assert search_schema["properties"]["count"]["default"] == 10
    assert search_schema["properties"]["count"]["maximum"] == 20

    update_schema = tools[3]["function"]["parameters"]["properties"]["updates"]
    assert update_schema["additionalProperties"] is False
    assert set(update_schema["properties"].keys()) == {
        "title",
        "description",
        "acceptance_criteria",
        "priority",
        "notes",
    }


def test_execute_list_requirements_returns_window_summary():
    service = _FakeRequirementsService()
    tools = RequirementAgentTools(
        requirements_service=service,
        actor_query_fn=lambda _actor_manager, _requirement_id: {},
        actor_write_fn=lambda _actor_manager, _requirement_id, _command: {},
    )
    context = {"project_id": "p-1", "resolved_requirement_ids": set()}

    result = tools.execute("list_requirements", {"start_index": 1, "count": 2}, context)

    assert result["total"] == 2
    assert result["count"] == 2
    assert result["items"][0]["requirement_id"] == "r-1"
    assert service.list_calls == [("p-1", 1, 2, False)]


def test_execute_search_requirements_validates_keyword_and_returns_total():
    service = _FakeRequirementsService()
    tools = RequirementAgentTools(
        requirements_service=service,
        actor_query_fn=lambda _actor_manager, _requirement_id: {},
        actor_write_fn=lambda _actor_manager, _requirement_id, _command: {},
    )
    context = {"project_id": "p-1", "resolved_requirement_ids": set()}

    result = tools.execute("search_requirements", {"keyword": "登录"}, context)

    assert result["total"] == 1
    assert result["items"][0]["title"] == "登录性能"
    assert context["resolved_requirement_id"] == "r-1"

    with pytest.raises(ValueError, match="keyword 不能为空白"):
        tools.execute("search_requirements", {"keyword": "   "}, context)

    with pytest.raises(ValueError, match="count 不能大于 20"):
        tools.execute("list_requirements", {"count": 21}, context)


def test_execute_get_requirement_state_reads_actor():
    service = _FakeRequirementsService()
    tools = RequirementAgentTools(
        requirements_service=service,
        actor_query_fn=lambda _actor_manager, requirement_id: {
            "status": "success",
            "state": {
                "requirement_id": requirement_id,
                "version": 4,
                "status": "draft",
                "priority": "high",
                "content": {
                    "title": "登录性能",
                    "description": "系统在 3 秒内完成登录",
                    "acceptance_criteria": ["3 秒内展示首页"],
                },
            },
        },
        actor_write_fn=lambda _actor_manager, _requirement_id, _command: {},
    )
    context = {"project_id": "p-1", "resolved_requirement_ids": set(), "actor_manager": object()}

    result = tools.execute("get_requirement_state", {"requirement_id": "r-1"}, context)

    assert result["version"] == 4
    assert result["acceptance_criteria"] == ["3 秒内展示首页"]
    assert context["resolved_requirement_id"] == "r-1"


def test_execute_update_requirement_content_writes_actor_and_returns_summary():
    service = _FakeRequirementsService()
    write_commands = []

    tools = RequirementAgentTools(
        requirements_service=service,
        actor_query_fn=lambda _actor_manager, requirement_id: {
            "status": "success",
            "state": {
                "requirement_id": requirement_id,
                "version": 6,
                "status": "draft",
                "priority": "high",
                "content": {
                    "title": "新标题",
                    "description": "系统在 3 秒内完成登录",
                    "acceptance_criteria": ["3 秒内展示首页"],
                },
            },
        },
        actor_write_fn=lambda _actor_manager, _requirement_id, command: write_commands.append(command) or {
            "status": "success",
            "event_id": "evt-1",
        },
    )
    context = {
        "project_id": "p-1",
        "user_id": "u-1",
        "session_id": "sess-1",
        "graph_id": "graph-1",
        "actor_manager": object(),
        "selected_requirement_id": "r-1",
        "resolved_requirement_ids": {"r-1"},
    }

    result = tools.execute(
        "update_requirement_content",
        {"requirement_id": "r-1", "updates": {"title": "新标题", "priority": "high"}},
        context,
    )

    assert result["write_status"] == "success"
    assert result["event_id"] == "evt-1"
    assert result["version"] == 6
    assert write_commands[0]["updates"] == {"title": "新标题", "priority": "high"}
    assert context["write_performed"] is True
