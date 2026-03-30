"""
Requirements API Pydantic 请求模型
对应历史蓝图: requirements_bp
"""

from typing import Any, Literal

from pydantic import BaseModel, Field, StrictBool, field_validator


class ExtractRequirementsRequest(BaseModel):
    text: str = Field(min_length=1)
    chunk_size: int = Field(default=3600, ge=1)
    overlap: int = Field(default=500, ge=0)
    clean_model: str = Field(default="deepseek-reasoner", min_length=1)
    extract_model: str = Field(default="deepseek-reasoner", min_length=1)

    @field_validator("text", "clean_model", "extract_model")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("字段不能为空")
        return text


class ExtractL123Request(BaseModel):
    session_id: str = Field(min_length=1)
    context_run_id: str | None = None
    bundle_strategy: Literal["sequence", "graph"] = "sequence"
    anchor_strategy: Literal["all", "keyword", "informative"] = "informative"
    r: int = Field(default=2, ge=1)
    model: str = Field(default="deepseek-reasoner", min_length=1)
    use_toolcall: StrictBool = True
    adaptive_retry_r2: StrictBool | None = None
    max_spans_per_bundle: int | None = Field(default=None, ge=1)
    token_limit: int | None = Field(default=None, ge=1)
    top_m_2hop: int | None = Field(default=None, ge=1)
    keywords: list[str] | None = None
    history_aware: StrictBool = False
    reset_before_extract: StrictBool = True
    post_dedup: StrictBool = False
    dedup_with_llm: StrictBool = False
    dedup_auto_merge: StrictBool = False
    dedup_threshold: float | None = None
    dedup_max_concurrent: int = Field(default=5, ge=1, le=10)
    pairwise_dedup: StrictBool = False
    pairwise_auto_apply: StrictBool = False
    pairwise_max_pairs: int | None = Field(default=None, ge=1, le=5000)
    enable_parallel_windows: StrictBool = False
    max_concurrent_windows: int = Field(default=5, ge=1, le=10)
    planner_connect_timeout_seconds: float | None = Field(default=None, ge=0.1, le=600)
    planner_read_timeout_seconds: float | None = Field(default=None, ge=0.1, le=7200)
    planner_max_retries: int | None = Field(default=None, ge=0, le=5)

    @field_validator("session_id", "model")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("字段不能为空")
        return text

    @field_validator("context_run_id")
    @classmethod
    def normalize_context_run_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None

    @field_validator("keywords")
    @classmethod
    def normalize_keywords(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return None
        normalized = [item.strip() for item in value if item and item.strip()]
        return normalized or None


class L4TopRequirementItem(BaseModel):
    id: str = Field(min_length=1)
    text: str = Field(min_length=1)

    @field_validator("id", "text")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("字段不能为空")
        return text


class GenerateL4RequirementsRequest(BaseModel):
    session_id: str = Field(min_length=1)
    requirements: list[L4TopRequirementItem] = Field(min_length=1)
    config: dict[str, Any] = Field(default_factory=dict)
    model: str | None = None
    force_regenerate: StrictBool = False

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("session_id 不能为空")
        return text

    @field_validator("model")
    @classmethod
    def normalize_model(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None
