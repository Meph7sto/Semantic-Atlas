"""Static contracts for graph-first agent integration."""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class AgentDelegation:
    """Declare how SessionController exposes and invokes a child agent."""

    tool_name: str
    route_key: str
    decision_mode: str
    tool_description: str
    tool_parameters: dict[str, Any]
    invoke_label: str
    invoke_phase_label: str
    invoke_task_prompt: str
    runtime_label: str
    runtime_phase_label: str
    runtime_task_prompt: str
    prompt_builder_kind: str
    runtime_node_key: str
    result_contract: str
    call_edge_label: str
    accepts_requirement_id: bool = False
    include_prompt_preferences: bool = False
    forwarded_argument_names: tuple[str, ...] = ()
    routing_keywords: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        for field_name in (
            "tool_name",
            "route_key",
            "decision_mode",
            "invoke_label",
            "runtime_label",
            "prompt_builder_kind",
            "runtime_node_key",
            "result_contract",
            "call_edge_label",
        ):
            if not str(getattr(self, field_name) or "").strip():
                raise ValueError(f"delegation {field_name} is required")
        if self.tool_parameters.get("type") != "object":
            raise ValueError("delegation tool_parameters must be an object schema")
        if not self.decision_mode.startswith("delegate_"):
            raise ValueError("delegation decision_mode must start with 'delegate_'")
        properties = self.tool_parameters.get("properties") or {}
        for argument_name in self.forwarded_argument_names:
            normalized_name = str(argument_name or "").strip()
            if not normalized_name:
                raise ValueError("delegation forwarded_argument_names cannot contain blanks")
            if normalized_name not in properties:
                raise ValueError(
                    "delegation forwarded argument must be declared in tool_parameters"
                )
        for keyword in self.routing_keywords:
            if not str(keyword or "").strip():
                raise ValueError("delegation routing_keywords cannot contain blanks")

    def tool_definition(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.tool_name,
                "description": self.tool_description,
                "parameters": dict(self.tool_parameters),
            },
        }


@dataclass(frozen=True)
class AgentDefinition:
    """Describe an agent's static capabilities and runtime policy.

    GraphExecutor owns the flow. ToolLoopRunner owns the loop. AgentDefinition
    keeps agent-specific wiring declarative so new agents do not need copied
    service or runner scaffolding as their default integration path.
    """

    agent_type: str
    container_key: str
    label: str
    description: str = ""
    role_type: str = "agent"
    max_tool_call_rounds: int = 6
    prompt_builder_factory: Callable[[], Any] | None = None
    tool_executor_factory: Callable[..., Any] | None = None
    application_service_factory: Callable[[], Any] | None = None
    context_builder: Callable[..., Any] | None = None
    result_postprocessor: Callable[..., Any] | None = None
    delegated_prompt_builder_factory: Callable[[], Any] | None = None
    delegation: AgentDelegation | None = None
    runtime_profile: str = "default"
    capability_policy: dict[str, Any] | None = None
    quota_policy: dict[str, Any] | None = None
    memory_policy: dict[str, Any] | None = None
    implementation_type: str = "local"
    selectable: bool = True
    selectable_description: str = ""
    binding_scope: str = ""

    def __post_init__(self) -> None:
        if not self.agent_type.strip():
            raise ValueError("agent_type is required")
        if not self.container_key.strip():
            raise ValueError("container_key is required")
        if not self.label.strip():
            raise ValueError("label is required")
        if self.max_tool_call_rounds < 1:
            raise ValueError("max_tool_call_rounds must be positive")


class AgentService(Protocol):
    """Minimum application-service surface for standalone agent paths."""

    AGENT_TYPE: str

    def create_or_get_session(
        self,
        user_id: str,
        project_id: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]: ...

    def stream_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
    ) -> Generator[dict[str, Any], None, None]: ...
