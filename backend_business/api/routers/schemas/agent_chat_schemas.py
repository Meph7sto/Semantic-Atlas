"""Schemas for requirement agent chat APIs."""

from __future__ import annotations

from typing import Literal
from typing import Optional

from pydantic import BaseModel, Field, field_validator


PromptPayloadFormat = Literal["json", "yaml", "markdown"]


class AgentChatSessionRequest(BaseModel):
    project_id: Optional[str] = Field(default=None)
    title: Optional[str] = Field(default=None, max_length=120)
    prompt_payload_format: Optional[PromptPayloadFormat] = Field(default=None)

    @field_validator("project_id", "title")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class AgentChatSessionUpdateRequest(BaseModel):
    title: Optional[str] = Field(default=None, max_length=120)
    prompt_payload_format: Optional[PromptPayloadFormat] = Field(default=None)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


class AgentChatMessageRequest(BaseModel):
    project_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    requirement_id: Optional[str] = Field(default=None)

    @field_validator("project_id", "message")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("字段不能为空")
        return text

    @field_validator("requirement_id")
    @classmethod
    def normalize_requirement_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None
