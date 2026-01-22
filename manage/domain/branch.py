"""分支模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any
from uuid import uuid4

from .enums import BranchStatus


@dataclass
class Branch:
    """分支实体（从某里程碑分叉）"""
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    name: str = ""

    base_milestone_id: str = ""  # 分支基线
    head_milestone_id: str = ""  # 分支当前HEAD

    status: BranchStatus = BranchStatus.ACTIVE
    description: str = ""

    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_by: str = ""
    updated_at: datetime = field(default_factory=datetime.now)

    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_id:
            raise ValueError("项目ID不能为空")
        if not self.name:
            raise ValueError("分支名称不能为空")
        if not self.base_milestone_id:
            raise ValueError("分支基线不能为空")

    def update_head(self, milestone_id: str, updated_by: str = "") -> None:
        self.head_milestone_id = milestone_id
        self.updated_by = updated_by
        self.updated_at = datetime.now()

    def mark_under_review(self) -> None:
        self.status = BranchStatus.UNDER_REVIEW

    def mark_merged(self) -> None:
        self.status = BranchStatus.MERGED

    def close(self) -> None:
        self.status = BranchStatus.CLOSED

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "base_milestone_id": self.base_milestone_id,
            "head_milestone_id": self.head_milestone_id,
            "status": self.status.value,
            "description": self.description,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }
