"""Tool definition and global registry.
工具定义和全局注册表。
"""

from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional


@dataclass
class ToolDefinition:
    """Describes a single tool available to agents.
    描述 Agent 可用的单个工具。
    """

    name: str  # 工具名称
    openai_schema: dict  # OpenAI function-call format; OpenAI 函数调用格式
    handler: Callable  # signature: (args: dict, ctx: AgentContext) -> dict; 处理函数签名
    is_write: bool = False  # True → goes through approval queue; True → 需要通过审批队列


class ToolRegistry:
    """Registry for managing tools.
    工具管理注册表。
    """

    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool_def: ToolDefinition) -> None:
        """Register a new tool.
        注册新工具。
        """
        self._tools[tool_def.name] = tool_def

    def get(self, name: str) -> Optional[ToolDefinition]:
        """Get a tool definition by name.
        按名称获取工具定义。
        """
        return self._tools.get(name)

    def get_schemas(self, names: List[str]) -> List[dict]:
        """Return OpenAI schemas for the given tool names (in order).
        返回给定工具名称的 OpenAI schema（按顺序）。
        """
        missing = [n for n in names if n not in self._tools]
        if missing:
            raise ValueError(f"Unknown tools in agent definition: {missing}")
        return [self._tools[n].openai_schema for n in names]

    def is_write(self, name: str) -> bool:
        """Check if a tool is a write operation.
        检查工具是否为写操作。
        """
        t = self._tools.get(name)
        return t.is_write if t else False


# Global singleton instance
# 全局单例实例
tool_registry = ToolRegistry()
