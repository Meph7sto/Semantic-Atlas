"""Tool capability policy enforcement for agent runtimes."""

from __future__ import annotations

import inspect
from typing import Any


class ToolCapabilityError(PermissionError):
    """Raised when a runtime attempts to call a tool outside its capability policy."""

    def __init__(self, tool_name: str, policy_id: str | None = None) -> None:
        self.tool_name = tool_name
        self.policy_id = policy_id
        suffix = f" under policy '{policy_id}'" if policy_id else ""
        super().__init__(f"工具 '{tool_name}' 未被授权{suffix}")


def _extract_tool_name(entry: dict[str, Any]) -> str:
    function_payload = entry.get("function") if isinstance(entry, dict) else {}
    return str((function_payload or {}).get("name") or "").strip()


class ToolCapabilityExecutor:
    """Wrap a tool executor and enforce an allowlist on the worker side."""

    def __init__(
        self,
        *,
        tool_executor: Any,
        allowed_tool_names: set[str] | None = None,
        policy_id: str | None = None,
    ) -> None:
        self._tool_executor = tool_executor
        self._explicit_allowed_tool_names = set(allowed_tool_names or [])
        self._policy_id = policy_id
        self._cached_discovered_tool_names: set[str] | None = None

    def get_tools_list(
        self,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        raw_tools = self._delegate_get_tools_list(context=context)
        allowed_names = self._resolve_allowed_tool_names(
            context=context,
            discovered_tools=raw_tools,
        )
        return [
            tool
            for tool in raw_tools
            if _extract_tool_name(tool) in allowed_names
        ]

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        self._ensure_tool_allowed(tool_name=tool_name, context=context)
        return self._tool_executor.execute(tool_name, arguments, context)

    def execute_streaming(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ):
        self._ensure_tool_allowed(tool_name=tool_name, context=context)
        execute_streaming = getattr(self._tool_executor, "execute_streaming", None)
        if callable(execute_streaming):
            return execute_streaming(tool_name, arguments, context)
        return self._tool_executor.execute(tool_name, arguments, context)

    def _ensure_tool_allowed(
        self,
        *,
        tool_name: str,
        context: dict[str, Any] | None,
    ) -> None:
        allowed_names = self._resolve_allowed_tool_names(context=context)
        if tool_name not in allowed_names:
            raise ToolCapabilityError(tool_name=tool_name, policy_id=self._policy_id)

    def _resolve_allowed_tool_names(
        self,
        *,
        context: dict[str, Any] | None,
        discovered_tools: list[dict[str, Any]] | None = None,
    ) -> set[str]:
        if self._explicit_allowed_tool_names:
            return set(self._explicit_allowed_tool_names)

        if self._cached_discovered_tool_names is None:
            tools = discovered_tools if discovered_tools is not None else self._delegate_get_tools_list(context=context)
            self._cached_discovered_tool_names = {
                name for name in (_extract_tool_name(tool) for tool in tools)
                if name
            }
        return set(self._cached_discovered_tool_names or set())

    def _delegate_get_tools_list(
        self,
        *,
        context: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        get_tools_list = getattr(self._tool_executor, "get_tools_list")
        try:
            signature = inspect.signature(get_tools_list)
        except (TypeError, ValueError):
            signature = None
        if signature is not None and "context" in signature.parameters:
            return list(get_tools_list(context=context) or [])
        return list(get_tools_list() or [])
