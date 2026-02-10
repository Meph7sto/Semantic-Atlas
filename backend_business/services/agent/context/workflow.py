"""Workflow context - state for multi-agent orchestration.
工作流上下文 - 多 Agent 编排的状态。
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class WorkflowContext:
    """Present when an agent is running as part of a multi-step workflow.
    当 Agent 作为多步工作流的一部分运行时存在。
    """

    workflow_id: str  # 当前工作流 ID
    workflow_name: str  # 工作流名称
    step_index: int = 0  # 当前步骤索引
    total_steps: int = 1  # 总步骤数
    accumulated_results: Dict[str, Any] = field(default_factory=dict)  # 累积的执行结果
    strategy: str = "sequential"  # sequential / parallel / vote / debate; 顺序 / 并行 / 投票 / 辩论
    deadline: Optional[datetime] = None  # 截止时间（可选）
