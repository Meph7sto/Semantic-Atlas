"""
FastAPI vision route contract tests.
"""

import os
import sys
from typing import Any

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.api.http.errors import (
    error_response_handler,
    validation_error_handler,
)
from backend_business.api.routers import vision


class _FakeUpstreamResponse:
    def __init__(self, status_code: int, payload: dict[str, Any]):
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self):
        return self._payload


class _StubHTTPClient(httpx.AsyncClient):
    def __init__(self):
        super().__init__()
        self.calls: list[dict[str, Any]] = []
        self.payload = {
            "success": True,
            "filename": "img.png",
            "speaker": "vision_agent",
            "prompt": "describe",
            "caption": "一张测试图片",
            "transcript_text": "[00:00] vision_agent: 一张测试图片",
        }

    async def post(self, url: str, data=None, files=None, timeout=None):
        self.calls.append({"url": url, "data": data, "files": files, "timeout": timeout})
        return _FakeUpstreamResponse(200, self.payload)


class _StubDBService:
    def __init__(self):
        self.upsert_calls: list[list[dict[str, Any]]] = []

    def upsert_spans(self, spans: list[dict[str, Any]]):
        self.upsert_calls.append(spans)
        return {"upserted_count": len(spans), "conflicts": []}


@pytest.fixture
def fastapi_client(monkeypatch):
    stub_http = _StubHTTPClient()
    stub_db = _StubDBService()

    def _fake_parse(transcript_text: str, session_id: str, options: dict[str, Any]):
        _ = transcript_text, options
        spans = [
            {
                "span_id": "sp-1",
                "session_id": session_id,
                "speaker": "vision_agent",
                "text": "第一句",
                "start_ms": 0,
                "end_ms": 8000,
            },
            {
                "span_id": "sp-2",
                "session_id": session_id,
                "speaker": "vision_agent",
                "text": "第二句",
                "start_ms": 8000,
                "end_ms": 16000,
            },
        ]
        return spans, ["warn-a"], {"speaker_count": 1}

    monkeypatch.setattr(vision.settings, "VISION_CALLBACK_SOURCE", "autodl")
    monkeypatch.setattr(vision.settings, "VISION_CALLBACK_TOKEN", "token-123")
    monkeypatch.setattr(vision, "db_service", stub_db)
    monkeypatch.setattr(vision, "parse_transcript_to_spans", _fake_parse)
    vision._previews.clear()

    app = FastAPI()
    app.include_router(vision.router)
    app.state.http_client = stub_http
    app.dependency_overrides[vision.get_current_user] = lambda: {
        "user_id": "u1",
        "role": "member",
    }
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub_http, stub_db

    vision._previews.clear()


def test_callback_requires_source_headers(fastapi_client):
    client, _, _ = fastapi_client

    response = client.post(
        "/api/v2/vision/callback",
        json={
            "filename": "a.png",
            "speaker": "vision_agent",
            "prompt": "描述",
            "caption": "图像描述",
            "transcript_text": "[00:00] vision_agent: 图像描述",
        },
    )
    assert response.status_code == 403
    assert response.json()["detail"] == "非法来源"


def test_callback_list_and_confirm_contract(fastapi_client):
    client, _, stub_db = fastapi_client

    callback_resp = client.post(
        "/api/v2/vision/callback",
        headers={
            "X-Vision-Source": "autodl",
            "X-Vision-Source-Token": "token-123",
        },
        json={
            "filename": "a.png",
            "speaker": "vision_agent",
            "prompt": "描述",
            "caption": "图像描述",
            "transcript_text": "[00:00] vision_agent: 图像描述",
        },
    )
    assert callback_resp.status_code == 200
    preview_id = callback_resp.json()["data"]["preview_id"]

    list_resp = client.get("/api/v2/vision/previews")
    assert list_resp.status_code == 200
    items = list_resp.json()["data"]
    assert len(items) == 1
    assert items[0]["preview_id"] == preview_id
    assert items[0]["status"] == "pending"

    confirm_resp = client.post(
        f"/api/v2/vision/previews/{preview_id}/confirm",
        json={"session_id": "s-1", "max_spans_returned": 1},
    )
    assert confirm_resp.status_code == 200
    data = confirm_resp.json()["data"]
    assert data["session_id"] == "s-1"
    assert data["span_total"] == 2
    assert len(data["spans_preview"]) == 1
    assert len(stub_db.upsert_calls) == 1

    confirm_again = client.post(
        f"/api/v2/vision/previews/{preview_id}/confirm",
        json={"session_id": "s-1"},
    )
    assert confirm_again.status_code == 409
    assert confirm_again.json()["detail"] == "该预览已确认入库"


def test_caption_rejects_non_image_file(fastapi_client):
    client, _, _ = fastapi_client

    response = client.post(
        "/api/v2/vision/caption",
        data={"prompt": "x", "speaker": "vision_agent"},
        files={"file": ("a.txt", b"text", "text/plain")},
    )
    assert response.status_code == 400
    assert response.json()["detail"] == "仅支持图片文件"


def test_caption_success_creates_preview(fastapi_client):
    client, stub_http, _ = fastapi_client

    response = client.post(
        "/api/v2/vision/caption",
        data={"prompt": "describe image", "speaker": "vision_agent"},
        files={"file": ("a.png", b"\x89PNG\r\n", "image/png")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["result"]["caption"] == "一张测试图片"
    assert body["data"]["preview"]["status"] == "pending"
    assert stub_http.calls[0]["url"] == vision.settings.VISION_CAPTION_URL
