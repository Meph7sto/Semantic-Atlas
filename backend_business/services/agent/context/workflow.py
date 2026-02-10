"""Workflow context - state for multi-agent orchestration."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class WorkflowContext:
    """Present when an agent is running as part of a multi-step workflow."""

    workflow_id: str
    workflow_name: str
    step_index: int = 0
    total_steps: int = 1
    accumulated_results: Dict[str, Any] = field(default_factory=dict)
    strategy: str = "sequential"                    # sequential / parallel / vote / debate
    deadline: Optional[datetime] = None
