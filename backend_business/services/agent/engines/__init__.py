"""Engine package — pluggable LLM tool-calling engines.

Usage::

    from backend_business.services.agent.engines import create_engine

    engine = create_engine(use_thinking_mode=True)
    result = engine.run(messages, tools_schema, tool_executor)
"""

from backend_business.services.agent.engines.base import (
    BaseEngine,
    EngineRunResult,
    ToolCallRequest,
    ToolResult,
    ToolExecutor,
)
from backend_business.services.agent.engines.thinking_tool_engine import (
    ThinkingToolCallEngine,
)


def create_engine(use_thinking_mode: bool = False) -> BaseEngine:
    """Factory: create the appropriate engine for the requested mode."""
    model = "deepseek-reasoner" if use_thinking_mode else "deepseek-chat"
    return ThinkingToolCallEngine(model=model)


__all__ = [
    "create_engine",
    "BaseEngine",
    "EngineRunResult",
    "ToolCallRequest",
    "ToolResult",
    "ToolExecutor",
    "ThinkingToolCallEngine",
]
