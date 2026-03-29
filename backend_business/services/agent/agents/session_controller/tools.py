"""Session controller agent tool definitions and execution helpers."""

from __future__ import annotations

import json
import logging
from typing import Any

from backend_business.services.requirements_manage_service import RequirementsManageService


logger = logging.getLogger(__name__)

_LIST_ITEM_EXCERPT_LENGTH = 180
_DEFAULT_DELEGATED_MAX_TOOL_CALL_ROUNDS = 15


def _mark_tool_loop_should_stop(context: dict[str, Any], reply: str | None) -> None:
    context["_stop_after_tool_round"] = True
    context["_forced_tool_loop_reply"] = str(reply or "").strip()


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


def _resolve_delegated_max_tool_call_rounds(context: dict[str, Any]) -> int:
    raw_value = context.get(
        "delegated_max_tool_call_rounds",
        _DEFAULT_DELEGATED_MAX_TOOL_CALL_ROUNDS,
    )
    try:
        normalized = int(raw_value)
    except (TypeError, ValueError):
        return _DEFAULT_DELEGATED_MAX_TOOL_CALL_ROUNDS
    return max(1, min(50, normalized))


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

    def execute_streaming(
        self,
        tool_name: str,
        arguments: dict[str, Any] | str | None,
        context: dict[str, Any],
    ):
        parsed_arguments = self._parse_arguments(arguments)
        if tool_name == "invoke_requirement_agent":
            return self._stream_invoke_requirement_agent(parsed_arguments, context)
        if tool_name == "invoke_conflict_detection":
            return self._stream_invoke_conflict_detection(parsed_arguments, context)
        return self.execute(tool_name, parsed_arguments, context)

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
        if not requirement_id:
            requirement_id = (
                str(context.get("resolved_requirement_id") or "").strip() or None
            )

        user_id = context.get("user_id", "")
        project_id = context.get("project_id", "")
        session_id = str(context.get("session_id") or "")
        prompt_payload_format = (
            str(context.get("delegated_prompt_payload_format") or "").strip() or "markdown"
        )
        context_mode = str(context.get("delegated_context_mode") or "").strip() or "full"
        delegated_max_tool_call_rounds = _resolve_delegated_max_tool_call_rounds(context)
        self._mark_dispatched_agent(context, "requirement_agent")

        recorder = context.get("_graph_recorder")
        parent_node_key = str(context.get("_active_stage_node_key") or "").strip()

        if recorder is None or not parent_node_key:
            return {"status": "error", "error": "No graph recorder available for inline execution"}

        tool_results = context.get("tool_results") or []
        sequence = len(tool_results) + 1
        node_key_prefix = f"req_agent_{sequence}"

        # 1. Start node with call edge (cross-container boundary)
        start_node_key = recorder.stage_node_key(f"{node_key_prefix}_start")
        recorder.start_stage(
            node_key=start_node_key,
            label=recorder.stage_label(f"Requirement Agent #{sequence}"),
            node_type="start",
            role_type="agent",
            container_key="requirement_agent",
            created_by=user_id,
            input_summary={
                "task_description": task_description,
                "requirement_id": requirement_id,
                "delegated_by": parent_node_key,
            },
            edge_type_from_previous="call",
        )
        recorder.complete_stage(
            start_node_key,
            created_by=user_id,
            output_summary={"accepted": True},
        )

        # 2. Run tool loop inline — nodes write into parent graph's requirement_agent container
        try:
            loop_result = self._requirement_agent_service.run_inline_tool_loop(
                recorder=recorder,
                user_id=user_id,
                user_message=task_description,
                project_id=project_id,
                session_id=session_id,
                prompt_payload_format=prompt_payload_format,
                context_mode=context_mode,
                max_tool_call_rounds=delegated_max_tool_call_rounds,
                requirement_id=requirement_id,
                container_key="requirement_agent",
                node_key_prefix=node_key_prefix,
            )
        except Exception as exc:
            logger.warning("需求管理 Agent 内联执行失败: %s", exc, exc_info=True)
            end_node_key = recorder.stage_node_key(f"{node_key_prefix}_end")
            recorder.start_stage(
                node_key=end_node_key,
                label=recorder.stage_label(f"Requirement Agent #{sequence} End"),
                node_type="end",
                role_type="agent",
                container_key="requirement_agent",
                created_by=user_id,
                input_summary={"error": str(exc)},
                edge_type_from_previous="seq",
            )
            recorder.complete_stage(
                end_node_key, created_by=user_id,
                output_summary={"error": str(exc)}, success=False, error=str(exc),
            )
            recorder.create_return_edge(
                child_node_key=end_node_key, parent_node_key=parent_node_key, created_by=user_id,
            )
            recorder.restore_stage_cursor(node_key=parent_node_key, updated_by=user_id)
            error_result = {"status": "error", "error": f"需求管理 Agent 执行失败: {exc}"}
            _mark_tool_loop_should_stop(context, error_result["error"])
            return error_result

        # 3. End node + return edge (cross-container boundary)
        end_node_key = recorder.stage_node_key(f"{node_key_prefix}_end")
        recorder.start_stage(
            node_key=end_node_key,
            label=recorder.stage_label(f"Requirement Agent #{sequence} End"),
            node_type="end",
            role_type="agent",
            container_key="requirement_agent",
            created_by=user_id,
            input_summary={"tool_loop_reply": loop_result.get("tool_loop_reply")},
            edge_type_from_previous="seq",
        )
        recorder.complete_stage(
            end_node_key, created_by=user_id,
            output_summary=loop_result,
        )
        recorder.create_return_edge(
            child_node_key=end_node_key, parent_node_key=parent_node_key, created_by=user_id,
        )
        recorder.restore_stage_cursor(node_key=parent_node_key, updated_by=user_id)
        resolved_requirement_id = loop_result.get("resolved_requirement_id")
        if resolved_requirement_id:
            context["resolved_requirement_id"] = resolved_requirement_id
            context.setdefault("resolved_requirement_ids", set()).add(resolved_requirement_id)
        write_result = loop_result.get("write_result")
        if write_result is not None:
            context["last_write_result"] = write_result
        if loop_result.get("approval_pending"):
            context["approval_pending"] = True
            context["last_approval_result"] = loop_result.get("approval_result")
        if loop_result.get("clarification_required") or loop_result.get("mode") == "clarification":
            context["clarification_required"] = True
            context["last_clarification_reply"] = loop_result.get("tool_loop_reply", "")

        result = {
            "status": "success",
            "reply": loop_result.get("tool_loop_reply", ""),
            "resolved_requirement_id": resolved_requirement_id,
            "write_result": write_result,
            "mode": loop_result.get("mode"),
            "clarification_required": bool(
                loop_result.get("clarification_required")
                or loop_result.get("mode") == "clarification"
            ),
            "approval_pending": bool(loop_result.get("approval_pending")),
            "approval_result": loop_result.get("approval_result"),
        }
        _mark_tool_loop_should_stop(context, result.get("reply"))
        return result

    def _stream_invoke_requirement_agent(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ):
        task_description = str(arguments.get("task_description") or "").strip()
        if not task_description:
            raise ValueError("task_description 不能为空")
        requirement_id = str(arguments.get("requirement_id") or "").strip() or None
        if not requirement_id:
            requirement_id = (
                str(context.get("resolved_requirement_id") or "").strip() or None
            )

        user_id = context.get("user_id", "")
        project_id = context.get("project_id", "")
        session_id = str(context.get("session_id") or "")
        prompt_payload_format = (
            str(context.get("delegated_prompt_payload_format") or "").strip() or "markdown"
        )
        context_mode = str(context.get("delegated_context_mode") or "").strip() or "full"
        delegated_max_tool_call_rounds = _resolve_delegated_max_tool_call_rounds(context)
        self._mark_dispatched_agent(context, "requirement_agent")

        recorder = context.get("_graph_recorder")
        parent_node_key = str(context.get("_active_stage_node_key") or "").strip()

        if recorder is None or not parent_node_key:
            return {"status": "error", "error": "No graph recorder available for inline execution"}

        tool_results = context.get("tool_results") or []
        sequence = len(tool_results) + 1
        node_key_prefix = f"req_agent_{sequence}"

        start_node_key = recorder.stage_node_key(f"{node_key_prefix}_start")
        recorder.start_stage(
            node_key=start_node_key,
            label=recorder.stage_label(f"Requirement Agent #{sequence}"),
            node_type="start",
            role_type="agent",
            container_key="requirement_agent",
            created_by=user_id,
            input_summary={
                "task_description": task_description,
                "requirement_id": requirement_id,
                "delegated_by": parent_node_key,
            },
            edge_type_from_previous="call",
        )
        recorder.complete_stage(
            start_node_key,
            created_by=user_id,
            output_summary={"accepted": True},
        )
        yield {
            "event": "stage",
            "data": recorder.build_stage_event_data(
                start_node_key,
                status="succeeded",
            ),
        }

        try:
            loop_result = yield from self._requirement_agent_service.stream_inline_tool_loop(
                recorder=recorder,
                user_id=user_id,
                user_message=task_description,
                project_id=project_id,
                session_id=session_id,
                prompt_payload_format=prompt_payload_format,
                context_mode=context_mode,
                max_tool_call_rounds=delegated_max_tool_call_rounds,
                requirement_id=requirement_id,
                container_key="requirement_agent",
                node_key_prefix=node_key_prefix,
            )
        except Exception as exc:
            logger.warning("需求管理 Agent 内联执行失败: %s", exc, exc_info=True)
            end_node_key = recorder.stage_node_key(f"{node_key_prefix}_end")
            recorder.start_stage(
                node_key=end_node_key,
                label=recorder.stage_label(f"Requirement Agent #{sequence} End"),
                node_type="end",
                role_type="agent",
                container_key="requirement_agent",
                created_by=user_id,
                input_summary={"error": str(exc)},
                edge_type_from_previous="seq",
            )
            recorder.complete_stage(
                end_node_key,
                created_by=user_id,
                output_summary={"error": str(exc)},
                success=False,
                error=str(exc),
            )
            recorder.create_return_edge(
                child_node_key=end_node_key,
                parent_node_key=parent_node_key,
                created_by=user_id,
            )
            recorder.restore_stage_cursor(node_key=parent_node_key, updated_by=user_id)
            yield {
                "event": "stage",
                "data": recorder.build_stage_event_data(
                    end_node_key,
                    status="failed",
                ),
            }
            error_result = {"status": "error", "error": f"需求管理 Agent 执行失败: {exc}"}
            _mark_tool_loop_should_stop(context, error_result["error"])
            return error_result

        end_node_key = recorder.stage_node_key(f"{node_key_prefix}_end")
        recorder.start_stage(
            node_key=end_node_key,
            label=recorder.stage_label(f"Requirement Agent #{sequence} End"),
            node_type="end",
            role_type="agent",
            container_key="requirement_agent",
            created_by=user_id,
            input_summary={"tool_loop_reply": loop_result.get("tool_loop_reply")},
            edge_type_from_previous="seq",
        )
        recorder.complete_stage(
            end_node_key,
            created_by=user_id,
            output_summary=loop_result,
        )
        recorder.create_return_edge(
            child_node_key=end_node_key,
            parent_node_key=parent_node_key,
            created_by=user_id,
        )
        recorder.restore_stage_cursor(node_key=parent_node_key, updated_by=user_id)
        resolved_requirement_id = loop_result.get("resolved_requirement_id")
        if resolved_requirement_id:
            context["resolved_requirement_id"] = resolved_requirement_id
            context.setdefault("resolved_requirement_ids", set()).add(resolved_requirement_id)
        write_result = loop_result.get("write_result")
        if write_result is not None:
            context["last_write_result"] = write_result
        if loop_result.get("approval_pending"):
            context["approval_pending"] = True
            context["last_approval_result"] = loop_result.get("approval_result")
        if loop_result.get("clarification_required") or loop_result.get("mode") == "clarification":
            context["clarification_required"] = True
            context["last_clarification_reply"] = loop_result.get("tool_loop_reply", "")
        yield {
            "event": "stage",
            "data": recorder.build_stage_event_data(
                end_node_key,
                status="succeeded",
            ),
        }

        result = {
            "status": "success",
            "reply": loop_result.get("tool_loop_reply", ""),
            "resolved_requirement_id": resolved_requirement_id,
            "write_result": write_result,
            "mode": loop_result.get("mode"),
            "clarification_required": bool(
                loop_result.get("clarification_required")
                or loop_result.get("mode") == "clarification"
            ),
            "approval_pending": bool(loop_result.get("approval_pending")),
            "approval_result": loop_result.get("approval_result"),
        }
        _mark_tool_loop_should_stop(context, result.get("reply"))
        return result

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
        delegated_max_tool_call_rounds = _resolve_delegated_max_tool_call_rounds(context)
        self._mark_dispatched_agent(context, "conflict_detection")

        recorder = context.get("_graph_recorder")
        parent_node_key = str(context.get("_active_stage_node_key") or "").strip()

        if recorder is None or not parent_node_key:
            return {"status": "error", "error": "No graph recorder available for inline execution"}

        tool_results = context.get("tool_results") or []
        sequence = len(tool_results) + 1
        node_key_prefix = f"conflict_agent_{sequence}"

        # 1. Start node with call edge (cross-container boundary)
        start_node_key = recorder.stage_node_key(f"{node_key_prefix}_start")
        recorder.start_stage(
            node_key=start_node_key,
            label=recorder.stage_label(f"Conflict Detection #{sequence}"),
            node_type="start",
            role_type="agent",
            container_key="conflict_detection",
            created_by=user_id,
            input_summary={
                "task_description": task_description,
                "delegated_by": parent_node_key,
            },
            edge_type_from_previous="call",
        )
        recorder.complete_stage(
            start_node_key,
            created_by=user_id,
            output_summary={"accepted": True},
        )

        # 2. Run tool loop inline
        try:
            loop_result = self._conflict_agent_service.run_inline_tool_loop(
                recorder=recorder,
                user_id=user_id,
                user_message=task_description,
                project_id=project_id,
                max_tool_call_rounds=delegated_max_tool_call_rounds,
                container_key="conflict_detection",
                node_key_prefix=node_key_prefix,
            )
        except Exception as exc:
            logger.warning("冲突检测 Agent 内联执行失败: %s", exc, exc_info=True)
            end_node_key = recorder.stage_node_key(f"{node_key_prefix}_end")
            recorder.start_stage(
                node_key=end_node_key,
                label=recorder.stage_label(f"Conflict Detection #{sequence} End"),
                node_type="end",
                role_type="agent",
                container_key="conflict_detection",
                created_by=user_id,
                input_summary={"error": str(exc)},
                edge_type_from_previous="seq",
            )
            recorder.complete_stage(
                end_node_key, created_by=user_id,
                output_summary={"error": str(exc)}, success=False, error=str(exc),
            )
            recorder.create_return_edge(
                child_node_key=end_node_key, parent_node_key=parent_node_key, created_by=user_id,
            )
            recorder.restore_stage_cursor(node_key=parent_node_key, updated_by=user_id)
            error_result = {"status": "error", "error": f"冲突检测 Agent 执行失败: {exc}"}
            _mark_tool_loop_should_stop(context, error_result["error"])
            return error_result

        # 3. End node + return edge (cross-container boundary)
        end_node_key = recorder.stage_node_key(f"{node_key_prefix}_end")
        recorder.start_stage(
            node_key=end_node_key,
            label=recorder.stage_label(f"Conflict Detection #{sequence} End"),
            node_type="end",
            role_type="agent",
            container_key="conflict_detection",
            created_by=user_id,
            input_summary={"tool_loop_reply": loop_result.get("tool_loop_reply")},
            edge_type_from_previous="seq",
        )
        recorder.complete_stage(
            end_node_key, created_by=user_id,
            output_summary=loop_result,
        )
        recorder.create_return_edge(
            child_node_key=end_node_key, parent_node_key=parent_node_key, created_by=user_id,
        )
        recorder.restore_stage_cursor(node_key=parent_node_key, updated_by=user_id)

        result = {
            "status": "success",
            "reply": loop_result.get("tool_loop_reply", ""),
        }
        _mark_tool_loop_should_stop(context, result.get("reply"))
        return result

    def _stream_invoke_conflict_detection(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ):
        task_description = str(arguments.get("task_description") or "").strip()
        if not task_description:
            raise ValueError("task_description 不能为空")

        user_id = context.get("user_id", "")
        project_id = context.get("project_id", "")
        delegated_max_tool_call_rounds = _resolve_delegated_max_tool_call_rounds(context)
        self._mark_dispatched_agent(context, "conflict_detection")

        recorder = context.get("_graph_recorder")
        parent_node_key = str(context.get("_active_stage_node_key") or "").strip()

        if recorder is None or not parent_node_key:
            return {"status": "error", "error": "No graph recorder available for inline execution"}

        tool_results = context.get("tool_results") or []
        sequence = len(tool_results) + 1
        node_key_prefix = f"conflict_agent_{sequence}"

        start_node_key = recorder.stage_node_key(f"{node_key_prefix}_start")
        recorder.start_stage(
            node_key=start_node_key,
            label=recorder.stage_label(f"Conflict Detection #{sequence}"),
            node_type="start",
            role_type="agent",
            container_key="conflict_detection",
            created_by=user_id,
            input_summary={
                "task_description": task_description,
                "delegated_by": parent_node_key,
            },
            edge_type_from_previous="call",
        )
        recorder.complete_stage(
            start_node_key,
            created_by=user_id,
            output_summary={"accepted": True},
        )
        yield {
            "event": "stage",
            "data": recorder.build_stage_event_data(
                start_node_key,
                status="succeeded",
            ),
        }

        try:
            loop_result = yield from self._conflict_agent_service.stream_inline_tool_loop(
                recorder=recorder,
                user_id=user_id,
                user_message=task_description,
                project_id=project_id,
                max_tool_call_rounds=delegated_max_tool_call_rounds,
                container_key="conflict_detection",
                node_key_prefix=node_key_prefix,
            )
        except Exception as exc:
            logger.warning("冲突检测 Agent 内联执行失败: %s", exc, exc_info=True)
            end_node_key = recorder.stage_node_key(f"{node_key_prefix}_end")
            recorder.start_stage(
                node_key=end_node_key,
                label=recorder.stage_label(f"Conflict Detection #{sequence} End"),
                node_type="end",
                role_type="agent",
                container_key="conflict_detection",
                created_by=user_id,
                input_summary={"error": str(exc)},
                edge_type_from_previous="seq",
            )
            recorder.complete_stage(
                end_node_key,
                created_by=user_id,
                output_summary={"error": str(exc)},
                success=False,
                error=str(exc),
            )
            recorder.create_return_edge(
                child_node_key=end_node_key,
                parent_node_key=parent_node_key,
                created_by=user_id,
            )
            recorder.restore_stage_cursor(node_key=parent_node_key, updated_by=user_id)
            yield {
                "event": "stage",
                "data": recorder.build_stage_event_data(
                    end_node_key,
                    status="failed",
                ),
            }
            error_result = {"status": "error", "error": f"冲突检测 Agent 执行失败: {exc}"}
            _mark_tool_loop_should_stop(context, error_result["error"])
            return error_result

        end_node_key = recorder.stage_node_key(f"{node_key_prefix}_end")
        recorder.start_stage(
            node_key=end_node_key,
            label=recorder.stage_label(f"Conflict Detection #{sequence} End"),
            node_type="end",
            role_type="agent",
            container_key="conflict_detection",
            created_by=user_id,
            input_summary={"tool_loop_reply": loop_result.get("tool_loop_reply")},
            edge_type_from_previous="seq",
        )
        recorder.complete_stage(
            end_node_key,
            created_by=user_id,
            output_summary=loop_result,
        )
        recorder.create_return_edge(
            child_node_key=end_node_key,
            parent_node_key=parent_node_key,
            created_by=user_id,
        )
        recorder.restore_stage_cursor(node_key=parent_node_key, updated_by=user_id)
        yield {
            "event": "stage",
            "data": recorder.build_stage_event_data(
                end_node_key,
                status="succeeded",
            ),
        }

        result = {
            "status": "success",
            "reply": loop_result.get("tool_loop_reply", ""),
        }
        _mark_tool_loop_should_stop(context, result.get("reply"))
        return result

    @staticmethod
    def _mark_dispatched_agent(context: dict[str, Any], agent_key: str) -> None:
        dispatched = context.setdefault("dispatched_agents", [])
        if agent_key not in dispatched:
            dispatched.append(agent_key)
