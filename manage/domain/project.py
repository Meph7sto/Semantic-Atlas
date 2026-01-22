"""项目模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional
from uuid import uuid4

from .enums import ProjectStatus


@dataclass
class Project:
    """项目实体"""
    id: str = field(default_factory=lambda: str(uuid4()))
    name: str = ""
    code: Optional[str] = None  # TODO: 项目标识/编号
    description: str = ""
    status: ProjectStatus = ProjectStatus.ACTIVE
    development_locked: bool = False  # baseline冻结期

    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_by: str = ""
    updated_at: datetime = field(default_factory=datetime.now)

    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("项目名称不能为空")

    def update_info(
        self,
        name: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[ProjectStatus] = None,
        updated_by: str = "",
        **kwargs: Any
    ) -> None:
        if name is not None:
            self.name = name
        if description is not None:
            self.description = description
        if status is not None:
            self.status = status

        self.updated_by = updated_by
        self.updated_at = datetime.now()
        for key, value in kwargs.items():
            self.metadata[key] = value

    def lock_development(self, reason: str = "") -> None:
        self.development_locked = True
        if reason:
            self.metadata["lock_reason"] = reason

    def unlock_development(self, reason: str = "") -> None:
        self.development_locked = False
        if reason:
            self.metadata["unlock_reason"] = reason

    def archive(self, archived_by: str = "") -> None:
        self.status = ProjectStatus.ARCHIVED
        self.updated_by = archived_by
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "code": self.code,
            "description": self.description,
            "status": self.status.value,
            "development_locked": self.development_locked,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Project":
        return cls(
            id=data.get("id", str(uuid4())),
            name=data["name"],
            code=data.get("code"),
            description=data.get("description", ""),
            status=ProjectStatus(data.get("status", "active")),
            development_locked=data.get("development_locked", False),
            created_by=data.get("created_by", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            updated_by=data.get("updated_by", ""),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(),
            metadata=data.get("metadata", {}),
        )
