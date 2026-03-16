"""
FastAPI file route contract tests.
"""

from pathlib import Path
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError


from backend_business.api.http.errors import (
    error_response_handler,
    validation_error_handler,
)
from backend_business.api.routers import file as file_router


class _StubFileService:
    def __init__(self, sample_file_path: Path):
        self._sample_file_path = sample_file_path
        self.save_calls: list[dict[str, Any]] = []
        self.list_calls: list[str] = []
        self.delete_calls: list[tuple[str, str]] = []

    def save_uploaded_file(
        self,
        user_id: str,
        original_filename: str,
        content: bytes,
        description: str,
        content_type: str | None = None,
    ):
        self.save_calls.append(
            {
                "user_id": user_id,
                "original_filename": original_filename,
                "description": description,
                "content_type": content_type,
                "size": len(content),
            }
        )
        return {
            "filename": "u1_file.txt",
            "originalFilename": original_filename,
            "fileSize": len(content),
            "uploadTime": "2026-03-09T00:00:00",
        }

    def list_uploaded_files(self, user_id: str):
        self.list_calls.append(user_id)
        return [{"filename": "u1_file.txt", "size": 10}]

    def resolve_accessible_file(self, user_id: str, filename: str):
        _ = user_id, filename
        return str(self._sample_file_path), "text/plain", "download.txt"

    def delete_uploaded_file(self, user_id: str, filename: str):
        self.delete_calls.append((user_id, filename))

    def list_all_users_files(self):
        return {
            "u1": [{"filename": "u1_file.txt"}],
            "u2": [{"filename": "u2_file.txt"}, {"filename": "u2_file2.txt"}],
        }


class _StubAIProxy:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def trace_batch(self, highs: list[str], lows: list[str], max_new_tokens: int = 1600):
        self.calls.append(
            {
                "highs": highs,
                "lows": lows,
                "max_new_tokens": max_new_tokens,
            }
        )
        return {
            "trace_pairs": [{"high": highs[0], "low": lows[0], "score": 0.88}],
            "total": 1,
        }


class _StubDBService:
    def __init__(self):
        self.save_calls: list[dict[str, Any]] = []
        self.detail_calls: list[int] = []
        self.found = True

    def save_batch(self, highs: list[str], lows: list[str], result: dict[str, Any]):
        self.save_calls.append({"highs": highs, "lows": lows, "result": result})
        return 123

    def get_requirement_detail(self, record_id: int):
        self.detail_calls.append(record_id)
        if not self.found:
            return None
        return {
            "id": record_id,
            "output": {"ok": True, "record_id": record_id},
        }


@pytest.fixture
async def fastapi_client(monkeypatch, tmp_path):
    sample = tmp_path / "sample.txt"
    sample.write_text("hello-download", encoding="utf-8")

    stub_file_service = _StubFileService(sample)
    stub_ai_proxy = _StubAIProxy()
    stub_db = _StubDBService()

    monkeypatch.setattr(file_router, "file_service", stub_file_service)
    monkeypatch.setattr(file_router, "ai_proxy", stub_ai_proxy)
    monkeypatch.setattr(file_router, "db_service", stub_db)

    app = build_test_app(file_router.router)
    app.dependency_overrides[file_router.get_current_user] = lambda: {
        "user_id": "u1",
        "role": "member",
    }
    app.dependency_overrides[file_router.require_admin] = lambda: {
        "user_id": "admin-1",
        "role": "admin",
    }

    async with async_client(app) as client:
        yield client, stub_file_service, stub_ai_proxy, stub_db


async def test_upload_and_list_contract(fastapi_client):
    client, stub_file_service, _, _ = fastapi_client

    upload_resp = await client.post(
        "/api/v2/upload",
        data={"description": "demo file"},
        files={"file": ("demo.txt", b"abc", "text/plain")},
    )
    assert upload_resp.status_code == 200
    assert upload_resp.json()["success"] is True
    assert stub_file_service.save_calls[0]["user_id"] == "u1"
    assert stub_file_service.save_calls[0]["description"] == "demo file"

    list_resp = await client.get("/api/v2/uploads")
    assert list_resp.status_code == 200
    body = list_resp.json()
    assert body["success"] is True
    assert body["total"] == 1
    assert stub_file_service.list_calls == ["u1"]


async def test_download_delete_and_admin_list_contract(fastapi_client):
    client, stub_file_service, _, _ = fastapi_client

    preview_resp = await client.get("/api/v2/uploads/u1_file.txt")
    assert preview_resp.status_code == 200
    assert preview_resp.headers["content-type"].startswith("text/plain")
    assert preview_resp.text == "hello-download"

    download_resp = await client.get("/api/v2/uploads/u1_file.txt?download=true")
    assert download_resp.status_code == 200
    assert "attachment" in download_resp.headers.get("content-disposition", "")

    delete_resp = await client.delete("/api/v2/uploads/u1_file.txt")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["success"] is True
    assert stub_file_service.delete_calls == [("u1", "u1_file.txt")]

    admin_resp = await client.get("/api/v2/admin/uploads")
    assert admin_resp.status_code == 200
    assert admin_resp.json()["userCount"] == 2
    assert admin_resp.json()["total"] == 3


async def test_upload_csv_success_and_download_result_contract(fastapi_client):
    client, _, stub_ai_proxy, stub_db = fastapi_client

    csv_content = (
        "high_level_requirement,low_level_requirement\n"
        "H1,L1\n"
        "H1,L1\n"
        "H2,L2\n"
    ).encode("utf-8")

    upload_csv_resp = await client.post(
        "/api/v2/upload_csv",
        data={"save_to_db": "true", "max_new_tokens": "128"},
        files={"file": ("req.csv", csv_content, "text/csv")},
    )
    assert upload_csv_resp.status_code == 200
    body = upload_csv_resp.json()
    assert body["success"] is True
    assert body["record_id"] == 123
    assert len(stub_ai_proxy.calls[0]["highs"]) == 2
    assert len(stub_ai_proxy.calls[0]["lows"]) == 2
    assert stub_ai_proxy.calls[0]["max_new_tokens"] == 128
    assert len(stub_db.save_calls) == 1

    download_result_resp = await client.get("/api/v2/download_result?id=123")
    assert download_result_resp.status_code == 200
    assert download_result_resp.headers["content-type"].startswith("application/json")
    assert "trace_result_123.json" in download_result_resp.headers.get("content-disposition", "")
    assert download_result_resp.json()["record_id"] == 123


async def test_upload_csv_missing_pairs_returns_400(fastapi_client):
    client, _, _, _ = fastapi_client

    bad_csv = "x,y\n1,2\n".encode("utf-8")
    response = await client.post(
        "/api/v2/upload_csv",
        files={"file": ("bad.csv", bad_csv, "text/csv")},
    )
    assert response.status_code == 400
    assert "CSV 中未解析到有效的 high/low 需求对" in response.json()["detail"]


async def test_download_result_not_found_returns_404(fastapi_client):
    client, _, _, stub_db = fastapi_client
    stub_db.found = False

    response = await client.get("/api/v2/download_result?id=999")
    assert response.status_code == 404
    assert response.json()["detail"] == "资源未找到"
