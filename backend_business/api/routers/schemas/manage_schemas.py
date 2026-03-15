"""
Manage API Pydantic 请求模型
对应历史蓝图: manage_bp (url_prefix="/api/v2/manage")
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

_ALLOWED_REQUIREMENT_STATUSES = (
    "draft",
    "under_review",
    "confirmed",
    "in_progress",
    "completed",
    "archived",
)
_ALLOWED_REQUIREMENT_STATUS_SET = set(_ALLOWED_REQUIREMENT_STATUSES)
_REQUIREMENT_STATUS_ALIASES = {"backlog": "draft"}


def normalize_requirement_status(status: Any, allow_none: bool = True) -> Optional[str]:
    if status is None:
        if allow_none:
            return None
        raise ValueError(
            f"status 必须是: {', '.join(_ALLOWED_REQUIREMENT_STATUSES)}"
        )

    text = str(status).strip()
    if not text:
        if allow_none:
            return None
        raise ValueError(
            f"status 必须是: {', '.join(_ALLOWED_REQUIREMENT_STATUSES)}"
        )

    normalized = _REQUIREMENT_STATUS_ALIASES.get(text.lower(), text.lower())
    if normalized in _ALLOWED_REQUIREMENT_STATUS_SET:
        return normalized

    raise ValueError(f"status 必须是: {', '.join(_ALLOWED_REQUIREMENT_STATUSES)}")


# ========================
# Project Schemas
# ========================

class CreateProjectRequest(BaseModel):
    """创建项目请求"""
    name: str = Field(min_length=1, description="项目名称")

    description: str = Field(default="", description="项目描述")


class UpdateProjectRequest(BaseModel):
    """更新项目请求"""
    name: Optional[str] = Field(None, min_length=1, description="项目名称")
    description: Optional[str] = Field(None, description="项目描述")
    current_session_id: Optional[str] = Field(
        None,
        description="当前会话ID（可设置为 null 以清空绑定）",
    )


# ========================
# Requirement Schemas
# ========================

class CreateRequirementRequest(BaseModel):
    """创建需求请求"""
    requirement_type: str = Field(min_length=1, description="需求类型")
    title: str = Field(min_length=1, description="需求标题")
    description: str = Field(default="", description="需求描述")
    status: str = Field(default="draft", description="需求状态")
    parent_id: Optional[str] = Field(None, description="父需求ID")
    order_index: int = Field(default=0, description="排序索引")
    priority: Optional[str] = Field(None, description="优先级: low/medium/high")
    assignee: Optional[str] = Field(None, description="指派人")
    tags: Optional[List[str]] = Field(default_factory=list, description="标签列表")
    due_date: Optional[str] = Field(None, description="截止日期")
    source_req_id: Optional[str] = Field(None, description="来源需求ID")
    source_level: Optional[str] = Field(None, description="来源层级")
    custom_fields: Optional[Dict[str, Any]] = Field(default_factory=dict, description="自定义字段")

    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        if v is not None and v not in ('low', 'medium', 'high'):
            raise ValueError('priority 必须是 low、medium 或 high')
        return v

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        return normalize_requirement_status(v, allow_none=False)


class UpdateRequirementRequest(BaseModel):
    """更新需求请求（支持部分字段）"""
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[str] = None
    assignee: Optional[str] = None
    tags: Optional[List[str]] = None
    due_date: Optional[str] = None
    custom_fields: Optional[Dict[str, Any]] = None
    order_index: Optional[int] = None

    @field_validator('priority')
    @classmethod
    def validate_priority(cls, v):
        if v is not None and v not in ('low', 'medium', 'high'):
            raise ValueError('priority 必须是 low、medium 或 high')
        return v

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        return normalize_requirement_status(v, allow_none=False)


class BulkUpdateStatusRequest(BaseModel):
    """批量更新需求状态请求"""
    req_ids: List[str] = Field(min_length=1, description="需求ID列表")
    status: str = Field(min_length=1, description="目标状态")

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        return normalize_requirement_status(v, allow_none=False)


class MoveRequirementRequest(BaseModel):
    """移动需求请求"""
    parent_id: Optional[str] = Field(None, description="新的父需求ID")
    order_index: int = Field(default=0, description="排序索引")


class ImportRequirementsRequest(BaseModel):
    """从 session 导入需求请求"""
    session_id: str = Field(min_length=1, description="会话ID")
    mapping_mode: str = Field(default="tree", description="映射模式: tree/flat")


# ========================
# Test Case Schemas
# ========================

class CreateTestCaseRequest(BaseModel):
    """创建测试用例请求"""
    title: str = Field(min_length=1, description="测试用例标题")
    description: str = Field(default="", description="测试用例描述")
    status: str = Field(default="draft", description="测试用例状态")
    source: str = Field(default="", description="测试用例来源")


class BindTestCaseRequest(BaseModel):
    """绑定测试用例请求"""
    test_case_id: str = Field(min_length=1, description="测试用例ID")
    link_type: str = Field(default="verification", description="链接类型")


# ========================
# Milestone Schemas
# ========================

class CreateMilestoneRequest(BaseModel):
    """创建里程碑请求"""
    name: str = Field(min_length=1, description="里程碑名称")
    message: str = Field(default="", description="里程碑消息")
    milestone_type: str = Field(default="regular", description="里程碑类型")
    is_baseline: bool = Field(default=False, description="是否为基线")
    sprint: Optional[str] = Field(None, description="Sprint标识")
    version: Optional[str] = Field(None, description="版本号")
    tags: Optional[List[str]] = Field(default_factory=list, description="标签列表")
    metadata: Optional[Dict[str, Any]] = Field(default_factory=dict, description="元数据")
    branch_name: Optional[str] = Field(None, description="分支名称")
    parent_milestone_id: Optional[str] = Field(None, description="父里程碑ID")


class CompareMilestonesRequest(BaseModel):
    """比较里程碑请求"""
    from_milestone_id: str = Field(min_length=1, description="源里程碑ID")
    to_milestone_id: str = Field(min_length=1, description="目标里程碑ID")


class AddMilestoneEdgeRequest(BaseModel):
    """添加里程碑边请求"""
    from_milestone_id: str = Field(min_length=1, description="源里程碑ID")
    to_milestone_id: str = Field(min_length=1, description="目标里程碑ID")
    relation_type: str = Field(default="activity", description="关系类型")
    message: str = Field(default="", description="消息")


# ========================
# Branch Schemas
# ========================

class CreateBranchRequest(BaseModel):
    """创建分支请求"""
    name: str = Field(min_length=1, description="分支名称")
    base_milestone_id: str = Field(min_length=1, description="基准里程碑ID")


class AddChangeSetRequest(BaseModel):
    """添加变更集请求"""
    change_type: str = Field(min_length=1, description="变更类型")
    requirement_id: Optional[str] = Field(None, description="需求ID")
    before_data: Optional[Dict[str, Any]] = Field(None, description="变更前数据")
    after_data: Optional[Dict[str, Any]] = Field(None, description="变更后数据")


class CreateMergeRequest(BaseModel):
    """创建合并请求请求"""
    target_milestone_id: str = Field(min_length=1, description="目标里程碑ID")


class MergeBranchesRequest(BaseModel):
    """合并分支请求"""
    source_branch: str = Field(min_length=1, description="源分支")
    target_branch: str = Field(min_length=1, description="目标分支")
    message: str = Field(default="", description="合并消息")
