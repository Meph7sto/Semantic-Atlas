"""审计日志应用服务"""
from __future__ import annotations
from typing import Dict, Any

from .base_service import AppService
from ..domain.audit_log import AuditLog
from ..domain.enums import AuditAction


class AuditService(AppService):
    """审计日志用例服务"""

    def record(
        self,
        project_id: str,
        actor: str,
        action: AuditAction,
        entity_type: str,
        entity_id: str,
        detail: Dict[str, Any] | None = None,
        correlation_id: str | None = None,
    ) -> AuditLog:
        log = AuditLog(
            project_id=project_id,
            actor=actor,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            detail=detail or {},
            correlation_id=correlation_id,
        )
        repo = self.repos.get("audit_log")
        if repo:
            repo.add(log)
        if self.uow:
            self.uow.commit()
        return log
