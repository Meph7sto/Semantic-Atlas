"""
FastAPI ASR inference route contract tests.
"""

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import backend_inference.routers.asr as asr


@pytest.fixture
def fastapi_client(monkeypatch):
    class _StubASRService:
        def health(self):
            return {"available": True, "loaded": True, "detail": "ok", "model": "stub-model"}

        def warmup(self):
            return None

        def transcribe(self, file_bytes: bytes, filename: str, content_type: str):
            return {
                "text": "hello world",
                "segments": [{"start": 0.0, "end": 1.2, "text": "hello world"}],
                "metadata": {"model": "stub-model", "filename": filename, "size": len(file_bytes)},
            }

    monkeypatch.setattr(asr, "asr_service", _StubASRService())

    app = FastAPI()
    app.include_router(asr.router)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_asr_health_ok(fastapi_client):
    client = fastapi_client
    resp = client.get("/asr/health")
    assert resp.status_code == 200
    assert resp.json()["available"] is True


def test_transcribe_success_contract(fastapi_client):
    client = fastapi_client
    resp = client.post(
        "/asr/transcribe",
        data={"session_id": "s-1", "attempt_no": "1"},
        files={"file": ("demo.wav", b"fake-audio", "audio/wav")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "s-1"
    assert body["attempt_no"] == "1"
    assert body["text"] == "hello world"
    assert isinstance(body["segments"], list)
    assert "remote_request_id" in body


def test_transcribe_empty_file_returns_400(fastapi_client):
    client = fastapi_client
    resp = client.post(
        "/asr/transcribe",
        files={"file": ("empty.wav", b"", "audio/wav")},
    )
    assert resp.status_code == 400
    assert "file is empty" in resp.json()["detail"]
