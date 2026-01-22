"""里程碑图应用服务"""
from __future__ import annotations
from typing import Optional, List

from .base_service import AppService
from ..domain.milestone_graph import MilestoneGraph
from ..domain.milestone import Milestone


class MilestoneGraphService(AppService):
    """里程碑图用例服务"""

    def add_milestone(self, graph: MilestoneGraph, milestone: Milestone, parent_ids: Optional[List[str]] = None, is_main: bool = True):
        ok, error = graph.add_milestone(milestone, parent_ids=parent_ids, is_main=is_main)
        if not ok:
            raise ValueError(error)
        repo = self.repos.get("milestone_graph")
        if repo:
            repo.update(graph)
        if self.uow:
            self.uow.commit()
        return graph

    def create_branch(self, graph: MilestoneGraph, branch_name: str, milestone_id: str):
        ok, error = graph.create_branch(branch_name, milestone_id)
        if not ok:
            raise ValueError(error)
        repo = self.repos.get("milestone_graph")
        if repo:
            repo.update(graph)
        if self.uow:
            self.uow.commit()
        return graph

    def update_branch(self, graph: MilestoneGraph, branch_name: str, milestone_id: str):
        ok, error = graph.update_branch(branch_name, milestone_id)
        if not ok:
            raise ValueError(error)
        repo = self.repos.get("milestone_graph")
        if repo:
            repo.update(graph)
        if self.uow:
            self.uow.commit()
        return graph
