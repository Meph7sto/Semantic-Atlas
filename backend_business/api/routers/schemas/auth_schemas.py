"""
Auth API Pydantic 请求模型
对应 Flask blueprint: auth_bp
"""

import re
from typing import Optional

from pydantic import BaseModel, field_validator


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
