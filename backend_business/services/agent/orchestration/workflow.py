"""Multi-agent workflow definitions.

A *Workflow* is a sequence of steps, each specifying which agent(s)
to run, what strategy to use, and how to pass data between steps.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class StepStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class WorkflowStep:
    """A single step in a multi-agent workflow."""

    step_id: str = field(default_factory=lambda: f"step_{uuid.uuid4().hex[:8]}")
    name: str = ""
    agent_ids: List[str] = field(default_factory=list)
    strategy: str = "sequential"        # sequential / parallel / vote / debate
    input_mapping: Dict[str, str] = field(default_factory=dict)
    timeout: float = 300.0
    status: StepStatus = StepStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None

    def to_dict(self) -> dict:
        return {
            "step_id": self.step_id,
            "name": self.name,
            "agent_ids": self.agent_ids,
            "strategy": self.strategy,
            "status": self.status.value,
            "result": self.result,
            "error": self.error,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }


class WorkflowStatus(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class Workflow:
    """A multi-step, multi-agent workflow.

    Usage::

        wf = Workflow(name="需求评审")
        wf.add_step(WorkflowStep(name="提取需求", agent_ids=["requirements_agent"]))
        wf.add_step(WorkflowStep(name="冲突检测", agent_ids=["conflict_agent"]))
        wf.add_step(WorkflowStep(name="追溯分析", agent_ids=["traceability_agent"]))

        await workflow_engine.run(wf, initial_input={...})
    """

    workflow_id: str = field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:12]}")
    name: str = ""
    description: str = ""
    project_id: Optional[str] = None
    steps: List[WorkflowStep] = field(default_factory=list)
    status: WorkflowStatus = WorkflowStatus.CREATED
    accumulated_results: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    completed_at: Optional[datetime] = None

    # ------------------------------------------------------------------
    # Step management
    # ------------------------------------------------------------------

    def add_step(self, step: WorkflowStep) -> None:
        self.steps.append(step)

    @property
    def current_step_index(self) -> int:
        for i, step in enumerate(self.steps):
            if step.status in (StepStatus.PENDING, StepStatus.RUNNING):
                return i
        return len(self.steps)  # all done

    @property
    def total_steps(self) -> int:
        return len(self.steps)

    @property
    def is_complete(self) -> bool:
        return all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in self.steps)

    @property
    def progress(self) -> float:
        if not self.steps:
            return 1.0
        done = sum(1 for s in self.steps if s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED))
        return done / len(self.steps)

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "workflow_id": self.workflow_id,
            "name": self.name,
            "description": self.description,
            "project_id": self.project_id,
            "status": self.status.value,
            "progress": self.progress,
            "steps": [s.to_dict() for s in self.steps],
            "accumulated_results": self.accumulated_results,
            "created_at": self.created_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
        }
