"""
Analysis API Pydantic 请求模型
"""

from typing import Optional

from pydantic import BaseModel, Field, field_validator


class IngestOptions(BaseModel):
    estimate_timestamps_if_missing: bool = True
    default_span_ms: int = Field(default=8000, ge=1)
    max_spans_returned: int = Field(default=200, ge=1)


class IngestTranscriptRequest(BaseModel):
    transcript_text: str = Field(min_length=1)
    session_id: Optional[str] = None
    options: IngestOptions = Field(default_factory=IngestOptions)

    @field_validator("transcript_text")
    @classmethod
    def validate_transcript_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("transcript_text 不能为空")
        return text

    @field_validator("session_id")
    @classmethod
    def normalize_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        return text or None


class BuildContextOptions(BaseModel):
    window_size: int = Field(default=8, ge=1)
    step_size: int = Field(default=7, ge=1)
    tau: float = Field(default=0.6)
    top_k: int = Field(default=3, ge=1)
    max_edges_per_window: int = Field(default=24, ge=1)
    token_limit_per_bundle: int = Field(default=4000, ge=1)
    mock_llm: bool = False
    llm_model: Optional[str] = None
    use_thinking_mode: bool = False
    enable_parallel_windows: bool = False
    max_concurrent_windows: int = Field(default=5, ge=1)


class BuildContextRequest(BaseModel):
    session_id: str = Field(min_length=1)
    options: BuildContextOptions = Field(default_factory=BuildContextOptions)

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("session_id 不能为空")
        return text

