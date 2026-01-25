"""需求模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Dict, Any
from uuid import uuid4

from .enums import RequirementType, RequirementStatus


@dataclass
class Requirement:
    """
    需求实体类

    表示系统中的一个需求节点（顶层需求/底层需求/任务）
    """

    # 核心标识
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""

    # 需求类型与状态
    requirement_type: RequirementType = RequirementType.LOW_LEVEL
    status: RequirementStatus = RequirementStatus.DRAFT

    # 基础信息（占位符，后续补充）
    title: str = ""
    description: str = ""
    priority: Optional[str] = None  # TODO: 优先级模型
    assignee: Optional[str] = None  # TODO: 负责人
    tags: Optional[list[str]] = None  # TODO: 标签
    due_date: Optional[str] = None  # TODO: 到期时间

    # 树结构关系
    parent_id: Optional[str] = None
    order: int = 0  # 同级排序

    # 元数据
    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_by: str = ""
    updated_at: datetime = field(default_factory=datetime.now)
    deleted: bool = False  # 软删除标记

    # 扩展字段（预留）
    custom_fields: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        if not self.title:
            raise ValueError("需求标题不能为空")
        if not self.project_id:
            raise ValueError("项目ID不能为空")

    def update(
        self,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[RequirementStatus] = None,
        updated_by: str = "",
        **kwargs: Any
    ) -> None:
        """更新需求信息"""
        if title is not None:
            self.title = title
        if description is not None:
            self.description = description
        if status is not None:
            self.status = status

        self.updated_by = updated_by
        self.updated_at = datetime.now()

        for key, value in kwargs.items():
            self.custom_fields[key] = value

    def soft_delete(self, deleted_by: str) -> None:
        """软删除需求"""
        self.deleted = True
        self.updated_by = deleted_by
        self.updated_at = datetime.now()

    def move_to(self, new_parent_id: Optional[str], new_order: int = 0) -> None:
        """移动需求到新父节点"""
        self.parent_id = new_parent_id
        self.order = new_order
        self.updated_at = datetime.now()

    def can_have_child(self, child_type: RequirementType) -> bool:
        """判断当前需求是否可以拥有指定类型的子需求"""
        rules = {
            RequirementType.TOP_LEVEL: [RequirementType.LOW_LEVEL, RequirementType.TASK],
            RequirementType.LOW_LEVEL: [RequirementType.TASK],
            RequirementType.TASK: []
        }
        return child_type in rules.get(self.requirement_type, [])

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于序列化）"""
        return {
            "id": self.id,
            "project_id": self.project_id,
            "requirement_type": self.requirement_type.value,
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "priority": self.priority,
            "assignee": self.assignee,
            "tags": self.tags,
            "due_date": self.due_date,
            "parent_id": self.parent_id,
            "order": self.order,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat(),
            "deleted": self.deleted,
            "custom_fields": self.custom_fields,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Requirement":
        """从字典创建需求对象"""
        return cls(
            id=data.get("id", str(uuid4())),
            project_id=data["project_id"],
            requirement_type=RequirementType(data.get("requirement_type", "low_level")),
            status=RequirementStatus(data.get("status", "draft")),
            title=data["title"],
            description=data.get("description", ""),
            priority=data.get("priority"),
            assignee=data.get("assignee"),
            tags=data.get("tags"),
            due_date=data.get("due_date"),
            parent_id=data.get("parent_id"),
            order=data.get("order", 0),
            created_by=data.get("created_by", ""),
            created_at=datetime.fromisoformat(data["created_at"]) if "created_at" in data else datetime.now(),
            updated_by=data.get("updated_by", ""),
            updated_at=datetime.fromisoformat(data["updated_at"]) if "updated_at" in data else datetime.now(),
            deleted=data.get("deleted", False),
            custom_fields=data.get("custom_fields", {}),
        )

    def __repr__(self) -> str:
        return f"<Requirement id={self.id} type={self.requirement_type.value} title='{self.title}'>"
