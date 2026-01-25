"""需求应用服务"""
from __future__ import annotations
from typing import List, Optional

from .base_service import AppService
from ..domain.requirement import Requirement
from ..domain.requirement_tree import RequirementTree
from ..domain.enums import RequirementStatus


class RequirementService(AppService):
    """需求与树的用例服务"""

    def import_requirements(self, project_id: str, requirements: List[Requirement]) -> RequirementTree:
        tree = RequirementTree(project_id=project_id)
        ok, errors = tree.build_tree(requirements)
        if not ok:
            raise ValueError("; ".join(errors))
        repo = self.repos.get("requirement")
        if repo:
            for req in requirements:
                repo.add(req)
        if self.uow:
            self.uow.commit()
        return tree

    def create_requirement(self, requirement: Requirement) -> Requirement:
        repo = self.repos.get("requirement")
        if repo:
            repo.add(requirement)
        if self.uow:
            self.uow.commit()
        return requirement

    def update_requirement(self, requirement: Requirement, **kwargs) -> Requirement:
        requirement.update(**kwargs)
        repo = self.repos.get("requirement")
        if repo:
            repo.update(requirement)
        if self.uow:
            self.uow.commit()
        return requirement

    def delete_requirement(self, requirement: Requirement, deleted_by: str) -> Requirement:
        requirement.soft_delete(deleted_by=deleted_by)
        repo = self.repos.get("requirement")
        if repo:
            repo.update(requirement)
        if self.uow:
            self.uow.commit()
        return requirement

    def change_status(self, requirement: Requirement, status: RequirementStatus, updated_by: str = "") -> Requirement:
        requirement.update(status=status, updated_by=updated_by)
        repo = self.repos.get("requirement")
        if repo:
            repo.update(requirement)
        if self.uow:
            self.uow.commit()
        return requirement
