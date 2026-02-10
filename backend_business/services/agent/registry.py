"""Agent definition and global registry.
Agent 定义和全局注册表。
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AgentDefinition:
    """Static configuration for a single agent.
    单个 Agent 的静态配置信息。
    """

    agent_id: str  # Agent 的唯一标识符
    name: str  # Agent 的显示名称
    system_prompt: str  # Agent 的系统提示词
    tool_names: List[str]  # 该 Agent 可使用的工具列表
    child_agent_ids: List[str] = field(default_factory=list)  # 该 Agent 可调度的子 Agent ID 列表
    max_tool_rounds: int = 6  # 最大工具调用轮数，防止无限循环


class AgentRegistry:
    """Global registry for managing all available agents.
    管理所有可用 Agent 的全局注册表。
    """

    def __init__(self) -> None:
        self._agents: Dict[str, AgentDefinition] = {}

    def register(self, agent_def: AgentDefinition) -> None:
        """Register a new agent definition.
        注册一个新的 Agent 定义。
        """
        self._agents[agent_def.agent_id] = agent_def

    def get(self, agent_id: str) -> Optional[AgentDefinition]:
        """Get an agent definition by ID.
        根据 ID 获取 Agent 定义。
        """
        return self._agents.get(agent_id)

    def list_agents(self) -> List[AgentDefinition]:
        """List all registered agents.
        列出所有已注册的 Agent。
        """
        return list(self._agents.values())


# Global instance of the agent registry
# Agent 注册表的全局实例
agent_registry = AgentRegistry()
