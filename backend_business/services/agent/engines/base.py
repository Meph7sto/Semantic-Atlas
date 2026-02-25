"""Engine base types and abstract interface.

Defines the data contracts between the AgentRunner and any LLM engine
implementation (thinking-mode, standard chat, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, Generator, List, Optional


# ------------------------------------------------------------------
# Data types
# ------------------------------------------------------------------

@dataclass
class ToolCallRequest:
    """A single tool call requested by the model."""
    id: str
    name: str
    arguments: Optional[Dict[str, Any]]


@dataclass
class ToolResult:
    """Result of executing one tool call."""
    tool_call_id: str
    name: str
    content: Any
    is_write: bool = False
    task: Optional[Dict[str, Any]] = None  # populated for write tools


@dataclass
class EngineResponse:
    """Parsed response from a single LLM round."""
    content: str = ""
    reasoning_content: str = ""
    tool_calls: List[ToolCallRequest] = field(default_factory=list)
    finish_reason: str = ""


@dataclass
class EngineRunResult:
    """Final result of a complete engine run (possibly multi-round)."""
    content: str = ""
    thinking_content: str = ""
    tasks_created: List[Dict[str, Any]] = field(default_factory=list)
    errors: List[Dict[str, Any]] = field(default_factory=list)
    rounds_used: int = 0


# Callback type: runner provides this so the engine can execute tools
# without knowing about the tool registry or agent context.
ToolExecutor = Callable[[ToolCallRequest], ToolResult]


# ------------------------------------------------------------------
# Abstract base
# ------------------------------------------------------------------

class BaseEngine(ABC):
    """Abstract interface for an LLM tool-calling engine."""

    @abstractmethod
    def run(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[dict],
        tool_executor: ToolExecutor,
        max_rounds: int = 6,
        max_tokens: int = 4096,
    ) -> EngineRunResult:
        """Synchronous multi-round execution. Returns final result."""
        ...

    @abstractmethod
    def stream(
        self,
        messages: List[Dict[str, Any]],
        tools_schema: List[dict],
        tool_executor: ToolExecutor,
        max_rounds: int = 6,
        max_tokens: int = 4096,
    ) -> Generator[Dict[str, Any], None, EngineRunResult]:
        """Streaming multi-round execution.

        Yields event dicts with ``{"type": ..., ...}`` matching the SSE
        event types the runner already emits (thinking, token, tool_call,
        tool_result, task_created, finish, error).

        The generator's return value (accessible via StopIteration.value)
        is the final ``EngineRunResult``.
        """
        ...
