"""测试用例/验收标准模型定义"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List
from uuid import uuid4

from .enums import TestCaseStatus


@dataclass
class TestCase:
    """测试用例"""
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    title: str = ""
    description: str = ""

    status: TestCaseStatus = TestCaseStatus.DRAFT
    version: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_by: str = ""
    updated_at: datetime = field(default_factory=datetime.now)

    custom_fields: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_id:
            raise ValueError("项目ID不能为空")
        if not self.title:
            raise ValueError("测试用例标题不能为空")

    def update(self, title: Optional[str] = None, description: Optional[str] = None, status: Optional[TestCaseStatus] = None, updated_by: str = "") -> None:
        if title is not None:
            self.title = title
        if description is not None:
            self.description = description
        if status is not None:
            self.status = status
        self.updated_by = updated_by
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "version": self.version,
            "tags": self.tags,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat(),
            "custom_fields": self.custom_fields,
        }


@dataclass
class AcceptanceCriteria:
    """验收标准"""
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    title: str = ""
    description: str = ""

    status: TestCaseStatus = TestCaseStatus.DRAFT
    version: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    updated_by: str = ""
    updated_at: datetime = field(default_factory=datetime.now)

    custom_fields: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_id:
            raise ValueError("项目ID不能为空")
        if not self.title:
            raise ValueError("验收标准标题不能为空")

    def update(self, title: Optional[str] = None, description: Optional[str] = None, status: Optional[TestCaseStatus] = None, updated_by: str = "") -> None:
        if title is not None:
            self.title = title
        if description is not None:
            self.description = description
        if status is not None:
            self.status = status
        self.updated_by = updated_by
        self.updated_at = datetime.now()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "version": self.version,
            "tags": self.tags,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_by": self.updated_by,
            "updated_at": self.updated_at.isoformat(),
            "custom_fields": self.custom_fields,
        }


@dataclass
class RequirementTestLink:
    """需求与测试/验收的绑定关系"""
    id: str = field(default_factory=lambda: str(uuid4()))
    project_id: str = ""
    requirement_id: str = ""
    test_case_id: Optional[str] = None
    acceptance_id: Optional[str] = None
    link_type: str = "test_case"  # test_case / acceptance

    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.project_id:
            raise ValueError("项目ID不能为空")
        if not self.requirement_id:
            raise ValueError("需求ID不能为空")
        if not (self.test_case_id or self.acceptance_id):
            raise ValueError("必须绑定测试用例或验收标准")

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "project_id": self.project_id,
            "requirement_id": self.requirement_id,
            "test_case_id": self.test_case_id,
            "acceptance_id": self.acceptance_id,
            "link_type": self.link_type,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "metadata": self.metadata,
        }
