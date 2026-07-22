"""Definition-driven native delegation planning for SessionController."""

from __future__ import annotations

from typing import Any

from backend_business.services.agent.runtime.agent_definition import AgentDefinition
from backend_business.services.agent.runtime.agent_registry import (
    BUILTIN_AGENT_REGISTRY,
    AgentRegistry,
)

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
    """Create native invoke payloads from catalog delegation metadata."""

    def __init__(
        self,
        *,
        agent_registry: AgentRegistry | None = None,
        requirement_agent_service: Any = None,
        conflict_agent_service: Any = None,
        requirement_classification_agent_service: Any = None,
    ) -> None:
        # Service parameters remain accepted for API compatibility; runtime
        # execution is resolved by the catalog rather than this planner.
        _ = (
            requirement_agent_service,
            conflict_agent_service,
            requirement_classification_agent_service,
        )
        self._agent_registry = agent_registry or BUILTIN_AGENT_REGISTRY

    def execute(
        self,
        definition: AgentDefinition,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._plan_invoke(definition, arguments, context)

    def stream(
        self,
        definition: AgentDefinition,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._plan_invoke(definition, arguments, context)

    def execute_requirement_agent(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._plan_invoke(
            self._agent_registry.require_by_container_key("requirement_agent"),
            arguments,
            context,
        )

    stream_requirement_agent = execute_requirement_agent

    def execute_conflict_detection(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._plan_invoke(
            self._agent_registry.require_by_container_key("conflict_detection"),
            arguments,
            context,
        )

    stream_conflict_detection = execute_conflict_detection

    def execute_requirement_classification_agent(
        self,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._plan_invoke(
            self._agent_registry.require_by_container_key(
                "requirement_classification_agent"
            ),
            arguments,
            context,
        )

    stream_requirement_classification_agent = execute_requirement_classification_agent

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
        forwarded_arguments: dict[str, str] | None = None,
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
        if forwarded_arguments:
            result.update(forwarded_arguments)
        return result

    def _plan_invoke(
        self,
        definition: AgentDefinition,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        delegation = definition.delegation
        if delegation is None:
            raise ValueError(f"agent is not delegatable: {definition.agent_type}")
        task_description = str(arguments.get("task_description") or "").strip()
        if not task_description:
            raise ValueError("task_description 不能为空")

        requirement_id: str | None = None
        if delegation.accepts_requirement_id:
            requirement_id = str(arguments.get("requirement_id") or "").strip() or None
            if not requirement_id:
                requirement_id = (
                    str(context.get("resolved_requirement_id") or "").strip() or None
                )
            if requirement_id:
                context["resolved_requirement_id"] = requirement_id

        prompt_payload_format: str | None = None
        context_mode: str | None = None
        if delegation.include_prompt_preferences:
            prompt_payload_format = (
                str(context.get("delegated_prompt_payload_format") or "").strip()
                or "markdown"
            )
            context_mode = (
                str(context.get("delegated_context_mode") or "").strip() or "full"
            )

        forwarded_arguments = {
            argument_name: value
            for argument_name in delegation.forwarded_argument_names
            if (
                value := str(arguments.get(argument_name) or "").strip()
            )
        }

        self._mark_dispatched_agent(context, definition.container_key)
        return self._build_invoke_result(
            delegated_agent=definition.container_key,
            route_key=delegation.route_key,
            task_description=task_description,
            requirement_id=requirement_id,
            max_tool_call_rounds=_resolve_delegated_max_tool_call_rounds(context),
            prompt_payload_format=prompt_payload_format,
            context_mode=context_mode,
            forwarded_arguments=forwarded_arguments,
        )

    @staticmethod
    def _mark_dispatched_agent(context: dict[str, Any], agent_key: str) -> None:
        dispatched = context.setdefault("dispatched_agents", [])
        if agent_key not in dispatched:
            dispatched.append(agent_key)
