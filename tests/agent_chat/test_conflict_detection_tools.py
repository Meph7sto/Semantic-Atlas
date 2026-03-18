"""
Unit tests for conflict detection tools.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.tools import ConflictDetectionTools  # noqa: E402


class _FakeRequirementsService:
    def __init__(self):
        self.requirements = {
            "r-1": {
                "req_id": "r-1",
                "project_id": "p-1",
                "deleted": False,
                "title": "登录性能",
                "description": "系统在 3 秒内完成登录",
                "acceptance_criteria": "3 秒内展示首页",
                "notes": "",
                "status": "draft",
                "priority": "high",
                "parent_id": None,
                "order_index": 1,
            },
            "r-2": {
                "req_id": "r-2",
                "project_id": "p-1",
                "deleted": False,
                "title": "系统响应时间不低于 5 秒",
                "description": "系统任何操作响应时间不应低于 5 秒",
                "acceptance_criteria": "",
                "notes": "",
                "status": "draft",
                "priority": "medium",
                "parent_id": None,
                "order_index": 2,
            },
            "r-deleted": {
                "req_id": "r-deleted",
                "project_id": "p-1",
                "deleted": True,
                "title": "已删除需求",
                "description": "这条已经被删除了",
            },
        }
        self.list_calls = []

    def list_requirements_window(self, project_id, start_index, count, include_deleted=False):
        self.list_calls.append((project_id, start_index, count, include_deleted))
        items = [v for v in self.requirements.values() if not v.get("deleted")]
        return {
            "total": len(items),
            "start_index": start_index,
            "count": len(items),
            "has_more": False,
            "items": items,
        }

    def get_requirement(self, requirement_id):
        return self.requirements.get(requirement_id)


def _make_tools(service=None, conflict_fn=None):
    service = service or _FakeRequirementsService()
    conflict_fn = conflict_fn or (lambda a, b: {"is_conflict": True, "raw_response": "存在冲突"})
    return ConflictDetectionTools(
        requirements_service=service,
        conflict_check_fn=conflict_fn,
    ), service


def test_get_tools_list_contains_expected_schemas():
    tools_list = ConflictDetectionTools.get_tools_list()
    tool_names = [t["function"]["name"] for t in tools_list]
    assert tool_names == ["list_requirements", "get_requirement_detail", "check_conflict"]

    # check_conflict schema
    check_schema = tools_list[2]["function"]["parameters"]
    assert set(check_schema["required"]) == {"requirement_id_a", "requirement_id_b"}

    # list_requirements window defaults
    list_schema = tools_list[0]["function"]["parameters"]
    assert list_schema["properties"]["start_index"]["default"] == 1
    assert list_schema["properties"]["count"]["default"] == 10
    assert list_schema["properties"]["count"]["maximum"] == 20


def test_execute_list_requirements():
    tools, service = _make_tools()
    context = {"project_id": "p-1"}

    result = tools.execute("list_requirements", {"start_index": 1, "count": 10}, context)

    assert result["total"] == 2
    assert len(result["items"]) == 2
    assert result["items"][0]["requirement_id"] == "r-1"
    assert service.list_calls == [("p-1", 1, 10, False)]


def test_execute_list_requirements_validates_count():
    tools, _ = _make_tools()
    context = {"project_id": "p-1"}

    with pytest.raises(ValueError, match="count 不能大于 20"):
        tools.execute("list_requirements", {"count": 21}, context)


def test_execute_get_requirement_detail():
    tools, _ = _make_tools()
    context = {"project_id": "p-1"}

    result = tools.execute("get_requirement_detail", {"requirement_id": "r-1"}, context)

    assert result["requirement_id"] == "r-1"
    assert result["title"] == "登录性能"
    assert result["description"] == "系统在 3 秒内完成登录"


def test_execute_get_requirement_detail_deleted_raises():
    tools, _ = _make_tools()
    context = {"project_id": "p-1"}

    with pytest.raises(ValueError, match="不存在或已删除"):
        tools.execute("get_requirement_detail", {"requirement_id": "r-deleted"}, context)


def test_execute_get_requirement_detail_missing_raises():
    tools, _ = _make_tools()
    context = {"project_id": "p-1"}

    with pytest.raises(ValueError, match="不存在或已删除"):
        tools.execute("get_requirement_detail", {"requirement_id": "nonexistent"}, context)


def test_execute_check_conflict_success():
    conflict_calls = []

    def fake_conflict(a, b):
        conflict_calls.append((a, b))
        return {"is_conflict": True, "raw_response": "二者在响应时间要求上矛盾"}

    tools, _ = _make_tools(conflict_fn=fake_conflict)
    context = {"project_id": "p-1"}

    result = tools.execute(
        "check_conflict",
        {"requirement_id_a": "r-1", "requirement_id_b": "r-2"},
        context,
    )

    assert result["is_conflict"] is True
    assert result["requirement_id_a"] == "r-1"
    assert result["requirement_id_b"] == "r-2"
    assert "矛盾" in result["raw_response"]
    assert len(conflict_calls) == 1
    assert "登录性能" in conflict_calls[0][0]
    assert "5 秒" in conflict_calls[0][1]


def test_execute_check_conflict_missing_requirement():
    tools, _ = _make_tools()
    context = {"project_id": "p-1"}

    with pytest.raises(ValueError, match="不存在或已删除"):
        tools.execute(
            "check_conflict",
            {"requirement_id_a": "r-1", "requirement_id_b": "nonexistent"},
            context,
        )


def test_execute_unknown_tool_raises():
    tools, _ = _make_tools()
    context = {"project_id": "p-1"}

    with pytest.raises(ValueError, match="未知工具"):
        tools.execute("nonexistent_tool", {}, context)


def test_execute_with_string_arguments():
    tools, _ = _make_tools()
    context = {"project_id": "p-1"}

    result = tools.execute("list_requirements", '{"start_index": 1, "count": 5}', context)
    assert result["total"] == 2


def test_execute_with_none_arguments():
    tools, _ = _make_tools()
    context = {"project_id": "p-1"}

    result = tools.execute("list_requirements", None, context)
    assert result["total"] == 2
