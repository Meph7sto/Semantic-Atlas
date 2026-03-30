"""
Unit tests for requirement classification tools.
"""

from __future__ import annotations

import os
import sys

import pytest

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.tools import RequirementClassificationTools  # noqa: E402


class _FakeRequirementsService:
    def __init__(self):
        self.requirements = {
            "r-1": {
                "req_id": "r-1",
                "project_id": "p-1",
                "deleted": False,
                "title": "系统应支持批量导入需求数据",
                "description": "支持 CSV 文件导入并建立需求草稿",
                "acceptance_criteria": "上传 CSV 后可以生成需求草稿",
                "notes": "适用于需求管理场景",
                "status": "draft",
                "priority": "P2",
                "parent_id": None,
                "order_index": 1,
                "requirement_type": "top_level",
                "source_level": "L2",
                "tags": ["既有标签"],
            },
            "r-2": {
                "req_id": "r-2",
                "project_id": "p-1",
                "deleted": False,
                "title": "系统必须在 1 秒内响应查询请求",
                "description": "查询接口平均响应时间不超过 1 秒",
                "acceptance_criteria": "压测场景下 P95 小于 1 秒",
                "notes": "",
                "status": "draft",
                "priority": "P1",
                "parent_id": "r-1",
                "order_index": 2,
                "requirement_type": "low_level",
                "source_level": None,
                "tags": [],
            },
            "r-deleted": {
                "req_id": "r-deleted",
                "project_id": "p-1",
                "deleted": True,
                "title": "已删除需求",
                "description": "不应再被读取",
                "acceptance_criteria": "",
                "notes": "",
                "status": "archived",
                "priority": "P3",
                "parent_id": None,
                "order_index": 3,
                "requirement_type": "top_level",
                "source_level": "L3",
                "tags": [],
            },
        }
        self.list_calls = []
        self.search_calls = []

    def list_requirements_window(self, project_id, start_index, count, include_deleted=False):
        self.list_calls.append((project_id, start_index, count, include_deleted))
        items = [item for item in self.requirements.values() if not item.get("deleted")]
        return {
            "total": len(items),
            "start_index": start_index,
            "count": min(count, len(items)),
            "has_more": False,
            "items": items[:count],
        }

    def search_requirements(self, project_id, keyword, start_index, count, include_deleted=False):
        self.search_calls.append((project_id, keyword, start_index, count, include_deleted))
        items = [
            item
            for item in self.requirements.values()
            if (
                not item.get("deleted")
                and project_id == item.get("project_id")
                and keyword in (item.get("title") or "")
            )
        ]
        return {
            "total": len(items),
            "start_index": start_index,
            "count": min(count, len(items)),
            "has_more": False,
            "items": items[:count],
        }

    def get_requirement(self, requirement_id):
        return self.requirements.get(requirement_id)


def _make_tools(
    *,
    service: _FakeRequirementsService | None = None,
    classifier_result: dict | None = None,
    llm_result: dict | None = None,
):
    service = service or _FakeRequirementsService()
    classifier_calls = []
    llm_calls = []

    classifier_payload = classifier_result or {
        "total": 1,
        "predictions": [
            {
                "index": 0,
                "requirement": "系统应支持批量导入需求数据",
                "predicted_label": "功能性需求",
            }
        ],
    }
    llm_payload = llm_result or {
        "content": (
            '{"level":"L2","requirement_nature":"functional",'
            '"domain_tags":["需求管理","导入导出"],'
            '"priority_suggestion":"P2",'
            '"reasoning":"该需求描述的是系统能力，属于功能需求。",'
            '"evidence":["title: 系统应支持批量导入需求数据"]}'
        )
    }

    def fake_classify_texts(texts):
        classifier_calls.extend(texts)
        return classifier_payload

    def fake_chat_completion(*, messages, **kwargs):
        llm_calls.append({"messages": messages, "kwargs": kwargs})
        return llm_payload

    tools = RequirementClassificationTools(
        requirements_service=service,
        classify_texts_fn=fake_classify_texts,
        chat_completion_fn=fake_chat_completion,
    )
    return tools, service, classifier_calls, llm_calls


def test_get_tools_list_contains_expected_schemas():
    tools_list = RequirementClassificationTools.get_tools_list()
    tool_names = [tool["function"]["name"] for tool in tools_list]
    assert tool_names == [
        "list_requirements",
        "search_requirements",
        "get_requirement_detail",
        "classify_requirement",
    ]

    classify_schema = tools_list[3]["function"]["parameters"]
    assert set(classify_schema["required"]) == {"requirement_id"}


def test_execute_list_requirements():
    tools, service, _, _ = _make_tools()
    result = tools.execute("list_requirements", {"start_index": 1, "count": 10}, {"project_id": "p-1"})

    assert result["total"] == 2
    assert result["items"][0]["requirement_id"] == "r-1"
    assert service.list_calls == [("p-1", 1, 10, False)]


def test_execute_search_requirements():
    tools, service, _, _ = _make_tools()
    result = tools.execute(
        "search_requirements",
        {"keyword": "批量导入", "start_index": 1, "count": 10},
        {"project_id": "p-1"},
    )

    assert result["total"] == 1
    assert result["items"][0]["requirement_id"] == "r-1"
    assert service.search_calls == [("p-1", "批量导入", 1, 10, False)]


def test_execute_get_requirement_detail():
    tools, _, _, _ = _make_tools()
    result = tools.execute("get_requirement_detail", {"requirement_id": "r-1"}, {"project_id": "p-1"})

    assert result["requirement_id"] == "r-1"
    assert result["source_level"] == "L2"
    assert result["requirement_type"] == "top_level"
    assert result["tags"] == ["既有标签"]


def test_execute_classify_requirement_combines_structural_and_model_results():
    tools, _, classifier_calls, llm_calls = _make_tools()

    result = tools.execute("classify_requirement", {"requirement_id": "r-1"}, {"project_id": "p-1"})

    assert result["requirement_id"] == "r-1"
    assert result["title"] == "系统应支持批量导入需求数据"
    assert result["level"] == "L2"
    assert result["requirement_nature"] == "functional"
    assert result["domain_tags"] == ["需求管理", "导入导出"]
    assert result["priority_suggestion"] == "P2"
    assert result["raw_classifier_label"] == "功能性需求"
    assert classifier_calls == [
        "标题: 系统应支持批量导入需求数据\n描述: 支持 CSV 文件导入并建立需求草稿\n验收标准: 上传 CSV 后可以生成需求草稿\n备注: 适用于需求管理场景"
    ]
    assert len(llm_calls) == 1


def test_execute_classify_requirement_uses_low_level_for_l4():
    tools, _, _, _ = _make_tools(
        llm_result={
            "content": (
                '{"level":"L3","requirement_nature":"non_functional",'
                '"domain_tags":["性能"],'
                '"priority_suggestion":"P1",'
                '"reasoning":"低层实现约束。",'
                '"evidence":["description: 查询接口平均响应时间不超过 1 秒"]}'
            )
        }
    )

    result = tools.execute("classify_requirement", {"requirement_id": "r-2"}, {"project_id": "p-1"})

    assert result["level"] == "L4"
    assert result["priority_suggestion"] == "P1"


def test_execute_classify_requirement_allows_classifier_fallback_to_none():
    tools, _, _, _ = _make_tools(
        classifier_result={"total": 0, "predictions": []},
        llm_result={
            "content": (
                '{"level":"L2","requirement_nature":"functional",'
                '"domain_tags":["需求管理"],'
                '"priority_suggestion":"P2",'
                '"reasoning":"无法从分类模型取得标签，使用 LLM 补判。",'
                '"evidence":["title: 系统应支持批量导入需求数据"]}'
            )
        },
    )

    result = tools.execute("classify_requirement", {"requirement_id": "r-1"}, {"project_id": "p-1"})

    assert result["raw_classifier_label"] is None


def test_execute_classify_requirement_rejects_deleted_requirement():
    tools, _, _, _ = _make_tools()

    with pytest.raises(ValueError, match="不存在或已删除"):
        tools.execute("classify_requirement", {"requirement_id": "r-deleted"}, {"project_id": "p-1"})


def test_execute_classify_requirement_rejects_wrong_project():
    tools, _, _, _ = _make_tools()

    with pytest.raises(ValueError, match="不属于当前项目"):
        tools.execute("classify_requirement", {"requirement_id": "r-1"}, {"project_id": "p-2"})


def test_execute_classify_requirement_rejects_invalid_priority():
    tools, _, _, _ = _make_tools(
        llm_result={
            "content": (
                '{"level":"L2","requirement_nature":"functional",'
                '"domain_tags":["需求管理"],'
                '"priority_suggestion":"high",'
                '"reasoning":"无效优先级。",'
                '"evidence":["title: 系统应支持批量导入需求数据"]}'
            )
        }
    )

    with pytest.raises(ValueError, match="priority_suggestion"):
        tools.execute("classify_requirement", {"requirement_id": "r-1"}, {"project_id": "p-1"})


def test_execute_unknown_tool_raises():
    tools, _, _, _ = _make_tools()

    with pytest.raises(ValueError, match="未知工具"):
        tools.execute("nonexistent_tool", {}, {"project_id": "p-1"})
