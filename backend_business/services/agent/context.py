"""Agent execution context - passed through the entire call tree."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class AgentContext:
    """Carries per-request state through agent execution."""

    user_id: str
    session_id: str
    project_id: Optional[str] = None
    depth: int = 0  # nesting level for hierarchical agents
    parent_agent_id: Optional[str] = None
    user_message_id: Optional[str] = None
    tool_call_id: Optional[str] = None  # updated by runner before each tool invocation
