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
                "acceptance_criteria": ["3 秒内展示首页"],
            },
            "r-2": {
                "req_id": "r-2",
                "project_id": "p-1",
                "deleted": False,
                "title": "登录页实现",
                "description": "提供用户名密码登录和首页跳转",
                "acceptance_criteria": ["登录成功后进入首页"],
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


class _FakeApprovalService:
    def __init__(self):
        self.calls = []

    def create_approval_request(
        self,
        *,
        project_id,
        requirement_id,
        requested_by,
        updates,
        session_id,
        graph_id,
        source_agent,
    ):
        self.calls.append(
            {
                "project_id": project_id,
                "requirement_id": requirement_id,
                "requested_by": requested_by,
                "updates": updates,
                "session_id": session_id,
                "graph_id": graph_id,
                "source_agent": source_agent,
            }
        )
        return {
            "approval_request_id": "apr-1",
            "push_message_id": "msg-1",
            "summary_text": "优先级 high -> high",
        }


class _FailingApprovalService:
    def __init__(self, message):
        self.message = message

    def create_approval_request(self, **kwargs):
        raise RuntimeError(self.message)


class _FakeTraceabilityProxy:
    def __init__(self):
        self.calls = []

    def trace_relation(self, high, low, max_new_tokens=800):
        self.calls.append(
            {
                "high": high,
                "low": low,
                "max_new_tokens": max_new_tokens,
            }
        )
        return {
            "has_relation": True,
            "relation_type": "realizes",
            "reason": "低层需求实现了顶层登录性能目标。",
        }


def test_get_tools_list_contains_expected_schemas():
    tools = RequirementAgentTools.get_tools_list()
    tool_names = [tool["function"]["name"] for tool in tools]

    assert tool_names == [
        "search_requirements",
        "list_requirements",
        "get_requirement_state",
        "update_requirement_content",
        "trace_requirement_relation",
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

    trace_schema = tools[4]["function"]["parameters"]
    assert trace_schema["required"] == [
        "high_level_requirement_id",
        "low_level_requirement_id",
    ]
    assert trace_schema["additionalProperties"] is False


def test_execute_list_requirements_returns_window_summary():
    service = _FakeRequirementsService()
    tools = RequirementAgentTools(
        requirements_service=service,
        actor_query_fn=lambda _actor_manager, _requirement_id: {},
        actor_write_fn=lambda _actor_manager, _requirement_id, _command: {},
        approval_service=_FakeApprovalService(),
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
        approval_service=_FakeApprovalService(),
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
        approval_service=_FakeApprovalService(),
    )
    context = {"project_id": "p-1", "resolved_requirement_ids": set(), "actor_manager": object()}

    result = tools.execute("get_requirement_state", {"requirement_id": "r-1"}, context)

    assert result["version"] == 4
    assert result["acceptance_criteria"] == ["3 秒内展示首页"]
    assert context["resolved_requirement_id"] == "r-1"


def test_execute_get_requirement_state_can_obtain_shared_actor_manager():
    service = _FakeRequirementsService()
    actor_manager = object()
    received_actor_managers = []
    tools = RequirementAgentTools(
        requirements_service=service,
        actor_query_fn=lambda resolved_actor_manager, requirement_id: (
            received_actor_managers.append(resolved_actor_manager)
            or {
                "status": "success",
                "state": {
                    "requirement_id": requirement_id,
                    "content": {"title": "登录性能"},
                },
            }
        ),
        actor_write_fn=lambda _actor_manager, _requirement_id, _command: {},
        approval_service=_FakeApprovalService(),
        actor_manager_getter=lambda: actor_manager,
    )
    context = {"project_id": "p-1", "resolved_requirement_ids": set()}

    tools.execute("get_requirement_state", {"requirement_id": "r-1"}, context)

    assert received_actor_managers == [actor_manager]
    assert context["actor_manager"] is actor_manager


def test_execute_update_requirement_content_creates_approval_and_returns_summary():
    service = _FakeRequirementsService()
    approval_service = _FakeApprovalService()

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
        actor_write_fn=lambda _actor_manager, _requirement_id, _command: {
            "status": "success",
            "event_id": "evt-1",
        },
        approval_service=approval_service,
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

    assert result["write_status"] == "approval_pending"
    assert result["approval_request_id"] == "apr-1"
    assert result["push_message_id"] == "msg-1"
    assert result["version"] == 6
    assert approval_service.calls[0]["updates"] == {"title": "新标题", "priority": "high"}
    assert context["approval_pending"] is True


def test_execute_update_requirement_content_surfaces_actionable_approval_error():
    service = _FakeRequirementsService()
    tools = RequirementAgentTools(
        requirements_service=service,
        actor_query_fn=lambda _actor_manager, _requirement_id: {"status": "success", "state": {}},
        actor_write_fn=lambda _actor_manager, _requirement_id, _command: {},
        approval_service=_FailingApprovalService(
            "审批记录写入失败，请检查数据库连接以及 requirement_change_approvals 表是否已初始化。"
        ),
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

    with pytest.raises(ValueError, match="requirement_change_approvals 表是否已初始化"):
        tools.execute(
            "update_requirement_content",
            {"requirement_id": "r-1", "updates": {"priority": "low"}},
            context,
        )


def test_execute_update_requirement_content_keeps_approval_pending_when_state_refresh_fails():
    service = _FakeRequirementsService()
    approval_service = _FakeApprovalService()
    tools = RequirementAgentTools(
        requirements_service=service,
        actor_query_fn=lambda _actor_manager, _requirement_id: {"status": "error"},
        actor_write_fn=lambda _actor_manager, _requirement_id, _command: {},
        approval_service=approval_service,
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
        {"requirement_id": "r-1", "updates": {"priority": "low"}},
        context,
    )

    assert result["write_status"] == "approval_pending"
    assert result["requirement_id"] == "r-1"
    assert result["title"] == "登录性能"
    assert result["priority"] is None
    assert context["approval_pending"] is True


def test_execute_trace_requirement_relation_uses_real_project_requirements():
    service = _FakeRequirementsService()
    trace_proxy = _FakeTraceabilityProxy()
    tools = RequirementAgentTools(
        requirements_service=service,
        actor_query_fn=lambda _actor_manager, _requirement_id: {},
        actor_write_fn=lambda _actor_manager, _requirement_id, _command: {},
        approval_service=_FakeApprovalService(),
        ai_proxy_client=trace_proxy,
    )
    context = {"project_id": "p-1", "resolved_requirement_ids": set()}

    result = tools.execute(
        "trace_requirement_relation",
        {
            "high_level_requirement_id": "r-1",
            "low_level_requirement_id": "r-2",
        },
        context,
    )

    assert result["high_level_requirement"]["requirement_id"] == "r-1"
    assert result["low_level_requirement"]["requirement_id"] == "r-2"
    assert result["relation"]["relation_type"] == "realizes"
    assert "需求 ID: r-1" in trace_proxy.calls[0]["high"]
    assert "系统在 3 秒内完成登录" in trace_proxy.calls[0]["high"]
    assert "需求 ID: r-2" in trace_proxy.calls[0]["low"]
    assert context["traceability_result"] == result
    assert context["resolved_requirement_ids"] == {"r-1", "r-2"}

    metadata = tools.get_tool_execution_metadata(
        "trace_requirement_relation",
        {
            "high_level_requirement_id": "r-1",
            "low_level_requirement_id": "r-2",
        },
        context,
    )
    assert metadata.read_only is True
    assert metadata.idempotent is True
    assert metadata.concurrency_group == "traceability"
    assert metadata.resource_key == "traceability:p-1:r-1:r-2"


def test_execute_trace_requirement_relation_rejects_invalid_pair_or_unavailable_service():
    service = _FakeRequirementsService()
    tools = RequirementAgentTools(
        requirements_service=service,
        actor_query_fn=lambda _actor_manager, _requirement_id: {},
        actor_write_fn=lambda _actor_manager, _requirement_id, _command: {},
        approval_service=_FakeApprovalService(),
    )
    context = {"project_id": "p-1", "resolved_requirement_ids": set()}

    with pytest.raises(ValueError, match="不能是同一条需求"):
        tools.execute(
            "trace_requirement_relation",
            {
                "high_level_requirement_id": "r-1",
                "low_level_requirement_id": "r-1",
            },
            context,
        )

    with pytest.raises(RuntimeError, match="需求追溯服务不可用"):
        tools.execute(
            "trace_requirement_relation",
            {
                "high_level_requirement_id": "r-1",
                "low_level_requirement_id": "r-2",
            },
            context,
        )
