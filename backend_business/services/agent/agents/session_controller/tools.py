"""Session controller agent tool definitions and execution helpers."""

from __future__ import annotations

import json
from typing import Any

from backend_business.services.agent.runtime.agent_registry import (
    BUILTIN_AGENT_REGISTRY,
    AgentRegistry,
)
from backend_business.services.agent.runtime.tool_scheduling import (
    ToolExecutionMetadata,
)
from backend_business.services.requirements_manage_service import RequirementsManageService

from .delegation import SessionControllerDelegationDispatcher

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
        requirement_agent_service: Any = None,
        conflict_agent_service: Any = None,
        requirement_classification_agent_service: Any | None = None,
        agent_registry: AgentRegistry | None = None,
        agent_services: dict[str, Any] | None = None,
    ) -> None:
        self.requirements_service = requirements_service
        self._requirement_agent_service = requirement_agent_service
        self._conflict_agent_service = conflict_agent_service
        self._requirement_classification_agent_service = requirement_classification_agent_service
        self._agent_registry = agent_registry or BUILTIN_AGENT_REGISTRY
        legacy_services = {
            "requirement_agent": requirement_agent_service,
            "conflict_detection": conflict_agent_service,
            "requirement_classification_agent": requirement_classification_agent_service,
        }
        self._runtime_tool_executor_services = {
            key: value for key, value in legacy_services.items() if value is not None
        }
        self._runtime_tool_executor_services.update(agent_services or {})
        self._delegation_dispatcher = SessionControllerDelegationDispatcher(
            agent_registry=self._agent_registry,
            requirement_agent_service=requirement_agent_service,
            conflict_agent_service=conflict_agent_service,
            requirement_classification_agent_service=requirement_classification_agent_service,
        )

    @property
    def agent_registry(self) -> AgentRegistry:
        return self._agent_registry

    def resolve_runtime_tool_executor(self, *, container_key: str) -> Any:
        """Resolve the tool executor bound to a runtime container."""
        if container_key in {"conductor", "session_controller", ""}:
            return self
        return self._agent_registry.resolve_tool_executor(
            container_key=container_key,
            services=self._runtime_tool_executor_services,
        )

    def get_tools_list(
        self,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
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
        controller_tools = [
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
        ]
        return [*controller_tools, *self._agent_registry.delegation_tool_definitions()]

    def get_tool_execution_metadata(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> ToolExecutionMetadata:
        project_id = str(context.get("project_id") or "unknown").strip()
        requirement_id = str(arguments.get("requirement_id") or "").strip()
        resource_key = (
            f"requirement:{project_id}:{requirement_id}"
            if requirement_id
            else f"project:{project_id}"
        )
        if tool_name in {"list_requirements", "search_requirements"}:
            return ToolExecutionMetadata(
                read_only=True,
                idempotent=True,
                resource_key=resource_key,
                concurrency_group="requirements",
            )
        if self._agent_registry.get_by_delegation_tool(tool_name) is not None:
            return ToolExecutionMetadata(
                read_only=False,
                idempotent=False,
                resource_key=resource_key,
                concurrency_group="agent-delegation",
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
        if tool_name == "search_requirements":
            return self._execute_search_requirements(parsed_arguments, context)
        delegated_definition = self._agent_registry.get_by_delegation_tool(tool_name)
        if delegated_definition is not None:
            return self._delegation_dispatcher.execute(
                delegated_definition,
                parsed_arguments,
                context,
            )
        raise ValueError(f"未知工具: {tool_name}")

    def execute_streaming(
        self,
        tool_name: str,
        arguments: dict[str, Any] | str | None,
        context: dict[str, Any],
    ):
        parsed_arguments = self._parse_arguments(arguments)
        delegated_definition = self._agent_registry.get_by_delegation_tool(tool_name)
        if delegated_definition is not None:
            return self._delegation_dispatcher.stream(
                delegated_definition,
                parsed_arguments,
                context,
            )
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
        return self._delegation_dispatcher.execute_requirement_agent(arguments, context)

    def _stream_invoke_requirement_agent(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ):
        return self._delegation_dispatcher.stream_requirement_agent(arguments, context)

    def _execute_invoke_conflict_detection(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._delegation_dispatcher.execute_conflict_detection(arguments, context)

    def _stream_invoke_conflict_detection(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ):
        return self._delegation_dispatcher.stream_conflict_detection(arguments, context)

    def _execute_invoke_requirement_classification_agent(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._delegation_dispatcher.execute_requirement_classification_agent(arguments, context)

    def _stream_invoke_requirement_classification_agent(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ):
        return self._delegation_dispatcher.stream_requirement_classification_agent(arguments, context)
