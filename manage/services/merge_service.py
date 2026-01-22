"""合并应用服务"""
from __future__ import annotations
from typing import List

from .base_service import AppService
from ..domain.merge import MergeRecord, MergeConflict
from ..domain.enums import MergeStatus, ConflictResolutionStrategy


class MergeService(AppService):
    """合并用例服务"""

    def create_merge_record(
        self,
        project_id: str,
        branch_id: str,
        base_milestone_id: str,
        source_milestone_id: str,
        target_milestone_id: str,
        created_by: str,
    ) -> MergeRecord:
        record = MergeRecord(
            project_id=project_id,
            branch_id=branch_id,
            base_milestone_id=base_milestone_id,
            source_milestone_id=source_milestone_id,
            target_milestone_id=target_milestone_id,
            created_by=created_by,
        )
        repo = self.repos.get("merge_record")
        if repo:
            repo.add(record)
        if self.uow:
            self.uow.commit()
        return record

    def mark_conflicts(self, record: MergeRecord, conflicts: List[MergeConflict]) -> MergeRecord:
        record.mark_conflicts(conflicts)
        repo = self.repos.get("merge_record")
        if repo:
            repo.update(record)
        if self.uow:
            self.uow.commit()
        return record

    def complete_merge(self, record: MergeRecord, result_milestone_id: str, merged_by: str) -> MergeRecord:
        record.complete_merge(result_milestone_id, merged_by)
        repo = self.repos.get("merge_record")
        if repo:
            repo.update(record)
        if self.uow:
            self.uow.commit()
        return record

    def set_resolution_strategy(self, record: MergeRecord, strategy: ConflictResolutionStrategy) -> MergeRecord:
        record.resolution_strategy = strategy
        repo = self.repos.get("merge_record")
        if repo:
            repo.update(record)
        if self.uow:
            self.uow.commit()
        return record
