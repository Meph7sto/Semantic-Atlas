"""Conflict detection agent tool definitions and execution helpers."""

from __future__ import annotations

import json
from typing import Any, Callable

from backend_business.services.agent.runtime.tool_scheduling import (
    ToolExecutionMetadata,
)
from backend_business.services.requirements_manage_service import RequirementsManageService


_LIST_ITEM_EXCERPT_LENGTH = 180


def _normalize_requirement_id(requirement_id: Any) -> str:
    normalized = str(requirement_id or "").strip()
    if not normalized:
        raise ValueError("requirement_id 不能为空")
    return normalized


def _normalize_window_arg(value: Any, *, default: int, field_name: str) -> int:
    if value is None:
        normalized = default
    else:
        normalized = int(value)
    if normalized < 1:
        raise ValueError(f"{field_name} 必须大于等于 1")
    if field_name == "count" and normalized > 20:
        raise ValueError("count 不能大于 20")
    return normalized


def _collapse_excerpt(text: Any) -> str:
    raw = str(text or "").strip()
    if not raw:
        return ""
    single_line = " ".join(raw.split())
    if len(single_line) <= _LIST_ITEM_EXCERPT_LENGTH:
        return single_line
    return f"{single_line[:_LIST_ITEM_EXCERPT_LENGTH - 3]}..."


def _summarize_list_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": item.get("req_id"),
        "title": item.get("title"),
        "status": item.get("status"),
        "priority": item.get("priority"),
        "parent_id": item.get("parent_id"),
        "order_index": item.get("order_index"),
        "description_excerpt": _collapse_excerpt(item.get("description")),
    }


def _requirement_detail(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "requirement_id": item.get("req_id"),
        "title": item.get("title"),
        "status": item.get("status"),
        "priority": item.get("priority"),
        "parent_id": item.get("parent_id"),
        "description": item.get("description") or "",
        "acceptance_criteria": item.get("acceptance_criteria") or "",
        "notes": item.get("notes") or "",
    }


class ConflictDetectionTools:
    """Conflict detection tool definitions and execution."""

    def __init__(
        self,
        *,
        requirements_service: RequirementsManageService,
        conflict_check_fn: Callable[[str, str], dict[str, Any]],
    ) -> None:
        self.requirements_service = requirements_service
        self._conflict_check_fn = conflict_check_fn

    @staticmethod
    def get_tools_list() -> list[dict[str, Any]]:
        window_properties = {
            "start_index": {
                "type": "integer",
                "minimum": 1,
                "default": 1,
                "description": "1-based 起始位置",
            },
            "count": {
                "type": "integer",
                "minimum": 1,
                "maximum": 20,
                "default": 10,
                "description": "窗口大小，默认 10，最大 20",
            },
        }
        return [
            {
                "type": "function",
                "function": {
                    "name": "list_requirements",
                    "description": "列出当前项目的需求（分页窗口），返回摘要信息。",
                    "parameters": {
                        "type": "object",
                        "properties": window_properties,
                        "required": [],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_requirement_detail",
                    "description": "获取单条需求的完整内容，包括描述、验收标准等。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "requirement_id": {
                                "type": "string",
                                "description": "需求 ID",
                            }
                        },
                        "required": ["requirement_id"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "check_conflict",
                    "description": "检测两条需求之间是否存在冲突。输入两条需求的 ID，返回冲突检测结果（是否冲突及分析说明）。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "requirement_id_a": {
                                "type": "string",
                                "description": "第一条需求的 ID",
                            },
                            "requirement_id_b": {
                                "type": "string",
                                "description": "第二条需求的 ID",
                            },
                        },
                        "required": ["requirement_id_a", "requirement_id_b"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    @staticmethod
    def get_tool_execution_metadata(
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> ToolExecutionMetadata:
        project_id = str(context.get("project_id") or "unknown").strip()
        resource_key = f"project:{project_id}"
        requirement_id = str(arguments.get("requirement_id") or "").strip()
        if requirement_id:
            resource_key = f"requirement:{project_id}:{requirement_id}"
        elif tool_name == "check_conflict":
            requirement_ids = sorted(
                str(arguments.get(key) or "").strip()
                for key in ("requirement_id_a", "requirement_id_b")
            )
            resource_key = f"conflict:{project_id}:{':'.join(requirement_ids)}"
        if tool_name in {
            "list_requirements",
            "get_requirement_detail",
            "check_conflict",
        }:
            return ToolExecutionMetadata(
                read_only=True,
                idempotent=True,
                resource_key=resource_key,
                concurrency_group="requirements",
            )
        return ToolExecutionMetadata()

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any] | str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        parsed_arguments = self._parse_arguments(arguments)
        if tool_name == "list_requirements":
            return self._execute_list_requirements(parsed_arguments, context)
        if tool_name == "get_requirement_detail":
            return self._execute_get_requirement_detail(parsed_arguments, context)
        if tool_name == "check_conflict":
            return self._execute_check_conflict(parsed_arguments, context)
        raise ValueError(f"未知工具: {tool_name}")

    @staticmethod
    def _parse_arguments(arguments: dict[str, Any] | str | None) -> dict[str, Any]:
        if arguments is None:
            return {}
        if isinstance(arguments, dict):
            return dict(arguments)
        if isinstance(arguments, str):
            text = arguments.strip()
            if not text:
                return {}
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("tool arguments 必须是对象")
            return parsed
        raise ValueError("tool arguments 格式无效")

    def _resolve_project_requirement(
        self,
        *,
        project_id: str,
        requirement_id: str,
    ) -> dict[str, Any]:
        requirement = self.requirements_service.get_requirement(requirement_id)
        if not requirement or requirement.get("deleted"):
            raise ValueError(f"需求 {requirement_id} 不存在或已删除")
        if requirement.get("project_id") != project_id:
            raise ValueError(f"需求 {requirement_id} 不属于当前项目")
        return requirement

    def _execute_list_requirements(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        start_index = _normalize_window_arg(
            arguments.get("start_index"), default=1, field_name="start_index"
        )
        count = _normalize_window_arg(arguments.get("count"), default=10, field_name="count")
        window = self.requirements_service.list_requirements_window(
            project_id=context["project_id"],
            start_index=start_index,
            count=count,
            include_deleted=False,
        )
        items = [_summarize_list_item(item) for item in window.get("items") or []]
        return {
            "total": window["total"],
            "start_index": window["start_index"],
            "count": window["count"],
            "has_more": window["has_more"],
            "items": items,
        }

    def _execute_get_requirement_detail(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        requirement_id = _normalize_requirement_id(arguments.get("requirement_id"))
        requirement = self._resolve_project_requirement(
            project_id=context["project_id"],
            requirement_id=requirement_id,
        )
        return _requirement_detail(requirement)

    def _execute_check_conflict(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        requirement_id_a = _normalize_requirement_id(arguments.get("requirement_id_a"))
        requirement_id_b = _normalize_requirement_id(arguments.get("requirement_id_b"))

        req_a = self._resolve_project_requirement(
            project_id=context["project_id"],
            requirement_id=requirement_id_a,
        )
        req_b = self._resolve_project_requirement(
            project_id=context["project_id"],
            requirement_id=requirement_id_b,
        )

        text_a = self._requirement_text(req_a)
        text_b = self._requirement_text(req_b)

        result = self._conflict_check_fn(text_a, text_b)
        return {
            "requirement_id_a": requirement_id_a,
            "requirement_id_b": requirement_id_b,
            "is_conflict": result.get("is_conflict", False),
            "raw_response": result.get("raw_response", ""),
        }

    @staticmethod
    def _requirement_text(requirement: dict[str, Any]) -> str:
        parts = []
        title = requirement.get("title") or ""
        if title:
            parts.append(f"标题: {title}")
        description = requirement.get("description") or ""
        if description:
            parts.append(f"描述: {description}")
        acceptance = requirement.get("acceptance_criteria") or ""
        if acceptance:
            parts.append(f"验收标准: {acceptance}")
        return "\n".join(parts) if parts else str(requirement.get("req_id", ""))
