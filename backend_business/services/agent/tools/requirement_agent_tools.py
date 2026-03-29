"""Requirement agent tool definitions and execution helpers."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from backend_business.services.requirements_manage_service import (
    RequirementsManageService,
    normalize_priority,
)
from backend_business.services.requirement_change_approval_service import (
    RequirementChangeApprovalService,
)


_LIST_ITEM_EXCERPT_LENGTH = 180
_ALLOWED_UPDATE_FIELDS = {
    "title",
    "description",
    "acceptance_criteria",
    "priority",
    "notes",
}
logger = logging.getLogger(__name__)


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


def _normalize_updates(updates: Any) -> dict[str, Any]:
    if not isinstance(updates, dict):
        raise ValueError("updates 必须是对象")

    normalized: dict[str, Any] = {}
    unknown_fields = sorted(set(updates.keys()) - _ALLOWED_UPDATE_FIELDS)
    if unknown_fields:
        raise ValueError(f"updates 包含不支持的字段: {', '.join(unknown_fields)}")

    for key, value in updates.items():
        if value is None:
            continue
        if key == "priority":
            normalized_priority = normalize_priority(value, allow_none=True)
            if normalized_priority is None:
                continue
            normalized[key] = normalized_priority
            continue
        normalized[key] = value

    if not normalized:
        raise ValueError("updates 不能为空")
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


def _summarize_actor_state(state: dict[str, Any] | None) -> dict[str, Any]:
    state = state or {}
    content = state.get("content") or {}
    return {
        "requirement_id": state.get("requirement_id"),
        "version": state.get("version"),
        "status": state.get("status"),
        "priority": state.get("priority"),
        "title": content.get("title"),
        "description": content.get("description"),
        "acceptance_criteria": content.get("acceptance_criteria"),
    }


def _summarize_requirement_record(item: dict[str, Any] | None) -> dict[str, Any]:
    item = item or {}
    return {
        "requirement_id": item.get("req_id"),
        "version": item.get("version"),
        "status": item.get("status"),
        "priority": item.get("priority"),
        "title": item.get("title"),
        "description": item.get("description"),
        "acceptance_criteria": item.get("acceptance_criteria"),
    }


def _format_approval_creation_error(exc: Exception) -> str:
    message = str(exc).strip() or "未知错误"
    return f"无法发起需求修改审批：{message}"


class RequirementAgentTools:
    """Requirement tool definitions and execution against existing backend services."""

    def __init__(
        self,
        *,
        requirements_service: RequirementsManageService,
        actor_query_fn: Callable[[Any, str], dict[str, Any]],
        actor_write_fn: Callable[[Any, str, dict[str, Any]], dict[str, Any]],
        approval_service: RequirementChangeApprovalService,
    ) -> None:
        self.requirements_service = requirements_service
        self._actor_query_fn = actor_query_fn
        self._actor_write_fn = actor_write_fn
        self._approval_service = approval_service

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
                    "name": "search_requirements",
                    "description": "在当前项目内按关键词搜索需求。关键词会匹配 req_id、title、description。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "非空关键词，不能为空白",
                            },
                            **window_properties,
                        },
                        "required": ["keyword"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "list_requirements",
                    "description": "按当前项目的需求排序列出一个分页窗口。",
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
                    "name": "get_requirement_state",
                    "description": "读取单条需求的当前真实状态。",
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
                    "name": "update_requirement_content",
                    "description": "更新单条需求内容，仅可修改 title、description、acceptance_criteria、priority、notes。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "requirement_id": {
                                "type": "string",
                                "description": "目标需求 ID",
                            },
                            "updates": {
                                "type": "object",
                                "properties": {
                                    "title": {"type": "string"},
                                    "description": {"type": "string"},
                                    "acceptance_criteria": {
                                        "oneOf": [
                                            {"type": "string"},
                                            {
                                                "type": "array",
                                                "items": {"type": "string"},
                                            },
                                        ]
                                    },
                                    "priority": {
                                        "type": "string",
                                        "enum": ["low", "medium", "high"],
                                    },
                                    "notes": {"type": "string"},
                                },
                                "additionalProperties": False,
                                "description": "仅允许现有可修改字段",
                            },
                        },
                        "required": ["requirement_id", "updates"],
                        "additionalProperties": False,
                    },
                },
            },
        ]

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any] | str | None,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        parsed_arguments = self._parse_arguments(arguments)
        if tool_name == "list_requirements":
            return self._execute_list_requirements(parsed_arguments, context)
        if tool_name == "search_requirements":
            return self._execute_search_requirements(parsed_arguments, context)
        if tool_name == "get_requirement_state":
            return self._execute_get_requirement_state(parsed_arguments, context)
        if tool_name == "update_requirement_content":
            return self._execute_update_requirement_content(parsed_arguments, context)
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
            raise ValueError("目标需求不存在或已删除")
        if requirement.get("project_id") != project_id:
            raise ValueError("目标需求不属于当前项目")
        return requirement

    @staticmethod
    def _record_resolution_from_window(
        *,
        context: dict[str, Any],
        items: list[dict[str, Any]],
    ) -> None:
        if len(items) != 1:
            return
        requirement_id = items[0].get("requirement_id")
        if not requirement_id:
            return
        resolved_ids = context.setdefault("resolved_requirement_ids", set())
        resolved_ids.add(requirement_id)
        context["resolved_requirement_id"] = requirement_id

    @staticmethod
    def _record_resolution_from_state(
        *,
        context: dict[str, Any],
        state_summary: dict[str, Any],
    ) -> None:
        requirement_id = state_summary.get("requirement_id")
        if not requirement_id:
            return
        resolved_ids = context.setdefault("resolved_requirement_ids", set())
        resolved_ids.add(requirement_id)
        context["resolved_requirement_id"] = requirement_id
        context["resolved_requirement_summary"] = state_summary

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
        self._record_resolution_from_window(context=context, items=items)
        return {
            "total": window["total"],
            "start_index": window["start_index"],
            "count": window["count"],
            "has_more": window["has_more"],
            "items": items,
        }

    def _execute_search_requirements(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        keyword = str(arguments.get("keyword") or "").strip()
        if not keyword:
            raise ValueError("keyword 不能为空白")
        start_index = _normalize_window_arg(
            arguments.get("start_index"), default=1, field_name="start_index"
        )
        count = _normalize_window_arg(arguments.get("count"), default=10, field_name="count")
        window = self.requirements_service.search_requirements(
            project_id=context["project_id"],
            keyword=keyword,
            start_index=start_index,
            count=count,
            include_deleted=False,
        )
        items = [_summarize_list_item(item) for item in window.get("items") or []]
        self._record_resolution_from_window(context=context, items=items)
        return {
            "total": window["total"],
            "start_index": window["start_index"],
            "count": window["count"],
            "has_more": window["has_more"],
            "items": items,
        }

    def _execute_get_requirement_state(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        requirement_id = _normalize_requirement_id(arguments.get("requirement_id"))
        self._resolve_project_requirement(
            project_id=context["project_id"],
            requirement_id=requirement_id,
        )
        actor_manager = context.get("actor_manager")
        state_result = self._actor_query_fn(actor_manager, requirement_id)
        if state_result.get("status") != "success":
            raise ValueError("读取需求状态失败")
        summary = _summarize_actor_state(state_result.get("state") or {})
        self._record_resolution_from_state(context=context, state_summary=summary)
        return summary

    def _execute_update_requirement_content(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        requirement_id = _normalize_requirement_id(arguments.get("requirement_id"))
        normalized_updates = _normalize_updates(arguments.get("updates"))
        requirement = self._resolve_project_requirement(
            project_id=context["project_id"],
            requirement_id=requirement_id,
        )
        self._ensure_write_target_is_resolved(
            requirement_id=requirement_id,
            context=context,
        )

        actor_manager = context.get("actor_manager")
        _ = actor_manager  # kept for call signature compatibility
        try:
            approval_result = self._approval_service.create_approval_request(
                project_id=context["project_id"],
                requirement_id=requirement_id,
                requested_by=context.get("user_id") or "requirement_agent_chat",
                updates=normalized_updates,
                session_id=context.get("session_id"),
                graph_id=context.get("graph_id"),
                source_agent="requirement_agent",
            )
        except Exception as exc:
            raise ValueError(_format_approval_creation_error(exc)) from exc

        state_result = self._actor_query_fn(context.get("actor_manager"), requirement_id)
        if state_result.get("status") == "success":
            summary = _summarize_actor_state(state_result.get("state") or {})
        else:
            logger.warning(
                "创建审批成功，但回读需求状态失败 requirement_id=%s graph_id=%s",
                requirement_id,
                context.get("graph_id"),
            )
            summary = _summarize_requirement_record(requirement)
        self._record_resolution_from_state(context=context, state_summary=summary)
        result = {
            **summary,
            "write_status": "approval_pending",
            "approval_request_id": approval_result.get("approval_request_id"),
            "push_message_id": approval_result.get("push_message_id"),
            "applied_updates": normalized_updates,
            "summary_text": approval_result.get("summary_text"),
        }
        context["approval_pending"] = True
        context["last_approval_result"] = result
        return result

    @staticmethod
    def _ensure_write_target_is_resolved(
        *,
        requirement_id: str,
        context: dict[str, Any],
    ) -> None:
        selected_requirement_id = context.get("selected_requirement_id")
        resolved_requirement_ids = context.setdefault("resolved_requirement_ids", set())
        if selected_requirement_id:
            if requirement_id == selected_requirement_id or requirement_id in resolved_requirement_ids:
                return
        elif requirement_id in resolved_requirement_ids:
            return

        context["clarification_required"] = True
        raise ValueError(
            "缺少明确 requirement_id：请先通过搜索、列表或显式上下文定位到唯一需求，再执行更新。"
        )
