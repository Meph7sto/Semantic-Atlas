"""Orchestration layer for multi-agent collaboration.

Provides:
- Supervisor: manages agent lifecycle and health
- Workflow: defines multi-step agent pipelines
- Strategies: collaboration patterns (sequential, parallel, vote)
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
