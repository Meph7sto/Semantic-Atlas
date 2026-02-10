"""Orchestration layer for multi-agent collaboration.
多 Agent 协作的编排层。

Provides:
- Supervisor: manages agent lifecycle and health
  Supervisor：管理 Agent 生命周期和健康状态
- Workflow: defines multi-step agent pipelines
  Workflow：定义多步骤 Agent 管道
- Strategies: collaboration patterns (sequential, parallel, vote)
  Strategies：协作模式（顺序、并行、投票）
"""

from .supervisor import AgentSupervisor, supervisor
from .workflow import Workflow, WorkflowStep
from .strategies import (
    CollaborationStrategy,
    SequentialStrategy,
    ParallelStrategy,
    VoteStrategy,
)

__all__ = [
    "AgentSupervisor",
    "supervisor",
    "Workflow",
    "WorkflowStep",
    "CollaborationStrategy",
    "SequentialStrategy",
    "ParallelStrategy",
    "VoteStrategy",
]
