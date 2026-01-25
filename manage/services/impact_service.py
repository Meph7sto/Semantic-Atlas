"""影响分析应用服务"""
from __future__ import annotations
from typing import Optional, Dict, Any

from .base_service import AppService
from ..domain.impact_analysis import ImpactAnalysisService, ImpactReport
from ..domain.change_set import ChangeSet


class ImpactAppService(AppService):
    """影响分析用例服务"""

    def __init__(self, analyzer: ImpactAnalysisService, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.analyzer = analyzer

    def analyze(
        self,
        change_set: ChangeSet,
        project_id: str,
        base_milestone_id: str,
        generated_by: str = "",
        context: Optional[Dict[str, Any]] = None,
    ) -> ImpactReport:
        report = self.analyzer.analyze(
            change_set=change_set,
            project_id=project_id,
            base_milestone_id=base_milestone_id,
            generated_by=generated_by,
            context=context,
        )
        repo = self.repos.get("impact_report")
        if repo:
            repo.add(report)
        if self.uow:
            self.uow.commit()
        return report
