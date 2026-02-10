"""Execution context - state for the tool-calling loop.
执行上下文 - 工具调用循环的状态。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ExecutionContext:
    """Tracks state while an agent runs its tool-calling loop.
    当 Agent 运行其工具调用循环时跟踪状态。
    """

    agent_id: str  # 当前正在执行的 Agent ID
    depth: int = 0  # nesting level for hierarchical agents; 分层 Agent 的嵌套级别
    parent_agent_id: Optional[str] = None  # who spawned this agent; 谁生成了这个 Agent
    current_tool_call_id: Optional[str] = None  # updated before each tool invocation; 每次工具调用前更新
    user_message_id: Optional[str] = None  # the user message that triggered this run; 触发此次运行的用户消息 ID
    round_number: int = 0  # current tool-calling round; 当前工具调用轮次
    max_rounds: int = 6  # ceiling (matches runner default); 上限（匹配运行器默认值）
