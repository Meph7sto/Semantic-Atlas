"""Multi-agent workflow definitions.
多 Agent 工作流定义。

A *Workflow* is a sequence of steps, each specifying which agent(s)
to run, what strategy to use, and how to pass data between steps.
*Workflow* 是一系列步骤，每个步骤指定运行哪个 Agent、使用什么策略以及如何在步骤之间传递数据。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class StepStatus(str, Enum):
    """Execution status of a workflow step.
    工作流步骤的执行状态。
    """

    PENDING = "pending"       # Waiting to start; 等待开始
    RUNNING = "running"       # Currently executing; 正在执行
    COMPLETED = "completed"   # Successfully finished; 成功完成
    FAILED = "failed"         # Execution failed; 执行失败
    SKIPPED = "skipped"       # Step was skipped; 步骤已跳过


@dataclass
class WorkflowStep:
    """A single step in a multi-agent workflow.
    多 Agent 工作流中的单个步骤。
    """

    step_id: str = field(default_factory=lambda: f"step_{uuid.uuid4().hex[:8]}")
    name: str = ""  # 步骤名称
    agent_ids: List[str] = field(default_factory=list)  # Participating agents; 参与的 Agent ID 列表
    strategy: str = "sequential"        # sequential / parallel / vote / debate; 协作策略
    input_mapping: Dict[str, str] = field(default_factory=dict)  # Data mapping from previous steps; 输入数据映射
    timeout: float = 300.0  # Execution timeout in seconds; 执行超时（秒）
    status: StepStatus = StepStatus.PENDING  # Current status; 当前状态
    result: Optional[Dict[str, Any]] = None  # Step output; 步骤输出
    error: Optional[str] = None  # Error message if failed; 错误信息（如果失败）
    started_at: Optional[datetime] = None  # Start timestamp; 开始时间
    completed_at: Optional[datetime] = None  # Completion timestamp; 完成时间

    def to_dict(self) -> dict:
        """Convert step to dictionary.
        将步骤转换为字典。
        """
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
    """Overall status of a workflow.
    工作流的整体状态。
    """

    CREATED = "created"       # Initialized but not started; 已初始化但未开始
    RUNNING = "running"       # In progress; 进行中
    COMPLETED = "completed"   # All steps finished; 所有步骤完成
    FAILED = "failed"         # Terminated due to error; 因错误终止
    CANCELLED = "cancelled"   # Manually stopped; 手动停止


@dataclass
class Workflow:
    """A multi-step, multi-agent workflow.
    多步骤、多 Agent 工作流。

    Usage::
    用法：

        wf = Workflow(name="需求评审")
        wf.add_step(WorkflowStep(name="提取需求", agent_ids=["requirements_agent"]))
        wf.add_step(WorkflowStep(name="冲突检测", agent_ids=["conflict_agent"]))
        wf.add_step(WorkflowStep(name="追溯分析", agent_ids=["traceability_agent"]))

        await workflow_engine.run(wf, initial_input={...})
    """

    workflow_id: str = field(default_factory=lambda: f"wf_{uuid.uuid4().hex[:12]}")
    name: str = ""  # 工作流名称
    description: str = ""  # 工作流描述
    project_id: Optional[str] = None  # 关联的项目 ID
    steps: List[WorkflowStep] = field(default_factory=list)  # 步骤列表
    status: WorkflowStatus = WorkflowStatus.CREATED  # 当前状态
    accumulated_results: Dict[str, Any] = field(default_factory=dict)  # Results from all steps; 所有步骤的累积结果
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))  # 创建时间
    completed_at: Optional[datetime] = None  # 完成时间

    # ------------------------------------------------------------------
    # Step management
    # 步骤管理
    # ------------------------------------------------------------------

    def add_step(self, step: WorkflowStep) -> None:
        """Add a step to the workflow.
        向工作流添加步骤。
        """
        self.steps.append(step)

    @property
    def current_step_index(self) -> int:
        """Get the index of the first pending or running step.
        获取第一个待处理或正在运行的步骤的索引。
        """
        for i, step in enumerate(self.steps):
            if step.status in (StepStatus.PENDING, StepStatus.RUNNING):
                return i
        return len(self.steps)  # all done

    @property
    def total_steps(self) -> int:
        """Total number of steps.
        总步骤数。
        """
        return len(self.steps)

    @property
    def is_complete(self) -> bool:
        """Check if all steps are completed (or skipped).
        检查所有步骤是否已完成（或跳过）。
        """
        return all(s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED) for s in self.steps)

    @property
    def progress(self) -> float:
        """Calculate progress (0.0 to 1.0).
        计算进度（0.0 到 1.0）。
        """
        if not self.steps:
            return 1.0
        done = sum(1 for s in self.steps if s.status in (StepStatus.COMPLETED, StepStatus.SKIPPED))
        return done / len(self.steps)

    # ------------------------------------------------------------------
    # Serialisation
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        """Convert workflow to dictionary.
        将工作流转换为字典。
        """
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
