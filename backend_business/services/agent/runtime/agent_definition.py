"""Static contracts for graph-first agent integration."""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any, Protocol


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
    tool_executor_factory: Callable[[], Any] | None = None
    context_builder: Any | None = None
    result_postprocessor: Any | None = None
    runtime_profile: str = "default"
    capability_policy: dict[str, Any] | None = None
    quota_policy: dict[str, Any] | None = None
    memory_policy: dict[str, Any] | None = None
    implementation_type: str = "local"
    selectable: bool = True
    selectable_description: str = ""
    binding_scope: str = ""
    node_key_prefix: str = ""

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
