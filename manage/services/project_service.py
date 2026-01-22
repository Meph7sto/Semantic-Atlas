"""项目应用服务"""
from __future__ import annotations
from typing import Optional, Dict, Any

from .base_service import AppService
from ..domain.project import Project


class ProjectService(AppService):
    """项目用例服务"""

    def create_project(
        self,
        name: str,
        created_by: str,
        description: str = "",
        code: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Project:
        project = Project(
            name=name,
            description=description,
            code=code,
            created_by=created_by,
            metadata=metadata or {},
        )
        repo = self.repos.get("project")
        if repo:
            repo.add(project)
        if self.uow:
            self.uow.commit()
        return project

    def update_project(self, project: Project, **kwargs: Any) -> Project:
        project.update_info(**kwargs)
        repo = self.repos.get("project")
        if repo:
            repo.update(project)
        if self.uow:
            self.uow.commit()
        return project

    def lock_development(self, project: Project, reason: str = "") -> Project:
        project.lock_development(reason)
        repo = self.repos.get("project")
        if repo:
            repo.update(project)
        if self.uow:
            self.uow.commit()
        return project

    def unlock_development(self, project: Project, reason: str = "") -> Project:
        project.unlock_development(reason)
        repo = self.repos.get("project")
        if repo:
            repo.update(project)
        if self.uow:
            self.uow.commit()
        return project
