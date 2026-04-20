"""Requirement change analysis request schemas."""

from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend_business.api.routers.schemas.manage_schemas import (
    normalize_requirement_status,
)
from backend_business.services.requirements_manage_service import normalize_priority


class RequirementChangePatch(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, description="变更后的标题")
    description: Optional[str] = Field(default=None, description="变更后的描述")
    tags: Optional[List[str]] = Field(default=None, description="变更后的标签")
    priority: Optional[str] = Field(default=None, description="变更后的优先级")
    status: Optional[str] = Field(default=None, description="变更后的状态")

    @field_validator("priority")
    @classmethod
    def validate_priority(cls, value):
        return normalize_priority(value, allow_none=True)

    @field_validator("status")
    @classmethod
    def validate_status(cls, value):
        return normalize_requirement_status(value, allow_none=True)


class AnalyzeRequirementChangeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1, description="项目ID")
    requirement_id: str = Field(min_length=1, description="需求ID")
    changes: RequirementChangePatch = Field(default_factory=RequirementChangePatch)
