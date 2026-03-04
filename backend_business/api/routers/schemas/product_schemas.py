"""
Product API Pydantic 请求模型
对应历史蓝图: product_bp (url_prefix="/api/v2/product")
"""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, field_validator


# ========================
# Product Schemas
# ========================

class CreateProductRequest(BaseModel):
    """创建产品请求"""
    name: str = Field(min_length=1, description="产品名称")
    description: str = Field(default="", description="产品描述")
    roadmap: str = Field(default="", description="产品路线图")
    version: str = Field(default="", description="产品版本")
    tags: Optional[List[str]] = Field(default_factory=list, description="标签列表")


class UpdateProductRequest(BaseModel):
    """更新产品请求（支持部分字段）"""
    name: Optional[str] = Field(None, min_length=1, description="产品名称")
    description: Optional[str] = Field(None, description="产品描述")
    status: Optional[str] = Field(None, description="产品状态")
    roadmap: Optional[str] = Field(None, description="产品路线图")
    version: Optional[str] = Field(None, description="产品版本")
    tags: Optional[List[str]] = Field(None, description="标签列表")

    @field_validator('status')
    @classmethod
    def validate_status(cls, v):
        if v is not None and v not in ('active', 'archived'):
            raise ValueError('status 必须是 active 或 archived')
        return v


# ========================
# Product Member Schemas
# ========================

class AddMemberRequest(BaseModel):
    """添加产品成员请求"""
    user_id: str = Field(min_length=1, description="用户ID")
    role: str = Field(default="member", description="成员角色")

    @field_validator('role')
    @classmethod
    def validate_role(cls, v):
        if v not in ('owner', 'admin', 'member'):
            raise ValueError('role 必须是 owner、admin 或 member')
        return v


# ========================
# Product-Project Relation Schemas
# ========================

class CreateProjectUnderProductRequest(BaseModel):
    """在产品下创建项目请求"""
    name: str = Field(min_length=1, description="项目名称")
    description: str = Field(default="", description="项目描述")


class BindProjectRequest(BaseModel):
    """绑定/解绑项目到产品请求"""
    product_id: Optional[str] = Field(None, description="产品ID（null 表示解绑）")
