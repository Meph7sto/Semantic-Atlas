"""里程碑图（MilestoneGraph）模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from uuid import uuid4

from .milestone import Milestone


@dataclass
class MilestoneEdge:
    """里程碑边（表示里程碑之间的父子关系）"""
    id: str = field(default_factory=lambda: str(uuid4()))
    child_milestone_id: str = ""
    parent_milestone_id: str = ""
    edge_type: str = "linear"
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "child_milestone_id": self.child_milestone_id,
            "parent_milestone_id": self.parent_milestone_id,
            "edge_type": self.edge_type,
            "created_at": self.created_at.isoformat(),
        }


@dataclass
class MilestoneGraphNode:
    """里程碑图节点（包装Milestone用于图遍历）"""
    milestone: Milestone
    parent_ids: List[str] = field(default_factory=list)
    child_ids: List[str] = field(default_factory=list)

    def is_merge_commit(self) -> bool:
        return len(self.parent_ids) > 1

    def is_root(self) -> bool:
        return len(self.parent_ids) == 0

    def is_leaf(self) -> bool:
        return len(self.child_ids) == 0

    def to_dict(self) -> Dict:
        return {
            "milestone": self.milestone.to_dict(),
            "parent_ids": self.parent_ids,
            "child_ids": self.child_ids,
            "is_merge": self.is_merge_commit(),
            "is_root": self.is_root(),
            "is_leaf": self.is_leaf(),
        }


class MilestoneGraph:
    """里程碑图（DAG）"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.nodes: Dict[str, MilestoneGraphNode] = {}
        self.edges: List[MilestoneEdge] = []
        self.head_id: Optional[str] = None
        self.branches: Dict[str, str] = {}

    def add_milestone(
        self,
        milestone: Milestone,
        parent_ids: Optional[List[str]] = None,
        is_main: bool = True
    ) -> Tuple[bool, str]:
        if milestone.project_id != self.project_id:
            return False, "里程碑不属于当前项目"

        if milestone.id in self.nodes:
            return False, f"里程碑 {milestone.id} 已存在"

        parent_ids = parent_ids or []
        for parent_id in parent_ids:
            if parent_id not in self.nodes:
                return False, f"父里程碑 {parent_id} 不存在"

        node = MilestoneGraphNode(milestone=milestone, parent_ids=parent_ids.copy())
        self.nodes[milestone.id] = node

        for parent_id in parent_ids:
            edge_type = "merge" if len(parent_ids) > 1 else "linear"
            edge = MilestoneEdge(
                child_milestone_id=milestone.id,
                parent_milestone_id=parent_id,
                edge_type=edge_type,
            )
            self.edges.append(edge)

            parent_node = self.nodes[parent_id]
            parent_node.child_ids.append(milestone.id)

        if is_main:
            self.head_id = milestone.id

        return True, ""

    def get_milestone(self, milestone_id: str) -> Optional[Milestone]:
        node = self.nodes.get(milestone_id)
        return node.milestone if node else None

    def get_head(self) -> Optional[Milestone]:
        return self.get_milestone(self.head_id) if self.head_id else None

    def get_baselines(self) -> List[Milestone]:
        return [node.milestone for node in self.nodes.values() if node.milestone.is_baseline]

    def get_parents(self, milestone_id: str) -> List[Milestone]:
        node = self.nodes.get(milestone_id)
        if not node:
            return []

        parents = []
        for parent_id in node.parent_ids:
            parent = self.get_milestone(parent_id)
            if parent:
                parents.append(parent)
        return parents

    def get_children(self, milestone_id: str) -> List[Milestone]:
        node = self.nodes.get(milestone_id)
        if not node:
            return []

        children = []
        for child_id in node.child_ids:
            child = self.get_milestone(child_id)
            if child:
                children.append(child)
        return children

    def get_ancestors(self, milestone_id: str) -> List[Milestone]:
        ancestors: List[Milestone] = []
        visited = set()

        def dfs(mid: str) -> None:
            if mid in visited:
                return
            visited.add(mid)

            node = self.nodes.get(mid)
            if not node:
                return

            for parent_id in node.parent_ids:
                parent = self.get_milestone(parent_id)
                if parent:
                    ancestors.append(parent)
                    dfs(parent_id)

        dfs(milestone_id)
        ancestors.sort(key=lambda m: m.created_at, reverse=True)
        return ancestors

    def get_history(self, milestone_id: Optional[str] = None, max_count: Optional[int] = None) -> List[Milestone]:
        start_id = milestone_id or self.head_id
        if not start_id:
            return []

        current = self.get_milestone(start_id)
        if not current:
            return []

        history = [current]
        history.extend(self.get_ancestors(start_id))

        if max_count:
            history = history[:max_count]

        return history

    def find_common_ancestor(self, milestone_id1: str, milestone_id2: str) -> Optional[Milestone]:
        ancestors1 = {milestone_id1}
        ancestors1.update(m.id for m in self.get_ancestors(milestone_id1))

        if milestone_id2 in ancestors1:
            return self.get_milestone(milestone_id2)

        for ancestor in self.get_ancestors(milestone_id2):
            if ancestor.id in ancestors1:
                return ancestor

        return None

    def get_graph_statistics(self) -> Dict:
        merge_commits = sum(1 for node in self.nodes.values() if node.is_merge_commit())
        baselines = sum(1 for node in self.nodes.values() if node.milestone.is_baseline)

        return {
            "total_milestones": len(self.nodes),
            "total_baselines": baselines,
            "total_edges": len(self.edges),
            "root_milestones": len([n for n in self.nodes.values() if n.is_root()]),
            "leaf_milestones": len([n for n in self.nodes.values() if n.is_leaf()]),
            "merge_commits": merge_commits,
            "branches": len(self.branches),
            "head_id": self.head_id,
        }

    def create_branch(self, branch_name: str, milestone_id: str) -> Tuple[bool, str]:
        if branch_name in self.branches:
            return False, f"分支 {branch_name} 已存在"

        if milestone_id not in self.nodes:
            return False, f"里程碑 {milestone_id} 不存在"

        self.branches[branch_name] = milestone_id
        return True, ""

    def update_branch(self, branch_name: str, milestone_id: str) -> Tuple[bool, str]:
        if branch_name not in self.branches:
            return False, f"分支 {branch_name} 不存在"

        if milestone_id not in self.nodes:
            return False, f"里程碑 {milestone_id} 不存在"

        self.branches[branch_name] = milestone_id
        return True, ""

    def export_mermaid(self) -> str:
        lines = ["graph TD"]
        for milestone_id, node in self.nodes.items():
            label = f"{node.milestone.name}"
            if node.milestone.is_baseline:
                label += " [BASELINE]"
            if milestone_id == self.head_id:
                label += " [HEAD]"
            lines.append(f"  {milestone_id}[\"{label}\"]")

        for edge in self.edges:
            lines.append(f"  {edge.parent_milestone_id} --> {edge.child_milestone_id}")

        return "\n".join(lines)
