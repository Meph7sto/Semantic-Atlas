"""Capability-scoped service surface for the requirement traceability agent."""

from __future__ import annotations

from typing import Any

from backend_business.services.agent.runtime.tool_capability import ToolCapabilityExecutor

TRACEABILITY_AGENT_TOOL_NAMES = frozenset(
    {
        "search_requirements",
        "list_requirements",
        "get_requirement_state",
        "trace_requirement_relation",
    }
)


class TraceabilityAgentService:
    """Reuse requirement query tools while keeping this agent read-only."""

    AGENT_TYPE = "traceability_agent"

    def __init__(self, *, shared_tools: Any = None) -> None:
        if shared_tools is None:
            from backend_business.services.agent.agents.requirement_agent.service import (
                requirement_agent_chat_service,
            )

            shared_tools = requirement_agent_chat_service.tools
        self.tools = ToolCapabilityExecutor(
            tool_executor=shared_tools,
            allowed_tool_names=set(TRACEABILITY_AGENT_TOOL_NAMES),
            policy_id="traceability_agent::tools",
        )


traceability_agent_service = TraceabilityAgentService()
