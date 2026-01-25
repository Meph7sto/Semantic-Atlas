"""需求树模型定义"""
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .requirement import Requirement


@dataclass
class RequirementTreeNode:
    """需求树节点（包装Requirement以构建树结构）"""
    requirement: Requirement
    children: List["RequirementTreeNode"] = field(default_factory=list)

    def add_child(self, child: "RequirementTreeNode") -> None:
        self.children.append(child)
        self.children.sort(key=lambda n: n.requirement.order)

    def remove_child(self, child_id: str) -> bool:
        for i, child in enumerate(self.children):
            if child.requirement.id == child_id:
                self.children.pop(i)
                return True
        return False

    def find_node(self, requirement_id: str) -> Optional["RequirementTreeNode"]:
        if self.requirement.id == requirement_id:
            return self
        for child in self.children:
            found = child.find_node(requirement_id)
            if found:
                return found
        return None

    def get_all_descendants(self) -> List[Requirement]:
        descendants: List[Requirement] = []
        for child in self.children:
            descendants.append(child.requirement)
            descendants.extend(child.get_all_descendants())
        return descendants

    def to_dict(self) -> Dict:
        return {
            "requirement": self.requirement.to_dict(),
            "children": [child.to_dict() for child in self.children]
        }


class RequirementTree:
    """需求树（整棵树的管理类）"""

    def __init__(self, project_id: str):
        self.project_id = project_id
        self.root_nodes: List[RequirementTreeNode] = []
        self._node_map: Dict[str, RequirementTreeNode] = {}

    def build_tree(self, requirements: List[Requirement]) -> Tuple[bool, List[str]]:
        errors: List[str] = []

        valid_requirements = [
            req for req in requirements
            if not req.deleted and req.project_id == self.project_id
        ]

        self._node_map.clear()
        for req in valid_requirements:
            self._node_map[req.id] = RequirementTreeNode(requirement=req)

        if self._has_cycle():
            errors.append("检测到需求树中存在环路")
            return False, errors

        self.root_nodes.clear()
        orphans: List[str] = []

        for req in valid_requirements:
            node = self._node_map[req.id]
            if req.parent_id is None:
                self.root_nodes.append(node)
            elif req.parent_id in self._node_map:
                parent_node = self._node_map[req.parent_id]
                if not parent_node.requirement.can_have_child(req.requirement_type):
                    errors.append(
                        f"需求 {req.id} ({req.requirement_type.value}) "
                        f"不能作为 {parent_node.requirement.id} "
                        f"({parent_node.requirement.requirement_type.value}) 的子节点"
                    )
                else:
                    parent_node.add_child(node)
            else:
                orphans.append(req.id)

        if orphans:
            errors.append(f"发现孤儿节点（父节点不存在）: {orphans}")

        self.root_nodes.sort(key=lambda n: n.requirement.order)
        success = len(errors) == 0
        return success, errors

    def _has_cycle(self) -> bool:
        visited = set()
        rec_stack = set()

        def dfs(req_id: str) -> bool:
            if req_id in rec_stack:
                return True
            if req_id in visited:
                return False

            visited.add(req_id)
            rec_stack.add(req_id)

            node = self._node_map.get(req_id)
            if node:
                for child in node.children:
                    if dfs(child.requirement.id):
                        return True

            rec_stack.remove(req_id)
            return False

        for req_id in self._node_map.keys():
            if req_id not in visited:
                if dfs(req_id):
                    return True

        return False

    def add_requirement(self, requirement: Requirement) -> Tuple[bool, str]:
        if requirement.id in self._node_map:
            return False, f"需求 {requirement.id} 已存在"

        if requirement.project_id != self.project_id:
            return False, "需求不属于当前项目"

        if requirement.parent_id:
            if requirement.parent_id not in self._node_map:
                return False, f"父节点 {requirement.parent_id} 不存在"

            parent_node = self._node_map[requirement.parent_id]
            if not parent_node.requirement.can_have_child(requirement.requirement_type):
                return False, "不符合层级规则"

        new_node = RequirementTreeNode(requirement=requirement)
        self._node_map[requirement.id] = new_node

        if requirement.parent_id:
            parent_node = self._node_map[requirement.parent_id]
            parent_node.add_child(new_node)
        else:
            self.root_nodes.append(new_node)
            self.root_nodes.sort(key=lambda n: n.requirement.order)

        return True, ""

    def remove_requirement(self, requirement_id: str, cascade: bool = False) -> Tuple[bool, str]:
        if requirement_id not in self._node_map:
            return False, f"需求 {requirement_id} 不存在"

        node = self._node_map[requirement_id]

        if node.children and not cascade:
            return False, "需求有子节点，不能删除（使用cascade=True强制删除）"

        if node.requirement.parent_id:
            parent_node = self._node_map[node.requirement.parent_id]
            parent_node.remove_child(requirement_id)
        else:
            self.root_nodes = [n for n in self.root_nodes if n.requirement.id != requirement_id]

        if cascade:
            to_delete = [requirement_id]
            descendants = node.get_all_descendants()
            to_delete.extend([d.id for d in descendants])

            for rid in to_delete:
                if rid in self._node_map:
                    del self._node_map[rid]
        else:
            del self._node_map[requirement_id]

        return True, ""

    def move_requirement(self, requirement_id: str, new_parent_id: Optional[str], new_order: int = 0) -> Tuple[bool, str]:
        if requirement_id not in self._node_map:
            return False, f"需求 {requirement_id} 不存在"

        node = self._node_map[requirement_id]
        old_parent_id = node.requirement.parent_id

        if new_parent_id:
            if new_parent_id not in self._node_map:
                return False, f"新父节点 {new_parent_id} 不存在"

            if new_parent_id == requirement_id:
                return False, "不能移动到自己"

            descendants = node.get_all_descendants()
            if any(d.id == new_parent_id for d in descendants):
                return False, "不能移动到自己的后代节点"

            new_parent_node = self._node_map[new_parent_id]
            if not new_parent_node.requirement.can_have_child(node.requirement.requirement_type):
                return False, "不符合层级规则"

        if old_parent_id:
            old_parent_node = self._node_map[old_parent_id]
            old_parent_node.remove_child(requirement_id)
        else:
            self.root_nodes = [n for n in self.root_nodes if n.requirement.id != requirement_id]

        node.requirement.move_to(new_parent_id, new_order)

        if new_parent_id:
            new_parent_node = self._node_map[new_parent_id]
            new_parent_node.add_child(node)
        else:
            self.root_nodes.append(node)
            self.root_nodes.sort(key=lambda n: n.requirement.order)

        return True, ""

    def find_requirement(self, requirement_id: str) -> Optional[Requirement]:
        node = self._node_map.get(requirement_id)
        return node.requirement if node else None

    def search_requirements(self, keyword: str) -> List[Requirement]:
        keyword = keyword.lower()
        results = []
        for node in self._node_map.values():
            if keyword in node.requirement.title.lower() or keyword in node.requirement.description.lower():
                results.append(node.requirement)
        return results

    def get_tree_statistics(self) -> Dict[str, int]:
        type_distribution: Dict[str, int] = {}
        for node in self._node_map.values():
            rtype = node.requirement.requirement_type.value
            type_distribution[rtype] = type_distribution.get(rtype, 0) + 1

        return {
            "total_count": len(self._node_map),
            "root_count": len(self.root_nodes),
            "type_distribution": type_distribution,
        }

    def to_dict(self) -> Dict:
        return {
            "project_id": self.project_id,
            "roots": [node.to_dict() for node in self.root_nodes],
            "stats": self.get_tree_statistics(),
        }
