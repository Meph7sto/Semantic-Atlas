"""
Vision API Pydantic 请求模型
"""

import json
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class VisionCallbackPayload(BaseModel):
    success: bool = True
    filename: Optional[str] = None
    speaker: str = Field(default="vision_agent", min_length=1)
    prompt: str = Field(default="", min_length=1)
    caption: str = Field(min_length=1)
    transcript_text: str = Field(min_length=1)

    @field_validator("speaker", "prompt", "caption", "transcript_text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("字段不能为空")
        return text


class VisionPreviewConfirmRequest(BaseModel):
    session_id: Optional[str] = None
    estimate_timestamps_if_missing: bool = True
    default_span_ms: int = Field(default=8000, ge=1)
    max_spans_returned: int = Field(default=200, ge=1)

    @field_validator("session_id")
    @classmethod
    def normalize_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None


class VisionAutoDLConfig(BaseModel):
    host: str = Field(min_length=1)
    port: int = Field(default=22, ge=1, le=65535)
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)
    workdir: str = Field(min_length=1)
    conda_env: str = Field(default="base", min_length=1)
    model_id: str = Field(min_length=1)
    service_port: int = Field(default=9000, ge=1, le=65535)
    startup_timeout_seconds: int = Field(default=600, ge=30, le=3600)

    @field_validator("host", "username", "password", "workdir", "conda_env", "model_id")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("字段不能为空")
        return text

    @classmethod
    def from_json(cls, raw_value: str) -> "VisionAutoDLConfig":
        try:
            payload = json.loads(raw_value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"AutoDL 配置 JSON 解析失败: {exc.msg}") from exc
        if not isinstance(payload, dict):
            raise ValueError("AutoDL 配置必须是对象")
        return cls(**payload)
