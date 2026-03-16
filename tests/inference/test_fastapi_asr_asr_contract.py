"""
FastAPI ASR inference route contract tests for backend_inference_ASR.
"""

import pytest

asr = pytest.importorskip("backend_inference_ASR.routers.asr")


@pytest.fixture
async def fastapi_client(monkeypatch):
    class _StubASRService:
        def health(self):
            return {
                "available": True,
                "loaded": True,
                "detail": "ok",
                "model": "stub-model",
            }

        def warmup(self):
            return None

        def transcribe(self, file_bytes: bytes, filename: str, content_type: str):
            return {
                "text": "hello",
                "segments": [{"start": 0.0, "end": 1.2, "speaker": 0, "text": "hello"}],
                "decoded_json": [
                    {"Start": 0.0, "End": 1.2, "Speaker": 0, "Content": "hello"}
                ],
                "raw_out": '<|im_start|>assistant\n[{"Start":0.0,"End":1.2,"Speaker":0,"Content":"hello"}]<|im_end|>',
                "metadata": {
                    "model": "stub-model",
                    "filename": filename,
                    "size": len(file_bytes),
                },
            }

    monkeypatch.setattr(asr, "asr_service", _StubASRService())

    app = build_test_app(asr.router, include_error_handlers=False)
    async with async_client(app) as client:
        yield client


async def test_transcribe_success_contract_returns_raw_out(fastapi_client):
    client = fastapi_client
    resp = await client.post(
        "/asr/transcribe",
        data={"session_id": "s-1", "attempt_no": "1"},
        files={"file": ("demo.wav", b"fake-audio", "audio/wav")},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["session_id"] == "s-1"
    assert body["attempt_no"] == "1"
    assert body["text"] == "hello"
    assert isinstance(body["segments"], list)
    assert isinstance(body["decoded_json"], list)
    assert body["raw_out"].startswith("<|im_start|>assistant")
    assert "remote_request_id" in body
