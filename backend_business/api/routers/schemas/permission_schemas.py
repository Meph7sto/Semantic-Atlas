"""
Permission API Pydantic 请求模型
对应历史蓝图: permission_bp
"""

from typing import Optional

from pydantic import BaseModel, Field


# ========================
# 项目成员管理
# ========================

class AddProjectMemberRequest(BaseModel):
    """添加项目成员请求"""
    user_id: str = Field(min_length=1)
    member_roles: list[str] = Field(default_factory=list)  # 可选：同时分配角色


class SetUserRolesRequest(BaseModel):
    """设置用户角色请求（全量替换）"""
    roles: list[str]


# ========================
# 评审管理
# ========================

class CreateReviewRequest(BaseModel):
    """创建评审指派请求"""
    reviewer_id: str = Field(min_length=1)
    seq: int = 1
    comment: Optional[str] = None


class ApproveReviewRequest(BaseModel):
    """通过评审请求"""
    comment: Optional[str] = None


class RejectReviewRequest(BaseModel):
    """驳回评审请求"""
    comment: Optional[str] = None


# ========================
# 基线管理
# ========================

class CreateBaselineRequest(BaseModel):
    """创建基线请求"""
    version: str = Field(min_length=1)
    locked: bool = False


# ========================
# 变更请求管理
# ========================

class CreateChangeRequestRequest(BaseModel):
    """创建变更请求请求"""
    baseline_id: int = Field(gt=0)
    reason: str = Field(min_length=1)
    change_summary: str = Field(min_length=1)


class ApproveChangeRequestRequest(BaseModel):
    """批准变更请求请求"""
    review_comment: Optional[str] = None


class RejectChangeRequestRequest(BaseModel):
    """驳回变更请求请求"""
    review_comment: Optional[str] = None
