from __future__ import annotations

import json
from typing import Any, Optional

from psycopg2.extras import RealDictCursor


class TranscriptionSessionMixin:
    def create_transcription_session(
        self,
        session_id: str,
        user_id: str,
        source_filename: str,
        source_extension: str,
        source_content_type: str,
        source_size_bytes: int,
        source_storage_path: str,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO transcription_sessions(
                        session_id,
                        user_id,
                        status,
                        source_filename,
                        source_extension,
                        source_content_type,
                        source_size_bytes,
                        source_storage_path
                    )
                    VALUES(%s,%s,'queued',%s,%s,%s,%s,%s)
                    RETURNING
                        session_id, user_id, status, source_filename, source_extension,
                        source_content_type, source_size_bytes, source_storage_path,
                        remote_request_id, transcript_text, transcript_segments, transcript_metadata,
                        error_code, error_message, attempt_count,
                        started_at::text AS started_at, completed_at::text AS completed_at,
                        created_at::text AS created_at, updated_at::text AS updated_at
                    """,
                    (
                        session_id,
                        user_id,
                        source_filename,
                        source_extension,
                        source_content_type,
                        int(source_size_bytes),
                        source_storage_path,
                    ),
                )
                row = cur.fetchone() or {}
        return dict(row)

    def start_transcription_attempt(
        self,
        session_id: str,
        remote_request_id: Optional[str] = None,
    ) -> dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT attempt_count
                    FROM transcription_sessions
                    WHERE session_id = %s
                    FOR UPDATE
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError("transcription session not found")

                attempt_no = int(row["attempt_count"]) + 1

                cur.execute(
                    """
                    UPDATE transcription_sessions
                    SET status = 'running',
                        attempt_count = %s,
                        remote_request_id = COALESCE(%s, remote_request_id),
                        error_code = NULL,
                        error_message = NULL,
                        started_at = NOW(),
                        completed_at = NULL,
                        updated_at = NOW()
                    WHERE session_id = %s
                    """,
                    (attempt_no, remote_request_id, session_id),
                )
                cur.execute(
                    """
                    INSERT INTO transcription_attempts(
                        session_id, attempt_no, status, remote_request_id, started_at
                    )
                    VALUES(%s, %s, 'running', %s, NOW())
                    ON CONFLICT(session_id, attempt_no) DO UPDATE
                    SET status = EXCLUDED.status,
                        remote_request_id = EXCLUDED.remote_request_id,
                        started_at = EXCLUDED.started_at
                    """,
                    (session_id, attempt_no, remote_request_id),
                )
        return {"session_id": session_id, "attempt_no": attempt_no}

    def queue_transcription_retry(self, session_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE transcription_sessions
                    SET status = 'queued',
                        error_code = NULL,
                        error_message = NULL,
                        completed_at = NULL,
                        updated_at = NOW()
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )

    def complete_transcription_session(
        self,
        session_id: str,
        attempt_no: int,
        transcript_text: str,
        transcript_segments: list[dict[str, Any]],
        transcript_metadata: dict[str, Any],
        remote_request_id: Optional[str] = None,
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE transcription_sessions
                    SET status = 'succeeded',
                        transcript_text = %s,
                        transcript_segments = %s::jsonb,
                        transcript_metadata = %s::jsonb,
                        remote_request_id = COALESCE(%s, remote_request_id),
                        error_code = NULL,
                        error_message = NULL,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE session_id = %s
                    """,
                    (
                        transcript_text,
                        json.dumps(transcript_segments, ensure_ascii=False),
                        json.dumps(transcript_metadata, ensure_ascii=False),
                        remote_request_id,
                        session_id,
                    ),
                )
                cur.execute(
                    """
                    UPDATE transcription_attempts
                    SET status = 'succeeded',
                        remote_request_id = COALESCE(%s, remote_request_id),
                        completed_at = NOW(),
                        metadata = %s::jsonb
                    WHERE session_id = %s AND attempt_no = %s
                    """,
                    (
                        remote_request_id,
                        json.dumps(
                            {"text_length": len(transcript_text)},
                            ensure_ascii=False,
                        ),
                        session_id,
                        int(attempt_no),
                    ),
                )

    def fail_transcription_session(
        self,
        session_id: str,
        attempt_no: int,
        status: str,
        error_code: str,
        error_message: str,
        remote_request_id: Optional[str] = None,
    ) -> None:
        if status not in {"failed", "timeout"}:
            status = "failed"
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE transcription_sessions
                    SET status = %s,
                        remote_request_id = COALESCE(%s, remote_request_id),
                        error_code = %s,
                        error_message = %s,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE session_id = %s
                    """,
                    (
                        status,
                        remote_request_id,
                        error_code[:100],
                        error_message[:1000],
                        session_id,
                    ),
                )
                cur.execute(
                    """
                    UPDATE transcription_attempts
                    SET status = %s,
                        remote_request_id = COALESCE(%s, remote_request_id),
                        error_code = %s,
                        error_message = %s,
                        completed_at = NOW()
                    WHERE session_id = %s AND attempt_no = %s
                    """,
                    (
                        status,
                        remote_request_id,
                        error_code[:100],
                        error_message[:1000],
                        session_id,
                        int(attempt_no),
                    ),
                )

    def get_transcription_session(
        self,
        session_id: str,
        user_id: str,
    ) -> Optional[dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        session_id, user_id, status, source_filename, source_extension,
                        source_content_type, source_size_bytes, source_storage_path,
                        remote_request_id, transcript_text, transcript_segments, transcript_metadata,
                        error_code, error_message, attempt_count,
                        started_at::text AS started_at, completed_at::text AS completed_at,
                        created_at::text AS created_at, updated_at::text AS updated_at
                    FROM transcription_sessions
                    WHERE session_id = %s AND user_id = %s
                    """,
                    (session_id, user_id),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def list_transcription_sessions(
        self,
        user_id: str,
        page: int = 1,
        per_page: int = 20,
    ) -> dict[str, Any]:
        page = max(1, int(page))
        per_page = max(1, min(100, int(per_page)))
        offset = (page - 1) * per_page
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT COUNT(1) AS c FROM transcription_sessions WHERE user_id = %s",
                    (user_id,),
                )
                total = int((cur.fetchone() or {}).get("c", 0))
                cur.execute(
                    """
                    SELECT
                        session_id, status, source_filename, source_extension, source_size_bytes,
                        remote_request_id, transcript_metadata,
                        attempt_count, error_code, error_message,
                        created_at::text AS created_at, updated_at::text AS updated_at,
                        completed_at::text AS completed_at
                    FROM transcription_sessions
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    (user_id, per_page, offset),
                )
                rows = [dict(r) for r in cur.fetchall()]
        return {
            "items": rows,
            "total": total,
            "page": page,
            "per_page": per_page,
            "pages": (total + per_page - 1) // per_page,
        }
