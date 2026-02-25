"""Tool definition and global registry."""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolDefinition:
    """Describes a single tool available to agents."""

    name: str
    openai_schema: dict  # OpenAI function-call format
    handler: Callable  # signature: (args: dict, ctx: AgentContext) -> dict
    is_write: bool = False  # True → goes through approval queue


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool_def: ToolDefinition) -> None:
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def get_schemas(self, names: List[str]) -> List[dict]:
        """Return OpenAI schemas for the given tool names (in order)."""
        missing = [n for n in names if n not in self._tools]
        if missing:
            raise ValueError(f"Unknown tools in agent definition: {missing}")
        return [self._tools[n].openai_schema for n in names]

    def is_write(self, name: str) -> bool:
        t = self._tools.get(name)
        return t.is_write if t else False


tool_registry = ToolRegistry()
