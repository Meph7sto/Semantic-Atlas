from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


TranscriptionStatus = Literal["queued", "running", "succeeded", "failed", "timeout"]


class CreateSessionResponse(BaseModel):
    session_id: str
    status: TranscriptionStatus
    source_filename: str
    source_extension: str
    source_size_bytes: int
    created_at: str


class SessionSummary(BaseModel):
    session_id: str
    status: TranscriptionStatus
    source_filename: str
    source_extension: str
    source_size_bytes: int
    remote_request_id: str | None = None
    transcript_metadata: dict[str, Any] | None = None
    attempt_count: int
    error_code: str | None = None
    error_message: str | None = None
    created_at: str
    updated_at: str
    completed_at: str | None = None


class SessionListResponse(BaseModel):
    items: list[SessionSummary]
    total: int
    page: int
    per_page: int
    pages: int


class SessionDetailResponse(BaseModel):
    session_id: str
    status: TranscriptionStatus
    source_filename: str
    source_extension: str
    source_content_type: str | None = None
    source_size_bytes: int
    transcript_text: str | None = None
    transcript_segments: list[dict[str, Any]] | None = None
    transcript_metadata: dict[str, Any] | None = None
    error_code: str | None = None
    error_message: str | None = None
    attempt_count: int
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str
    updated_at: str


class RetrySessionResponse(BaseModel):
    session_id: str
    status: TranscriptionStatus
    message: str = Field(default="retry queued")
