"""影响分析模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, List, Optional
from uuid import uuid4

from .enums import ImpactLevel
from .change_set import ChangeSet


@dataclass
class ImpactItem:
    """受影响节点"""
    requirement_id: str
    level: ImpactLevel = ImpactLevel.MEDIUM
    reason: str = ""
    path: List[str] = field(default_factory=list)  # 影响路径（节点ID链路）
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "requirement_id": self.requirement_id,
            "level": self.level.value,
            "reason": self.reason,
            "path": self.path,
            "metadata": self.metadata,
        }


@dataclass
class ImpactReport:
    """影响分析报告"""
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    branch_id: str = ""
    base_milestone_id: str = ""
    change_set_id: str = ""

    generated_by: str = ""
    generated_at: datetime = field(default_factory=datetime.now)

    items: List[ImpactItem] = field(default_factory=list)
    summary: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def build_summary(self) -> Dict[str, Any]:
        level_counts = {l.value: 0 for l in ImpactLevel}
        for item in self.items:
            level_counts[item.level.value] += 1
        self.summary = {
            "total": len(self.items),
            "by_level": level_counts,
        }
        return self.summary

    def to_dict(self) -> Dict[str, Any]:
        if not self.summary:
            self.build_summary()
        return {
            "id": self.id,
            "project_id": self.project_id,
            "branch_id": self.branch_id,
            "base_milestone_id": self.base_milestone_id,
            "change_set_id": self.change_set_id,
            "generated_by": self.generated_by,
            "generated_at": self.generated_at.isoformat(),
            "summary": self.summary,
            "items": [i.to_dict() for i in self.items],
            "metadata": self.metadata,
        }


class ImpactAnalysisService:
    """影响分析服务接口（占位实现）"""

    def analyze(
        self,
        change_set: ChangeSet,
        project_id: str,
        base_milestone_id: str,
        generated_by: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> ImpactReport:
        raise NotImplementedError("影响分析算法尚未实现，请在基础设施层接入真实算法")
