"""Requirement-agent adapter for generic actor runtime integration."""

from __future__ import annotations

from backend_business.services.agent.actor.actor_runtime import AgentActorRuntime


class RequirementAgentActorRuntime(AgentActorRuntime):
    """Backward-compatible actor runtime preserving requirement-agent defaults."""

    def __init__(self) -> None:
        super().__init__(
            query_source="requirement_agent_chat",
            loop_thread_name="requirement-agent-actor-loop",
        )

