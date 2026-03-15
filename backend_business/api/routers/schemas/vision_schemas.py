"""
Vision API Pydantic 请求模型
"""

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
