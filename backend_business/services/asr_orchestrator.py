from __future__ import annotations

import logging
import os
import time
from typing import Any, Optional

import httpx

from backend_business.api.http.errors import ErrorResponse
from backend_business.config import settings
from backend_business.services.db_service import db_service

logger = logging.getLogger(__name__)


class ASROrchestrator:
    def __init__(self):
        raw = str(settings.ASR_ALLOWED_EXTENSIONS or "")
        self.allowed_extensions = {
            item.strip().lower().lstrip(".")
            for item in raw.split(",")
            if item.strip()
        }
        self.max_upload_bytes = int(settings.ASR_MAX_UPLOAD_MB) * 1024 * 1024

    def _compose_remote_url(self) -> str:
        return (
            f"{settings.ASR_REMOTE_BASE_URL.rstrip('/')}"
            f"{settings.ASR_REMOTE_TRANSCRIBE_PATH}"
        )

    def _compose_health_url(self) -> str:
        return (
            f"{settings.ASR_REMOTE_BASE_URL.rstrip('/')}"
            f"{settings.ASR_REMOTE_HEALTH_PATH}"
        )

    def validate_upload(self, filename: str, content_size: int) -> str:
        if content_size <= 0:
            raise ErrorResponse("上传文件不能为空", 400)
        if content_size > self.max_upload_bytes:
            raise ErrorResponse(
                f"上传文件过大，最大允许 {settings.ASR_MAX_UPLOAD_MB}MB",
                413,
            )
        suffix = (filename.rsplit(".", 1)[-1].lower() if "." in filename else "").strip()
        if suffix not in self.allowed_extensions:
            allowed = ", ".join(sorted(self.allowed_extensions))
            raise ErrorResponse(f"不支持的文件类型，允许: {allowed}", 400)
        return suffix

    def health(self) -> dict[str, Any]:
        if not settings.ASR_REMOTE_BASE_URL:
            return {
                "available": False,
                "detail": "ASR_REMOTE_BASE_URL 未配置",
                "remote": None,
            }

        headers: dict[str, str] = {}
        if settings.ASR_REMOTE_AUTH_TOKEN:
            headers["Authorization"] = f"Bearer {settings.ASR_REMOTE_AUTH_TOKEN}"

        try:
            with httpx.Client(timeout=5.0) as client:
                resp = client.get(self._compose_health_url(), headers=headers)
            if resp.status_code != 200:
                return {
                    "available": False,
                    "detail": f"远端健康检查失败: HTTP {resp.status_code}",
                    "remote": self._compose_health_url(),
                }
            payload = resp.json() if resp.content else {}
            return {
                "available": bool(payload.get("available", True)),
                "detail": payload.get("detail", "ok"),
                "remote": self._compose_health_url(),
            }
        except Exception as exc:
            return {
                "available": False,
                "detail": f"远端健康检查异常: {exc}",
                "remote": self._compose_health_url(),
            }

    def ensure_available_or_raise(self) -> None:
        status = self.health()
        if not status.get("available"):
            raise ErrorResponse(
                f"远端 ASR 服务不可用: {status.get('detail', 'unknown')}",
                503,
            )

    def process_session(
        self,
        session_id: str,
        file_path: str,
        source_filename: str,
        source_content_type: str,
    ) -> None:
        if db_service is None:
            logger.error("db_service not initialized, skip ASR processing")
            return
        if not os.path.exists(file_path):
            db_service.fail_transcription_session(
                session_id=session_id,
                attempt_no=1,
                status="failed",
                error_code="SOURCE_FILE_NOT_FOUND",
                error_message=f"source file not found: {file_path}",
            )
            return

        remote_request_id: Optional[str] = None
        attempt = db_service.start_transcription_attempt(session_id=session_id)
        attempt_no = int(attempt["attempt_no"])

        headers: dict[str, str] = {}
        if settings.ASR_REMOTE_AUTH_TOKEN:
            headers["Authorization"] = f"Bearer {settings.ASR_REMOTE_AUTH_TOKEN}"

        logger.info(
            "asr session dispatch start session_id=%s attempt_no=%s remote=%s",
            session_id,
            attempt_no,
            self._compose_remote_url(),
        )
        started_at = time.time()

        try:
            timeout = settings.ASR_REMOTE_TIMEOUT_SECONDS
            with open(file_path, "rb") as fp, httpx.Client(timeout=timeout) as client:
                resp = client.post(
                    self._compose_remote_url(),
                    data={"session_id": session_id, "attempt_no": str(attempt_no)},
                    files={
                        "file": (
                            source_filename,
                            fp,
                            source_content_type or "application/octet-stream",
                        )
                    },
                    headers=headers,
                )

            if resp.status_code != 200:
                msg = (resp.text or "").strip()[:1000]
                db_service.fail_transcription_session(
                    session_id=session_id,
                    attempt_no=attempt_no,
                    status="failed",
                    error_code=f"REMOTE_HTTP_{resp.status_code}",
                    error_message=msg or "remote transcribe failed",
                )
                logger.warning(
                    "asr session failed session_id=%s attempt_no=%s remote_request_id=%s failure_reason=%s latency=%.3f",
                    session_id,
                    attempt_no,
                    remote_request_id,
                    f"HTTP_{resp.status_code}",
                    time.time() - started_at,
                )
                return

            payload = resp.json()
            remote_request_id = str(payload.get("remote_request_id") or "") or None
            text = str(payload.get("text") or "").strip()
            segments = payload.get("segments") or []
            metadata = payload.get("metadata") or {}
            if not isinstance(segments, list):
                segments = []
            if not isinstance(metadata, dict):
                metadata = {}

            if not text:
                db_service.fail_transcription_session(
                    session_id=session_id,
                    attempt_no=attempt_no,
                    status="failed",
                    error_code="EMPTY_TRANSCRIPT",
                    error_message="远端未返回有效转写文本",
                    remote_request_id=remote_request_id,
                )
                return

            db_service.complete_transcription_session(
                session_id=session_id,
                attempt_no=attempt_no,
                transcript_text=text,
                transcript_segments=segments,
                transcript_metadata=metadata,
                remote_request_id=remote_request_id,
            )
            logger.info(
                "asr session succeeded session_id=%s attempt_no=%s remote_request_id=%s text_length=%s latency=%.3f",
                session_id,
                attempt_no,
                remote_request_id,
                len(text),
                time.time() - started_at,
            )
        except httpx.TimeoutException as exc:
            db_service.fail_transcription_session(
                session_id=session_id,
                attempt_no=attempt_no,
                status="timeout",
                error_code="REMOTE_TIMEOUT",
                error_message=str(exc),
                remote_request_id=remote_request_id,
            )
            logger.warning(
                "asr session timeout session_id=%s attempt_no=%s remote_request_id=%s failure_reason=%s latency=%.3f",
                session_id,
                attempt_no,
                remote_request_id,
                "REMOTE_TIMEOUT",
                time.time() - started_at,
            )
        except Exception as exc:
            db_service.fail_transcription_session(
                session_id=session_id,
                attempt_no=attempt_no,
                status="failed",
                error_code="REMOTE_EXCEPTION",
                error_message=str(exc),
                remote_request_id=remote_request_id,
            )
            logger.exception(
                "asr session exception session_id=%s attempt_no=%s remote_request_id=%s failure_reason=%s latency=%.3f",
                session_id,
                attempt_no,
                remote_request_id,
                "REMOTE_EXCEPTION",
                time.time() - started_at,
            )


asr_orchestrator = ASROrchestrator()
