"""Agent definition and global registry."""

from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class AgentDefinition:
    """Static configuration for a single agent."""

    agent_id: str
    name: str
    system_prompt: str
    tool_names: List[str]
    child_agent_ids: List[str] = field(default_factory=list)
    max_tool_rounds: int = 6


class AgentRegistry:
    def __init__(self) -> None:
        self._agents: Dict[str, AgentDefinition] = {}

    def register(self, agent_def: AgentDefinition) -> None:
        self._agents[agent_def.agent_id] = agent_def

    def get(self, agent_id: str) -> Optional[AgentDefinition]:
        return self._agents.get(agent_id)

    def list_agents(self) -> List[AgentDefinition]:
        return list(self._agents.values())


agent_registry = AgentRegistry()
