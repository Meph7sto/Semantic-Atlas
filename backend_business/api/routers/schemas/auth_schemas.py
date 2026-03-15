"""
Auth API Pydantic 请求模型
对应历史蓝图: auth_bp
"""

import re
from typing import Optional

from pydantic import BaseModel, Field, field_validator

_STANDARD_LOGIN_ROLES = {"super_admin", "admin", "member", "viewer"}


class LoginRequest(BaseModel):
    """登录请求"""
    username: str
    password: str
    role: str = "member"  # 可选，用于 test 用户模拟不同角色

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        if not v:
            raise ValueError("用户名不能为空")
        return v

    @field_validator('password', mode='before')
    @classmethod
    def validate_password(cls, v):
        if not v:
            raise ValueError("密码不能为空")
        return v

    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        role = str(v or "").strip().lower()
        if role not in _STANDARD_LOGIN_ROLES:
            raise ValueError("无效的角色，必须是 super_admin、admin、member 或 viewer")
        return role


class RegisterRequest(BaseModel):
    """注册请求"""
    username: str
    password: str
    display_name: str
    role: str = "viewer"  # 前端可能传入，但会被强制改为 viewer
    external_type: Optional[str] = None

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("用户名不能为空")
        if not re.match(r'^[a-zA-Z0-9_-]+$', v):
            raise ValueError("用户名只能包含字母、数字、下划线和中划线")
        return v

    @field_validator('password', mode='before')
    @classmethod
    def validate_password(cls, v):
        if not v:
            raise ValueError("密码不能为空")
        if len(v) < 6:
            raise ValueError("密码长度不能少于 6 位")
        return v

    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("显示名称不能为空")
        return v


class ChangePasswordRequest(BaseModel):
    """修改密码请求"""
    old_password: str
    new_password: str

    @field_validator('old_password', mode='before')
    @classmethod
    def validate_old_password(cls, v):
        if not v:
            raise ValueError("请提供当前密码")
        return v

    @field_validator('new_password', mode='before')
    @classmethod
    def validate_new_password(cls, v):
        if not v:
            raise ValueError("请提供新密码")
        if len(v) < 6:
            raise ValueError("新密码长度不能少于 6 位")
        return v


class UpdateProfileRequest(BaseModel):
    """更新个人资料请求"""
    display_name: Optional[str] = None
    avatar_url: Optional[str] = None

    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v):
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("显示名称不能为空")
            if len(v) > 50:
                raise ValueError("显示名称不能超过 50 个字符")
        return v

    @field_validator('avatar_url')
    @classmethod
    def validate_avatar_url(cls, v):
        if v is not None and v.strip():
            if not v.startswith(("http://", "https://")):
                raise ValueError("头像 URL 必须以 http:// 或 https:// 开头")
            if len(v) > 500:
                raise ValueError("头像 URL 过长")
        return v


class CreateUserRequest(BaseModel):
    """创建用户请求（管理员）"""
    username: str
    password: str
    display_name: str
    role: str = "member"
    external_type: Optional[str] = None

    @field_validator('username')
    @classmethod
    def validate_username(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("用户名不能为空")
        return v

    @field_validator('password', mode='before')
    @classmethod
    def validate_password(cls, v):
        if not v:
            raise ValueError("密码不能为空")
        return v

    @field_validator('display_name')
    @classmethod
    def validate_display_name(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("显示名称不能为空")
        return v


class UpdateUserRequest(BaseModel):
    """更新用户请求（管理员）"""
    display_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


# ========================
# Registration Management Schemas
# ========================

class ApproveRegistrationRequest(BaseModel):
    """批准注册请求"""
    role: str  # admin, member, viewer
    external_type: Optional[str] = None  # CLIENT or CONTRACTOR

    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        if v not in ("admin", "member", "viewer"):
            raise ValueError("无效的角色，必须是 admin、member 或 viewer")
        return v

    @field_validator('external_type')
    @classmethod
    def validate_external_type(cls, v):
        if v is not None and v not in ("CLIENT", "CONTRACTOR"):
            raise ValueError("无效的外部身份类型")
        return v


class RejectRegistrationRequest(BaseModel):
    """拒绝注册请求"""
    reason: str

    @field_validator('reason')
    @classmethod
    def validate_reason(cls, v):
        v = v.strip()
        if not v:
            raise ValueError("拒绝原因不能为空")
        if len(v) > 500:
            raise ValueError("拒绝原因不能超过 500 个字符")
        return v


class RegistrationListItem(BaseModel):
    """注册列表项响应"""
    user_id: str
    username: str
    display_name: str
    external_type: Optional[str]
    avatar_url: Optional[str]
    created_at: str
    registration_status: str


class RegistrationDetailResponse(BaseModel):
    """注册详情响应"""
    user_id: str
    username: str
    display_name: str
    role: Optional[str]
    is_active: bool
    external_type: Optional[str]
    avatar_url: Optional[str]
    created_at: str
    registration_status: str
    rejection_reason: Optional[str]
    rejected_at: Optional[str]
    approved_at: Optional[str]
    approved_by: Optional[str]
    rejected_by: Optional[str]


class ProductScopeItem(BaseModel):
    """用户产品范围项"""
    product_id: str
    can_edit: bool = False

    @field_validator('product_id')
    @classmethod
    def validate_product_id(cls, v):
        value = v.strip()
        if not value:
            raise ValueError("product_id 不能为空")
        return value


class ProjectScopeItem(BaseModel):
    """用户项目范围项"""
    project_id: str
    can_edit: bool = False

    @field_validator('project_id')
    @classmethod
    def validate_project_id(cls, v):
        value = v.strip()
        if not value:
            raise ValueError("project_id 不能为空")
        return value


class UpdateUserScopesRequest(BaseModel):
    """更新用户可见范围请求（全量替换）"""
    product_scopes: list[ProductScopeItem] = Field(default_factory=list)
    project_scopes: list[ProjectScopeItem] = Field(default_factory=list)
