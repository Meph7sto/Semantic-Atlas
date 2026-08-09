from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, UploadFile
from fastapi.responses import Response
from werkzeug.utils import secure_filename

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.asr_schemas import (
    CreateSessionResponse,
    RetrySessionResponse,
    SessionDetailResponse,
    SessionListResponse,
)
from backend_business.config import settings
from backend_business.services.asr_orchestrator import asr_orchestrator
from backend_business.services.db_service import db_service

router = APIRouter(prefix="/api/v2/asr", tags=["asr"])

PCA_DEMO_TRANSCRIPT_PATH = Path(
    "F:/xwechat_files/wxid_mqr3bqj6oqfw22_8ad5/msg/file/2026-08/"
    "demo_PCA输液泵需求调研会议记录.txt"
)


def _require_db():
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)
    return db_service


def _user_upload_dir(user_id: str) -> str:
    path = os.path.join(settings.UPLOAD_FOLDER, "asr", user_id)
    os.makedirs(path, exist_ok=True)
    return path


def _safe_name(filename: str) -> str:
    safe = secure_filename(filename or "")
    if not safe:
        safe = "media"
    return safe


def _read_text_file(path: Path) -> str:
    for encoding in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return path.read_text(encoding="utf-8", errors="ignore")


def _load_pca_demo_transcript() -> str:
    configured_path = Path(
        os.environ.get("PCA_DEMO_TRANSCRIPT_PATH", str(PCA_DEMO_TRANSCRIPT_PATH))
    )
    if not configured_path.exists():
        raise ErrorResponse(f"PCA演示转写文本不存在: {configured_path}", 500)
    text = _read_text_file(configured_path).strip()
    if not text:
        raise ErrorResponse("PCA演示转写文本为空", 500)
    return text


@router.get("/health")
def asr_health(current_user: dict = Depends(get_current_user)):
    status = asr_orchestrator.health()
    return {"available": bool(status.get("available")), **status}


@router.post("/sessions", response_model=CreateSessionResponse)
async def create_transcription_session(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    demo: str = Query(default=""),
    current_user: dict = Depends(get_current_user),
):
    db = _require_db()

    user_id = str(current_user["user_id"])
    source_filename = _safe_name(file.filename or "")
    content = await file.read()
    source_size_bytes = len(content)
    source_extension = asr_orchestrator.validate_upload(
        source_filename, source_size_bytes
    )

    user_dir = _user_upload_dir(user_id)
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    suffix = uuid.uuid4().hex[:10]
    storage_filename = f"{ts}_{suffix}_{source_filename}"
    storage_path = os.path.join(user_dir, storage_filename)
    with open(storage_path, "wb") as fp:
        fp.write(content)

    session_id = f"asr_{uuid.uuid4().hex}"
    created = db.create_transcription_session(
        session_id=session_id,
        user_id=user_id,
        source_filename=source_filename,
        source_extension=source_extension,
        source_content_type=file.content_type or "application/octet-stream",
        source_size_bytes=source_size_bytes,
        source_storage_path=storage_path,
    )

    if demo.strip().lower() == "pca":
        transcript_text = _load_pca_demo_transcript()
        attempt = db.start_transcription_attempt(
            session_id=session_id,
            remote_request_id="pca-demo-transcript",
        )
        db.complete_transcription_session(
            session_id=session_id,
            attempt_no=int(attempt["attempt_no"]),
            transcript_text=transcript_text,
            transcript_segments=[],
            transcript_metadata={
                "source": "pca_demo_audio_transcription",
                "transcript_path": str(
                    os.environ.get(
                        "PCA_DEMO_TRANSCRIPT_PATH", str(PCA_DEMO_TRANSCRIPT_PATH)
                    )
                ),
                "uploaded_filename": source_filename,
                "text_length": len(transcript_text),
            },
            remote_request_id="pca-demo-transcript",
        )
        refreshed = db.get_transcription_session(
            session_id=session_id,
            user_id=user_id,
        )
        return refreshed or {**created, "status": "succeeded"}

    asr_orchestrator.ensure_available_or_raise()
    background_tasks.add_task(
        asr_orchestrator.process_session,
        session_id,
        storage_path,
        source_filename,
        file.content_type or "application/octet-stream",
    )
    return created


@router.get("/sessions", response_model=SessionListResponse)
def list_transcription_sessions(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    db = _require_db()
    return db.list_transcription_sessions(
        user_id=str(current_user["user_id"]),
        page=page,
        per_page=per_page,
    )


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
def get_transcription_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    db = _require_db()
    row = db.get_transcription_session(
        session_id=session_id.strip(),
        user_id=str(current_user["user_id"]),
    )
    if not row:
        raise ErrorResponse("会话不存在", 404)
    return row


@router.post("/sessions/{session_id}/retry", response_model=RetrySessionResponse)
def retry_transcription_session(
    session_id: str,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    db = _require_db()
    asr_orchestrator.ensure_available_or_raise()

    row = db.get_transcription_session(
        session_id=session_id.strip(),
        user_id=str(current_user["user_id"]),
    )
    if not row:
        raise ErrorResponse("会话不存在", 404)
    if row["status"] not in {"failed", "timeout"}:
        raise ErrorResponse("仅失败或超时会话可重试", 409)

    source_path = str(row.get("source_storage_path") or "")
    if not source_path or not os.path.exists(source_path):
        raise ErrorResponse("原始文件不存在，无法重试", 409)

    db.queue_transcription_retry(session_id=row["session_id"])
    background_tasks.add_task(
        asr_orchestrator.process_session,
        row["session_id"],
        source_path,
        row["source_filename"],
        row.get("source_content_type") or "application/octet-stream",
    )
    return {
        "session_id": row["session_id"],
        "status": "queued",
        "message": "retry queued",
    }


@router.get("/sessions/{session_id}/export")
def export_transcription_session(
    session_id: str,
    format: Literal["txt", "json"] = Query(default="txt"),
    current_user: dict = Depends(get_current_user),
):
    db = _require_db()
    row = db.get_transcription_session(
        session_id=session_id.strip(),
        user_id=str(current_user["user_id"]),
    )
    if not row:
        raise ErrorResponse("会话不存在", 404)
    if row["status"] != "succeeded":
        raise ErrorResponse("转写结果尚未就绪，无法导出", 409)

    filename_base = f"{row['session_id']}_transcript"
    raw_out = row.get("transcript_text") or ""

    if format == "json":
        payload = json.dumps(
            {
                "session_id": row["session_id"],
                "status": row["status"],
                "raw_out": raw_out,
            },
            ensure_ascii=False,
            indent=2,
        ).encode("utf-8")
        return Response(
            content=payload,
            media_type="application/json; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="{filename_base}.json"'
            },
        )

    return Response(
        content=raw_out.encode("utf-8"),
        media_type="text/plain; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename_base}.txt"'},
    )
