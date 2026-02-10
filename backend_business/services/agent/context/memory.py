"""Memory context - short-term and working memory for an agent.
记忆上下文 - Agent 的短期记忆和工作记忆。
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class MemoryContext:
    """Optional memory carried across rounds or conversations.
    跨轮次或对话携带的可选记忆。
    """

    short_term: List[Dict[str, Any]] = field(default_factory=list)  # recent conversation summaries; 最近对话摘要
    working_memory: Dict[str, Any] = field(default_factory=dict)  # scratch-pad for current task; 当前任务的暂存区
    facts: List[str] = field(default_factory=list)  # known facts / constraints; 已知事实/约束
