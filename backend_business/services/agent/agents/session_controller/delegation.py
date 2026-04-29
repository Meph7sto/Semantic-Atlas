"""Native delegation planning for SessionController tools."""

from __future__ import annotations

from typing import Any


_DEFAULT_DELEGATED_MAX_TOOL_CALL_ROUNDS = 15


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


class SessionControllerDelegationDispatcher:
    """Create native invoke payloads for delegated child agents."""

    def __init__(
        self,
        *,
        requirement_agent_service: Any,
        conflict_agent_service: Any,
        requirement_classification_agent_service: Any | None = None,
    ) -> None:
        # Constructor signature stays compatible with SessionControllerTools.
        _ = (
            requirement_agent_service,
            conflict_agent_service,
            requirement_classification_agent_service,
        )

    def execute_requirement_agent(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._plan_requirement_invoke(arguments, context)

    def stream_requirement_agent(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._plan_requirement_invoke(arguments, context)

    def execute_conflict_detection(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._plan_conflict_invoke(arguments, context)

    def stream_conflict_detection(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._plan_conflict_invoke(arguments, context)

    def execute_requirement_classification_agent(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._plan_classification_invoke(arguments, context)

    def stream_requirement_classification_agent(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._plan_classification_invoke(arguments, context)

    @staticmethod
    def _build_invoke_result(
        *,
        delegated_agent: str,
        route_key: str,
        task_description: str,
        requirement_id: str | None = None,
        max_tool_call_rounds: int | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        result = {
            "status": "accepted",
            "native_invoke": True,
            "delegated_agent": delegated_agent,
            "invoke_route_key": route_key,
            "task_description": task_description,
        }
        if requirement_id:
            result["requirement_id"] = requirement_id
        if max_tool_call_rounds is not None:
            result["max_tool_call_rounds"] = max_tool_call_rounds
        if prompt_payload_format:
            result["prompt_payload_format"] = prompt_payload_format
        if context_mode:
            result["context_mode"] = context_mode
        return result

    def _plan_requirement_invoke(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        task_description = str(arguments.get("task_description") or "").strip()
        if not task_description:
            raise ValueError("task_description 不能为空")
        requirement_id = str(arguments.get("requirement_id") or "").strip() or None
        if not requirement_id:
            requirement_id = str(context.get("resolved_requirement_id") or "").strip() or None
        prompt_payload_format = (
            str(context.get("delegated_prompt_payload_format") or "").strip() or "markdown"
        )
        context_mode = str(context.get("delegated_context_mode") or "").strip() or "full"
        max_tool_call_rounds = _resolve_delegated_max_tool_call_rounds(context)
        self._mark_dispatched_agent(context, "requirement_agent")
        if requirement_id:
            context["resolved_requirement_id"] = requirement_id
        return self._build_invoke_result(
            delegated_agent="requirement_agent",
            route_key="invoke_requirement",
            task_description=task_description,
            requirement_id=requirement_id,
            max_tool_call_rounds=max_tool_call_rounds,
            prompt_payload_format=prompt_payload_format,
            context_mode=context_mode,
        )

    def _plan_conflict_invoke(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        task_description = str(arguments.get("task_description") or "").strip()
        if not task_description:
            raise ValueError("task_description 不能为空")
        max_tool_call_rounds = _resolve_delegated_max_tool_call_rounds(context)
        self._mark_dispatched_agent(context, "conflict_detection")
        return self._build_invoke_result(
            delegated_agent="conflict_detection",
            route_key="invoke_conflict",
            task_description=task_description,
            max_tool_call_rounds=max_tool_call_rounds,
        )

    def _plan_classification_invoke(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        task_description = str(arguments.get("task_description") or "").strip()
        if not task_description:
            raise ValueError("task_description 不能为空")
        requirement_id = str(arguments.get("requirement_id") or "").strip() or None
        if not requirement_id:
            requirement_id = str(context.get("resolved_requirement_id") or "").strip() or None
        max_tool_call_rounds = _resolve_delegated_max_tool_call_rounds(context)
        self._mark_dispatched_agent(context, "requirement_classification_agent")
        if requirement_id:
            context["resolved_requirement_id"] = requirement_id
        return self._build_invoke_result(
            delegated_agent="requirement_classification_agent",
            route_key="invoke_classification",
            task_description=task_description,
            requirement_id=requirement_id,
            max_tool_call_rounds=max_tool_call_rounds,
        )

    @staticmethod
    def _mark_dispatched_agent(context: dict[str, Any], agent_key: str) -> None:
        dispatched = context.setdefault("dispatched_agents", [])
        if agent_key not in dispatched:
            dispatched.append(agent_key)
