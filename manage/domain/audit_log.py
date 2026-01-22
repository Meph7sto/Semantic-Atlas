"""审计日志模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import uuid4

from .enums import AuditAction


@dataclass
class AuditLog:
    """审计日志"""
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    actor: str = ""
    action: AuditAction = AuditAction.CREATE
    entity_type: str = ""  # TODO: 统一实体类型枚举
    entity_id: str = ""
    detail: Dict[str, Any] = field(default_factory=dict)
    correlation_id: Optional[str] = None  # 关联请求/链路ID
    created_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "actor": self.actor,
            "action": self.action.value,
            "entity_type": self.entity_type,
            "entity_id": self.entity_id,
            "detail": self.detail,
            "correlation_id": self.correlation_id,
            "created_at": self.created_at.isoformat(),
        }
