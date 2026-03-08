from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, File, Form, Header, HTTPException, UploadFile

from core.config import settings
from services.asr_service import asr_service

router = APIRouter(prefix="/asr", tags=["asr"])
logger = logging.getLogger(__name__)


@router.get("/health")
def asr_health():
    return asr_service.health()


def _check_token(authorization: str | None) -> None:
    configured = settings.ASR_SERVICE_TOKEN.strip()
    if not configured:
        return
    token = (authorization or "").strip()
    expected = f"Bearer {configured}"
    if token != expected:
        raise HTTPException(status_code=401, detail="invalid asr service token")


@router.post("/warmup")
def asr_warmup():
    try:
        asr_service.warmup()
        return {"success": True, **asr_service.health()}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@router.post("/transcribe")
async def transcribe(
    file: UploadFile = File(...),
    session_id: str = Form(default=""),
    attempt_no: str = Form(default=""),
    authorization: str | None = Header(default=None),
):
    _check_token(authorization)
    if file is None:
        raise HTTPException(status_code=400, detail="file is required")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="file is empty")

    try:
        result = asr_service.transcribe(
            file_bytes=file_bytes,
            filename=file.filename or "audio",
            content_type=file.content_type or "application/octet-stream",
        )
    except Exception as exc:
        logger.exception(
            "asr transcribe failed filename=%s content_type=%s size=%s",
            file.filename,
            file.content_type,
            len(file_bytes),
        )
        raise HTTPException(status_code=500, detail=f"{type(exc).__name__}: {exc}")

    return {
        "remote_request_id": uuid.uuid4().hex,
        "session_id": session_id or None,
        "attempt_no": attempt_no or None,
        "raw_out": result.get("raw_out", ""),
        "metadata": result.get("metadata", {}),
        "error": None,
    }
