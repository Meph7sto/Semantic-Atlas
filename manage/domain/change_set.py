"""变更集模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4

from .enums import ChangeType


@dataclass
class RequirementChange:
    """单个需求变更"""
    requirement_id: str
    change_type: ChangeType
    before: Optional[Dict[str, Any]] = None
    after: Optional[Dict[str, Any]] = None
    fields_changed: List[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "change_type": self.change_type.value,
            "before": self.before,
            "after": self.after,
            "fields_changed": self.fields_changed,
            "reason": self.reason,
        }


@dataclass
class ChangeSet:
    """分支相对基线的变更集"""
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    branch_id: str = ""
    base_milestone_id: str = ""
    target_milestone_id: Optional[str] = None

    changes: List[RequirementChange] = field(default_factory=list)

    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def add_change(self, change: RequirementChange) -> None:
        self.changes.append(change)

    def get_change_by_requirement(self, requirement_id: str) -> Optional[RequirementChange]:
        for change in self.changes:
            if change.requirement_id == requirement_id:
                return change
        return None

    def get_summary(self) -> Dict[str, int]:
        summary = {"added": 0, "modified": 0, "deleted": 0, "moved": 0}
        for change in self.changes:
            key = change.change_type.value
            if key in summary:
                summary[key] += 1
        summary["total"] = len(self.changes)
        return summary

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "branch_id": self.branch_id,
            "base_milestone_id": self.base_milestone_id,
            "target_milestone_id": self.target_milestone_id,
            "summary": self.get_summary(),
            "changes": [c.to_dict() for c in self.changes],
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }
