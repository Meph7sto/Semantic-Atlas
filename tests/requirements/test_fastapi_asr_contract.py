"""
FastAPI ASR business route contract tests.
"""


import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError


from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import asr


class _StubDB:
    def __init__(self):
        self.rows = {}

    def create_transcription_session(self, **kwargs):
        sid = kwargs["session_id"]
        row = {
            "session_id": sid,
            "status": "queued",
            "source_filename": kwargs["source_filename"],
            "source_extension": kwargs["source_extension"],
            "source_size_bytes": kwargs["source_size_bytes"],
            "source_content_type": kwargs["source_content_type"],
            "source_storage_path": kwargs["source_storage_path"],
            "attempt_count": 0,
            "transcript_text": None,
            "transcript_segments": [],
            "transcript_metadata": {},
            "error_code": None,
            "error_message": None,
            "created_at": "2026-03-06T00:00:00",
            "updated_at": "2026-03-06T00:00:00",
            "completed_at": None,
            "started_at": None,
            "user_id": kwargs["user_id"],
        }
        self.rows[sid] = row
        return row

    def list_transcription_sessions(self, user_id: str, page: int, per_page: int):
        items = [v for v in self.rows.values() if v["user_id"] == user_id]
        return {
            "items": items,
            "total": len(items),
            "page": page,
            "per_page": per_page,
            "pages": 1,
        }

    def get_transcription_session(self, session_id: str, user_id: str):
        row = self.rows.get(session_id)
        if not row or row["user_id"] != user_id:
            return None
        return row

    def queue_transcription_retry(self, session_id: str):
        self.rows[session_id]["status"] = "queued"


class _StubOrchestrator:
    def __init__(self):
        self.calls = []

    def health(self):
        return {"available": True, "detail": "ok", "remote": "http://remote/asr/health"}

    def ensure_available_or_raise(self):
        return

    def validate_upload(self, filename: str, content_size: int):
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in {"wav", "mp3", "m4a", "mp4"}:
            raise asr.ErrorResponse("不支持的文件类型", 400)
        return ext

    def process_session(self, *args, **kwargs):
        self.calls.append((args, kwargs))


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub_db = _StubDB()
    stub_orchestrator = _StubOrchestrator()

    monkeypatch.setattr(asr, "db_service", stub_db)
    monkeypatch.setattr(asr, "asr_orchestrator", stub_orchestrator)

    app = build_test_app(asr.router)
    app.dependency_overrides[get_current_user] = lambda: {
        "user_id": "u-test",
        "username": "tester",
        "role": "member",
    }

    async with async_client(app) as client:
        yield client, stub_db, stub_orchestrator


async def test_create_asr_session_success(fastapi_client):
    client, stub_db, _ = fastapi_client
    resp = await client.post(
        "/api/v2/asr/sessions",
        files={"file": ("demo.wav", b"fake-audio", "audio/wav")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"].startswith("asr_")
    assert body["status"] == "queued"
    assert body["source_extension"] == "wav"
    assert body["session_id"] in stub_db.rows


async def test_create_asr_session_reject_unsupported_file(fastapi_client):
    client, _, _ = fastapi_client
    resp = await client.post(
        "/api/v2/asr/sessions",
        files={"file": ("demo.exe", b"x", "application/octet-stream")},
    )
    assert resp.status_code == 400
    assert "不支持的文件类型" in resp.json()["detail"]


async def test_list_and_detail_asr_sessions(fastapi_client):
    client, _, _ = fastapi_client
    create_resp = await client.post(
        "/api/v2/asr/sessions",
        files={"file": ("demo.mp3", b"fake-audio", "audio/mpeg")},
    )
    session_id = create_resp.json()["session_id"]

    list_resp = await client.get("/api/v2/asr/sessions")
    assert list_resp.status_code == 200
    assert list_resp.json()["total"] == 1

    detail_resp = await client.get(f"/api/v2/asr/sessions/{session_id}")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["session_id"] == session_id


async def test_retry_only_failed_or_timeout(fastapi_client):
    client, stub_db, _ = fastapi_client
    create_resp = await client.post(
        "/api/v2/asr/sessions",
        files={"file": ("demo.m4a", b"fake-audio", "audio/m4a")},
    )
    session_id = create_resp.json()["session_id"]

    # queued 状态不可重试
    retry_resp = await client.post(f"/api/v2/asr/sessions/{session_id}/retry")
    assert retry_resp.status_code == 409

    # failed 状态可重试
    stub_db.rows[session_id]["status"] = "failed"
    retry_resp = await client.post(f"/api/v2/asr/sessions/{session_id}/retry")
    assert retry_resp.status_code == 200
    assert retry_resp.json()["status"] == "queued"


async def test_export_requires_succeeded_status(fastapi_client):
    client, stub_db, _ = fastapi_client
    create_resp = await client.post(
        "/api/v2/asr/sessions",
        files={"file": ("demo.wav", b"fake-audio", "audio/wav")},
    )
    session_id = create_resp.json()["session_id"]

    # 未成功前导出失败
    export_resp = await client.get(f"/api/v2/asr/sessions/{session_id}/export?format=txt")
    assert export_resp.status_code == 409

    stub_db.rows[session_id]["status"] = "succeeded"
    stub_db.rows[session_id]["transcript_text"] = "hello world"
    stub_db.rows[session_id]["transcript_segments"] = [{"start": 0.0, "end": 1.0, "text": "hello"}]
    stub_db.rows[session_id]["transcript_metadata"] = {"model": "vibevoice"}

    export_resp = await client.get(f"/api/v2/asr/sessions/{session_id}/export?format=json")
    assert export_resp.status_code == 200
    assert export_resp.headers["content-type"].startswith("application/json")

