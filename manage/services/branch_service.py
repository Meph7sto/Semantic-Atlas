"""分支与变更集应用服务"""
from __future__ import annotations
from typing import Optional

from .base_service import AppService
from ..domain.branch import Branch
from ..domain.change_set import ChangeSet, RequirementChange
from ..domain.enums import ChangeType


class BranchService(AppService):
    """分支用例服务"""

    def create_branch(self, project_id: str, name: str, base_milestone_id: str, created_by: str, description: str = "") -> Branch:
        branch = Branch(
            project_id=project_id,
            name=name,
            base_milestone_id=base_milestone_id,
            head_milestone_id=base_milestone_id,
            created_by=created_by,
            description=description,
        )
        repo = self.repos.get("branch")
        if repo:
            repo.add(branch)
        if self.uow:
            self.uow.commit()
        return branch

    def update_branch_head(self, branch: Branch, milestone_id: str, updated_by: str = "") -> Branch:
        branch.update_head(milestone_id, updated_by=updated_by)
        repo = self.repos.get("branch")
        if repo:
            repo.update(branch)
        if self.uow:
            self.uow.commit()
        return branch

    def build_change_set(self, project_id: str, branch_id: str, base_milestone_id: str, target_milestone_id: Optional[str] = None) -> ChangeSet:
        change_set = ChangeSet(
            project_id=project_id,
            branch_id=branch_id,
            base_milestone_id=base_milestone_id,
            target_milestone_id=target_milestone_id,
        )
        repo = self.repos.get("change_set")
        if repo:
            repo.add(change_set)
        if self.uow:
            self.uow.commit()
        return change_set

    def add_change(self, change_set: ChangeSet, requirement_id: str, change_type: ChangeType, before=None, after=None, fields_changed=None, reason: str = "") -> RequirementChange:
        change = RequirementChange(
            requirement_id=requirement_id,
            change_type=change_type,
            before=before,
            after=after,
            fields_changed=fields_changed or [],
            reason=reason,
        )
        change_set.add_change(change)
        repo = self.repos.get("change_set")
        if repo:
            repo.update(change_set)
        if self.uow:
            self.uow.commit()
        return change
