"""
FastAPI classification route contract tests.
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

from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import classification


class _FakeResponse:
    def __init__(self, status_code: int, json_data: Any, headers: dict[str, str] | None = None, content: bytes | None = None):
        self.status_code = status_code
        self._json_data = json_data
        self.headers = headers or {"Content-Type": "application/json"}
        self.content = content if content is not None else b""
        self.text = content.decode("utf-8", errors="ignore") if content else ""

    def json(self):
        if isinstance(self._json_data, Exception):
            raise self._json_data
        return self._json_data


class _StubAsyncClient:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self.raise_connect_error = False

    async def post(self, url: str, json: dict | None = None, files: dict | None = None, timeout: float | None = None):
        self.calls.append({"url": url, "json": json, "files": files, "timeout": timeout})

        if self.raise_connect_error:
            raise httpx.ConnectError("connect failed", request=httpx.Request("POST", url))

        if url.endswith("/classification/predict-texts"):
            return _FakeResponse(
                status_code=200,
                json_data={
                    "total": 1,
                    "predictions": [{"index": 0, "requirement": "A", "predicted_label": "功能性需求"}],
                    "label_distribution": {"功能性需求": 1},
                },
            )

        if url.endswith("/classification/predict-csv"):
            csv_bytes = "text,predicted_label\nA,功能性需求\n".encode("utf-8-sig")
            return _FakeResponse(
                status_code=200,
                json_data={},
                headers={
                    "Content-Type": "text/csv",
                    "Content-Disposition": "attachment; filename=pred_test.csv",
                },
                content=csv_bytes,
            )

        return _FakeResponse(status_code=500, json_data={"detail": "unexpected url"})


class _StubDBService:
    def __init__(self):
        self.saved_calls: list[dict[str, Any]] = []
        self.latest_calls: list[str] = []

    def save_classification(self, **kwargs):
        self.saved_calls.append(kwargs)
        return 77

    def get_latest_classification(self, session_id: str):
        self.latest_calls.append(session_id)
        return {"session_id": session_id, "total": 1}


@pytest.fixture
def fastapi_client(monkeypatch):
    stub_client = _StubAsyncClient()
    stub_db = _StubDBService()

    monkeypatch.setattr(classification, "_get_http_client", lambda _request: stub_client)
    monkeypatch.setattr(classification, "db_service", stub_db)

    app = FastAPI()
    app.include_router(classification.router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub_client, stub_db


def test_predict_texts_success_and_save_to_db(fastapi_client):
    client, stub_client, stub_db = fastapi_client

    response = client.post(
        "/api/v2/classification/predict-texts",
        json={
            "requirements": ["A"],
            "save_to_db": True,
            "session_id": " s-1 ",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["record_id"] == 77
    assert body["total"] == 1
    assert stub_client.calls[0]["json"] == {"requirements": ["A"]}
    assert stub_db.saved_calls[0]["session_id"] == "s-1"


def test_predict_texts_connect_error_returns_503(fastapi_client):
    client, stub_client, _ = fastapi_client
    stub_client.raise_connect_error = True

    response = client.post(
        "/api/v2/classification/predict-texts",
        json={"requirements": ["A"]},
    )

    assert response.status_code == 503
    assert "Cannot connect to Classification Service" in response.json()["detail"]


def test_predict_csv_missing_file_returns_400(fastapi_client):
    client, _, _ = fastapi_client

    response = client.post("/api/v2/classification/predict-csv")
    assert response.status_code == 400
    assert response.json()["detail"] == "请上传 CSV 文件"


def test_predict_csv_passes_through_csv_response(fastapi_client):
    client, stub_client, _ = fastapi_client

    response = client.post(
        "/api/v2/classification/predict-csv",
        files={"file": ("reqs.csv", b"text\nA\n", "text/csv")},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")
    assert "predicted_label" in response.text
    assert stub_client.calls[0]["files"]["file"][0] == "reqs.csv"


def test_latest_classification_requires_session_id(fastapi_client):
    client, _, _ = fastapi_client

    response = client.get("/api/v2/classification/latest")
    assert response.status_code == 400
    assert response.json()["detail"] == "缺少 session_id"


def test_latest_classification_success(fastapi_client):
    client, _, stub_db = fastapi_client

    response = client.get("/api/v2/classification/latest?session_id=s-1")
    assert response.status_code == 200
    assert response.json()["data"]["session_id"] == "s-1"
    assert stub_db.latest_calls == ["s-1"]
