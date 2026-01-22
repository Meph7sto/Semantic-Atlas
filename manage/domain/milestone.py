"""里程碑（Milestone）模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import List, Dict, Optional, Any, Tuple
from uuid import uuid4

from .requirement import Requirement
from .requirement_tree import RequirementTree
from .enums import ChangeType


@dataclass
class MilestoneNodeSnapshot:
    """里程碑节点快照"""
    id: str = field(default_factory=lambda: str(uuid4()))
    milestone_id: str = ""

    requirement_id: str = ""
    requirement_type: str = ""
    status: str = ""
    title: str = ""
    description: str = ""
    parent_id: Optional[str] = None
    order: int = 0

    snapshot_data: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)

    @classmethod
    def from_requirement(cls, requirement: Requirement, milestone_id: str) -> "MilestoneNodeSnapshot":
        return cls(
            milestone_id=milestone_id,
            requirement_id=requirement.id,
            requirement_type=requirement.requirement_type.value,
            status=requirement.status.value,
            title=requirement.title,
            description=requirement.description,
            parent_id=requirement.parent_id,
            order=requirement.order,
            snapshot_data=requirement.to_dict(),
        )

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "milestone_id": self.milestone_id,
            "requirement_id": self.requirement_id,
            "requirement_type": self.requirement_type,
            "status": self.status,
            "title": self.title,
            "description": self.description,
            "parent_id": self.parent_id,
            "order": self.order,
            "snapshot_data": self.snapshot_data,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class MilestoneRelationSnapshot:
    """里程碑关系快照"""
    id: str = field(default_factory=lambda: str(uuid4()))
    milestone_id: str = ""
    parent_id: str = ""
    child_id: str = ""
    order: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "milestone_id": self.milestone_id,
            "parent_id": self.parent_id,
            "child_id": self.child_id,
            "order": self.order,
        }


@dataclass
class Milestone:
    """里程碑（Milestone）"""
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""

    name: str = ""
    description: str = ""
    message: str = ""

    milestone_type: str = "regular"
    is_baseline: bool = False

    sprint: Optional[str] = None
    version: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    snapshots: List[MilestoneNodeSnapshot] = field(default_factory=list)
    relations: List[MilestoneRelationSnapshot] = field(default_factory=list)

    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)

    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.project_id:
            raise ValueError("项目ID不能为空")
        if not self.name:
            raise ValueError("里程碑名称不能为空")

    def get_snapshot_count(self) -> int:
        return len(self.snapshots)

    def mark_as_baseline(self) -> None:
        self.is_baseline = True
        self.milestone_type = "baseline"

    def get_snapshot_by_requirement_id(self, requirement_id: str) -> Optional[MilestoneNodeSnapshot]:
        for snapshot in self.snapshots:
            if snapshot.requirement_id == requirement_id:
                return snapshot
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "name": self.name,
            "description": self.description,
            "message": self.message,
            "milestone_type": self.milestone_type,
            "is_baseline": self.is_baseline,
            "sprint": self.sprint,
            "version": self.version,
            "tags": self.tags,
            "snapshot_count": self.get_snapshot_count(),
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }

    def to_dict_full(self) -> Dict[str, Any]:
        data = self.to_dict()
        data["snapshots"] = [s.to_dict() for s in self.snapshots]
        data["relations"] = [r.to_dict() for r in self.relations]
        return data

    def validate_snapshot_integrity(self) -> Tuple[bool, List[str]]:
        errors: List[str] = []
        if not self.snapshots:
            errors.append("里程碑中没有任何快照")
            return False, errors

        snapshot_ids = {s.requirement_id for s in self.snapshots}

        for relation in self.relations:
            if relation.parent_id not in snapshot_ids:
                errors.append(f"关系中的父节点 {relation.parent_id} 在快照中不存在")
            if relation.child_id not in snapshot_ids:
                errors.append(f"关系中的子节点 {relation.child_id} 在快照中不存在")

        for snapshot in self.snapshots:
            if snapshot.parent_id and snapshot.parent_id not in snapshot_ids:
                errors.append(f"需求 {snapshot.requirement_id} 的父节点 {snapshot.parent_id} 在快照中不存在（孤儿节点）")

        for snapshot in self.snapshots:
            if not snapshot.snapshot_data:
                errors.append(f"需求 {snapshot.requirement_id} 的 snapshot_data 为空")
            elif "id" not in snapshot.snapshot_data:
                errors.append(f"需求 {snapshot.requirement_id} 的 snapshot_data 缺少 id 字段")

        return len(errors) == 0, errors


@dataclass
class MilestoneDiff:
    """里程碑差异"""
    from_milestone_id: str = ""
    to_milestone_id: str = ""

    added: List[str] = field(default_factory=list)
    deleted: List[str] = field(default_factory=list)
    modified: List[str] = field(default_factory=list)
    moved: List[str] = field(default_factory=list)

    changes: List[Dict[str, Any]] = field(default_factory=list)
    total_changes: int = 0

    def __post_init__(self) -> None:
        self.total_changes = len(self.added) + len(self.deleted) + len(self.modified) + len(self.moved)

    def add_change(self, change_type: ChangeType, requirement_id: str, details: Optional[Dict[str, Any]] = None) -> None:
        change = {
            "type": change_type.value,
            "requirement_id": requirement_id,
            "details": details or {}
        }
        self.changes.append(change)

        if change_type == ChangeType.ADDED:
            self.added.append(requirement_id)
        elif change_type == ChangeType.DELETED:
            self.deleted.append(requirement_id)
        elif change_type == ChangeType.MODIFIED:
            self.modified.append(requirement_id)
        elif change_type == ChangeType.MOVED:
            self.moved.append(requirement_id)

        self.total_changes += 1

    def to_dict(self) -> Dict[str, Any]:
        return {
            "from_milestone_id": self.from_milestone_id,
            "to_milestone_id": self.to_milestone_id,
            "summary": {
                "added": len(self.added),
                "deleted": len(self.deleted),
                "modified": len(self.modified),
                "moved": len(self.moved),
                "total": self.total_changes,
            },
            "added": self.added,
            "deleted": self.deleted,
            "modified": self.modified,
            "moved": self.moved,
            "changes": self.changes,
        }


class MilestoneService:
    """里程碑服务"""

    @staticmethod
    def create_milestone(
        project_id: str,
        requirements: List[Requirement],
        name: str,
        created_by: str,
        message: str = "",
        milestone_type: str = "regular",
        sprint: Optional[str] = None,
        version: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Milestone:
        milestone = Milestone(
            project_id=project_id,
            name=name,
            message=message,
            milestone_type=milestone_type,
            sprint=sprint,
            version=version,
            tags=tags or [],
            created_by=created_by,
            metadata=metadata or {},
        )

        for req in requirements:
            milestone.snapshots.append(MilestoneNodeSnapshot.from_requirement(req, milestone.id))

        for snapshot in milestone.snapshots:
            if snapshot.parent_id:
                milestone.relations.append(
                    MilestoneRelationSnapshot(
                        milestone_id=milestone.id,
                        parent_id=snapshot.parent_id,
                        child_id=snapshot.requirement_id,
                        order=snapshot.order,
                    )
                )

        return milestone

    @staticmethod
    def create_baseline(
        project_id: str,
        requirements: List[Requirement],
        name: str,
        created_by: str,
        message: str = "",
        sprint: Optional[str] = None,
        version: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Milestone:
        milestone = MilestoneService.create_milestone(
            project_id=project_id,
            requirements=requirements,
            name=name,
            created_by=created_by,
            message=message,
            milestone_type="baseline",
            sprint=sprint,
            version=version,
            tags=tags,
            metadata=metadata,
        )
        milestone.mark_as_baseline()
        return milestone

    @staticmethod
    def compare_milestones(from_milestone: Milestone, to_milestone: Milestone) -> MilestoneDiff:
        diff = MilestoneDiff(from_milestone_id=from_milestone.id, to_milestone_id=to_milestone.id)

        from_map = {s.requirement_id: s for s in from_milestone.snapshots}
        to_map = {s.requirement_id: s for s in to_milestone.snapshots}

        for rid in from_map.keys() - to_map.keys():
            diff.add_change(ChangeType.DELETED, rid)

        for rid in to_map.keys() - from_map.keys():
            diff.add_change(ChangeType.ADDED, rid)

        for rid in from_map.keys() & to_map.keys():
            from_s = from_map[rid]
            to_s = to_map[rid]

            if from_s.snapshot_data != to_s.snapshot_data:
                diff.add_change(ChangeType.MODIFIED, rid)

            if from_s.parent_id != to_s.parent_id or from_s.order != to_s.order:
                diff.add_change(ChangeType.MOVED, rid)

        return diff

    @staticmethod
    def restore_requirements_from_milestone(milestone: Milestone) -> List[Requirement]:
        return [Requirement.from_dict(s.snapshot_data) for s in milestone.snapshots]

    @staticmethod
    def restore_tree_from_milestone(milestone: Milestone) -> Optional[RequirementTree]:
        if not milestone.snapshots:
            return None

        requirements = MilestoneService.restore_requirements_from_milestone(milestone)
        tree = RequirementTree(project_id=milestone.project_id)
        tree.build_tree(requirements)
        return tree

    @staticmethod
    def get_milestone_tree_statistics(milestone: Milestone) -> Dict[str, Any]:
        counts: Dict[str, int] = {}
        roots = 0
        for snap in milestone.snapshots:
            counts[snap.requirement_type] = counts.get(snap.requirement_type, 0) + 1
            if snap.parent_id is None:
                roots += 1

        return {
            "total_count": len(milestone.snapshots),
            "root_count": roots,
            "type_distribution": counts,
        }
