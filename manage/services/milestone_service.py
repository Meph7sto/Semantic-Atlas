"""里程碑应用服务"""
from __future__ import annotations
from typing import List, Optional, Dict, Any

from .base_service import AppService
from ..domain.requirement import Requirement
from ..domain.milestone import Milestone, MilestoneService


class MilestoneAppService(AppService):
    """里程碑用例服务"""

    def create_milestone(
        self,
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
        milestone = MilestoneService.create_milestone(
            project_id=project_id,
            requirements=requirements,
            name=name,
            created_by=created_by,
            message=message,
            milestone_type=milestone_type,
            sprint=sprint,
            version=version,
            tags=tags,
            metadata=metadata,
        )
        repo = self.repos.get("milestone")
        if repo:
            repo.add(milestone)
        if self.uow:
            self.uow.commit()
        return milestone

    def create_baseline(
        self,
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
        milestone = MilestoneService.create_baseline(
            project_id=project_id,
            requirements=requirements,
            name=name,
            created_by=created_by,
            message=message,
            sprint=sprint,
            version=version,
            tags=tags,
            metadata=metadata,
        )
        repo = self.repos.get("milestone")
        if repo:
            repo.add(milestone)
        if self.uow:
            self.uow.commit()
        return milestone

    def compare(self, from_milestone: Milestone, to_milestone: Milestone):
        return MilestoneService.compare_milestones(from_milestone, to_milestone)
