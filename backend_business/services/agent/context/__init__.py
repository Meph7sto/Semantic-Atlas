"""Agent context package - composable context for different scenarios.

Usage
-----
    from backend_business.services.agent.context import AgentContext, BaseContext, ExecutionContext

    # Simple single-agent execution (most common today)
    ctx = AgentContext(
        base=BaseContext(user_id="u1", session_id="s1", project_id="p1"),
        execution=ExecutionContext(agent_id="requirements_agent", user_message_id="m1"),
    )

    # Agent participating in group chat within a workflow
    ctx = AgentContext(
        base=BaseContext(user_id="u1", session_id="s1"),
        execution=ExecutionContext(agent_id="conflict_agent"),
        messaging=MessagingContext(channel_id="ch-01", channel_type="group", peer_agents=["req_agent"]),
        workflow=WorkflowContext(workflow_id="wf-01", workflow_name="Review", step_index=1, total_steps=3),
    )
"""

from dataclasses import dataclass
from typing import Optional

from backend_business.services.agent.context.base import BaseContext
from backend_business.services.agent.context.execution import ExecutionContext
from backend_business.services.agent.context.messaging import MessagingContext
from backend_business.services.agent.context.workflow import WorkflowContext
from backend_business.services.agent.context.memory import MemoryContext


@dataclass
class AgentContext:
    """Top-level context that composes sub-contexts on demand."""

    base: BaseContext
    execution: Optional[ExecutionContext] = None
    messaging: Optional[MessagingContext] = None
    workflow: Optional[WorkflowContext] = None
    memory: Optional[MemoryContext] = None

    # ------------------------------------------------------------------
    # Convenience properties – keep common access patterns short
    # ------------------------------------------------------------------

    @property
    def user_id(self) -> str:
        return self.base.user_id

    @property
    def session_id(self) -> str:
        return self.base.session_id

    @property
    def project_id(self) -> Optional[str]:
        return self.base.project_id

    @property
    def trace_id(self) -> str:
        return self.base.trace_id

    @property
    def agent_id(self) -> Optional[str]:
        return self.execution.agent_id if self.execution else None

    @property
    def tool_call_id(self) -> Optional[str]:
        return self.execution.current_tool_call_id if self.execution else None

    @tool_call_id.setter
    def tool_call_id(self, value: str) -> None:
        if self.execution:
            self.execution.current_tool_call_id = value

    @property
    def user_message_id(self) -> Optional[str]:
        return self.execution.user_message_id if self.execution else None


__all__ = [
    "AgentContext",
    "BaseContext",
    "ExecutionContext",
    "MessagingContext",
    "WorkflowContext",
    "MemoryContext",
]
