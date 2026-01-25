"""合并模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4

from .enums import MergeStatus, ConflictResolutionStrategy


@dataclass
class MergeConflict:
    """合并冲突"""
    requirement_id: str
    fields: List[str] = field(default_factory=list)
    description: str = ""
    resolution: Optional[str] = None  # TODO: 结构化冲突解决方案
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "fields": self.fields,
            "description": self.description,
            "resolution": self.resolution,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class MergeRecord:
    """合并记录"""
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    branch_id: str = ""

    base_milestone_id: str = ""
    source_milestone_id: str = ""  # 分支HEAD
    target_milestone_id: str = ""  # 主线HEAD
    result_milestone_id: Optional[str] = None

    status: MergeStatus = MergeStatus.PENDING
    conflicts: List[MergeConflict] = field(default_factory=list)
    resolution_strategy: ConflictResolutionStrategy = ConflictResolutionStrategy.MANUAL

    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    merged_by: Optional[str] = None
    merged_at: Optional[datetime] = None

    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_conflicts(self, conflicts: List[MergeConflict]) -> None:
        self.conflicts = conflicts
        self.status = MergeStatus.CONFLICTS if conflicts else self.status

    def resolve_conflict(self, requirement_id: str, resolution: str) -> None:
        for conflict in self.conflicts:
            if conflict.requirement_id == requirement_id:
                conflict.resolution = resolution
                break

    def complete_merge(self, result_milestone_id: str, merged_by: str) -> None:
        self.result_milestone_id = result_milestone_id
        self.status = MergeStatus.MERGED
        self.merged_by = merged_by
        self.merged_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "branch_id": self.branch_id,
            "base_milestone_id": self.base_milestone_id,
            "source_milestone_id": self.source_milestone_id,
            "target_milestone_id": self.target_milestone_id,
            "result_milestone_id": self.result_milestone_id,
            "status": self.status.value,
            "conflicts": [c.to_dict() for c in self.conflicts],
            "resolution_strategy": self.resolution_strategy.value,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "merged_by": self.merged_by,
            "merged_at": self.merged_at.isoformat() if self.merged_at else None,
            "metadata": self.metadata,
        }
