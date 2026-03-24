"""Session controller agent tool definitions and execution helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend_business.services.requirements_manage_service import RequirementsManageService


logger = logging.getLogger(__name__)

_LIST_ITEM_EXCERPT_LENGTH = 180


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
        "description_excerpt": _collapse_excerpt(item.get("description")),
    }


class SessionControllerTools:
    """Session controller tool definitions and execution."""

    def __init__(
        self,
        *,
        requirements_service: RequirementsManageService,
        requirement_agent_service: Any,
        conflict_agent_service: Any,
    ) -> None:
        self.requirements_service = requirements_service
        self._requirement_agent_service = requirement_agent_service
        self._conflict_agent_service = conflict_agent_service

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
                    "description": "列出当前项目的需求（分页窗口），用于浏览性查询，返回摘要信息。",
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
                    "name": "search_requirements",
                    "description": "在当前项目内按关键词搜索需求，用于定位特定需求。",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "keyword": {
                                "type": "string",
                                "description": "非空搜索关键词，匹配需求 ID、标题、描述",
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
                    "name": "invoke_requirement_agent",
                    "description": (
                        "将需求管理任务委托给需求管理 Agent 执行。"
                        "适用于：读取需求详情、修改需求内容、需求状态查询等。"
                        "task_description 必须是具体的任务描述，包含用户原始意图和上下文。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_description": {
                                "type": "string",
                                "description": "详细的任务描述，包含用户意图和必要上下文",
                            },
                            "requirement_id": {
                                "type": "string",
                                "description": "如已知目标需求 ID，可选传入",
                            },
                        },
                        "required": ["task_description"],
                        "additionalProperties": False,
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "invoke_conflict_detection",
                    "description": (
                        "将冲突检测任务委托给冲突检测 Agent 执行。"
                        "适用于：检测两条或多条需求之间是否存在语义冲突。"
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "task_description": {
                                "type": "string",
                                "description": "具体的冲突检测任务描述，包含需要检测的需求 ID 或检测条件",
                            },
                        },
                        "required": ["task_description"],
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
        if tool_name == "invoke_requirement_agent":
            return self._execute_invoke_requirement_agent(parsed_arguments, context)
        if tool_name == "invoke_conflict_detection":
            return self._execute_invoke_conflict_detection(parsed_arguments, context)
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

    def _execute_search_requirements(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        keyword = str(arguments.get("keyword") or "").strip()
        if not keyword:
            raise ValueError("keyword 不能为空")
        start_index = _normalize_window_arg(
            arguments.get("start_index"), default=1, field_name="start_index"
        )
        count = _normalize_window_arg(arguments.get("count"), default=10, field_name="count")
        window = self.requirements_service.search_requirements(
            project_id=context["project_id"],
            keyword=keyword,
            start_index=start_index,
            count=count,
        )
        items = [_summarize_list_item(item) for item in window.get("items") or []]
        return {
            "total": window.get("total", 0),
            "start_index": window.get("start_index", start_index),
            "count": window.get("count", count),
            "has_more": window.get("has_more", False),
            "keyword": keyword,
            "items": items,
        }

    def _execute_invoke_requirement_agent(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        task_description = str(arguments.get("task_description") or "").strip()
        if not task_description:
            raise ValueError("task_description 不能为空")
        requirement_id = str(arguments.get("requirement_id") or "").strip() or None

        user_id = context.get("user_id", "")
        project_id = context.get("project_id", "")
        self._mark_dispatched_agent(context, "requirement_agent")
        child_stage = self._start_child_agent_stage(
            context=context,
            agent_key="requirement_agent",
            agent_label="Requirement Agent",
            task_description=task_description,
        )

        try:
            sub_session = self._requirement_agent_service.create_session(
                user_id=user_id,
                project_id=project_id,
                title=f"[子任务] {task_description[:50]}",
            )
            sub_session_id = sub_session["session_id"]
        except Exception as exc:
            logger.warning("创建需求管理子会话失败: %s", exc)
            self._complete_child_agent_stage(
                context=context,
                child_stage=child_stage,
                success=False,
                output_summary={"status": "error", "error": f"创建子会话失败: {exc}"},
            )
            return {"status": "error", "error": f"创建子会话失败: {exc}"}

        reply_text = ""
        result_data: dict[str, Any] = {}
        try:
            for event in self._requirement_agent_service.stream_requirement_agent_reply(
                session_id=sub_session_id,
                user_id=user_id,
                project_id=project_id,
                user_message=task_description,
                requirement_id=requirement_id,
            ):
                event_name = event.get("event", "")
                event_data = event.get("data", {}) or {}
                if event_name == "result":
                    result_data = event_data
                elif event_name == "assistant_message":
                    reply_text = event_data.get("content", "")
                elif event_name == "error":
                    self._complete_child_agent_stage(
                        context=context,
                        child_stage=child_stage,
                        success=False,
                        output_summary={
                            "status": "error",
                            "error": event_data.get("error", "需求管理 Agent 返回错误"),
                            "sub_graph_id": result_data.get("graph_id"),
                        },
                    )
                    return {
                        "status": "error",
                        "error": event_data.get("error", "需求管理 Agent 返回错误"),
                    }
        except Exception as exc:
            logger.warning("调用需求管理 Agent 失败: %s", exc, exc_info=True)
            self._complete_child_agent_stage(
                context=context,
                child_stage=child_stage,
                success=False,
                output_summary={"status": "error", "error": f"需求管理 Agent 执行失败: {exc}"},
            )
            return {"status": "error", "error": f"需求管理 Agent 执行失败: {exc}"}

        response = {
            "status": "success",
            "reply": reply_text,
            "sub_graph_id": result_data.get("graph_id"),
            "mode": result_data.get("mode"),
            "resolved_requirement_id": result_data.get("resolved_requirement_id"),
            "write_result": result_data.get("write_result"),
        }
        self._complete_child_agent_stage(
            context=context,
            child_stage=child_stage,
            success=True,
            output_summary=response,
        )
        return response

    def _execute_invoke_conflict_detection(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        task_description = str(arguments.get("task_description") or "").strip()
        if not task_description:
            raise ValueError("task_description 不能为空")

        user_id = context.get("user_id", "")
        project_id = context.get("project_id", "")
        self._mark_dispatched_agent(context, "conflict_detection")
        child_stage = self._start_child_agent_stage(
            context=context,
            agent_key="conflict_detection",
            agent_label="Conflict Detection Agent",
            task_description=task_description,
        )

        try:
            sub_session = self._conflict_agent_service.create_session(
                user_id=user_id,
                project_id=project_id,
                title=f"[子任务] {task_description[:50]}",
            )
            sub_session_id = sub_session["session_id"]
        except Exception as exc:
            logger.warning("创建冲突检测子会话失败: %s", exc)
            self._complete_child_agent_stage(
                context=context,
                child_stage=child_stage,
                success=False,
                output_summary={"status": "error", "error": f"创建子会话失败: {exc}"},
            )
            return {"status": "error", "error": f"创建子会话失败: {exc}"}

        reply_text = ""
        result_data: dict[str, Any] = {}
        try:
            for event in self._conflict_agent_service.stream_conflict_agent_reply(
                session_id=sub_session_id,
                user_id=user_id,
                project_id=project_id,
                user_message=task_description,
            ):
                event_name = event.get("event", "")
                event_data = event.get("data", {}) or {}
                if event_name == "result":
                    result_data = event_data
                elif event_name == "assistant_message":
                    reply_text = event_data.get("content", "")
                elif event_name == "error":
                    self._complete_child_agent_stage(
                        context=context,
                        child_stage=child_stage,
                        success=False,
                        output_summary={
                            "status": "error",
                            "error": event_data.get("error", "冲突检测 Agent 返回错误"),
                            "sub_graph_id": result_data.get("graph_id"),
                        },
                    )
                    return {
                        "status": "error",
                        "error": event_data.get("error", "冲突检测 Agent 返回错误"),
                    }
        except Exception as exc:
            logger.warning("调用冲突检测 Agent 失败: %s", exc, exc_info=True)
            self._complete_child_agent_stage(
                context=context,
                child_stage=child_stage,
                success=False,
                output_summary={"status": "error", "error": f"冲突检测 Agent 执行失败: {exc}"},
            )
            return {"status": "error", "error": f"冲突检测 Agent 执行失败: {exc}"}

        response = {
            "status": "success",
            "reply": reply_text,
            "sub_graph_id": result_data.get("graph_id"),
        }
        self._complete_child_agent_stage(
            context=context,
            child_stage=child_stage,
            success=True,
            output_summary=response,
        )
        return response

    @staticmethod
    def _mark_dispatched_agent(context: dict[str, Any], agent_key: str) -> None:
        dispatched = context.setdefault("dispatched_agents", [])
        if agent_key not in dispatched:
            dispatched.append(agent_key)

    def _start_child_agent_stage(
        self,
        *,
        context: dict[str, Any],
        agent_key: str,
        agent_label: str,
        task_description: str,
    ) -> dict[str, Any] | None:
        recorder = context.get("_graph_recorder")
        parent_node_key = str(context.get("_active_stage_node_key") or "").strip()
        user_id = str(context.get("user_id") or "")
        if recorder is None or not parent_node_key:
            return None

        tool_results = context.get("tool_results") or []
        sequence = len(tool_results) + 1
        child_node_key = f"{parent_node_key}__delegate_{agent_key}_{sequence}"
        child_label = f"{agent_label} Delegate #{sequence}"
        recorder.start_stage(
            node_key=child_node_key,
            label=child_label,
            node_type="llm",
            role_type="agent",
            container_key=agent_key,
            created_by=user_id,
            input_summary={
                "task_description": task_description,
                "delegated_by": parent_node_key,
                "agent": agent_key,
            },
            edge_type_from_previous="call",
        )
        return {
            "node_key": child_node_key,
            "parent_node_key": parent_node_key,
        }

    def _complete_child_agent_stage(
        self,
        *,
        context: dict[str, Any],
        child_stage: dict[str, Any] | None,
        success: bool,
        output_summary: dict[str, Any],
    ) -> None:
        if not child_stage:
            return
        recorder = context.get("_graph_recorder")
        user_id = str(context.get("user_id") or "")
        if recorder is None:
            return

        error_text = None if success else str(output_summary.get("error") or "delegated agent failed")
        recorder.complete_stage(
            child_stage["node_key"],
            created_by=user_id,
            output_summary=output_summary,
            success=success,
            error=error_text,
        )
        recorder.restore_stage_cursor(
            node_key=child_stage["parent_node_key"],
            updated_by=user_id,
        )
