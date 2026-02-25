"""Execution context - state for the tool-calling loop."""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionContext:
    """Tracks state while an agent runs its tool-calling loop."""

    agent_id: str
    depth: int = 0                                  # nesting level for hierarchical agents
    parent_agent_id: Optional[str] = None           # who spawned this agent
    current_tool_call_id: Optional[str] = None      # updated before each tool invocation
    user_message_id: Optional[str] = None           # the user message that triggered this run
    round_number: int = 0                           # current tool-calling round
    max_rounds: int = 6                             # ceiling (matches runner default)
