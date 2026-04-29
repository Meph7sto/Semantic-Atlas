"""
FastAPI conflict route contract tests.
"""


import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError


from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import conflict


class _StubAIProxy:
    def __init__(self):
        self.calls = []
        self.should_raise = False

    def conflict_check(
        self,
        requirement_a: str,
        requirement_b: str,
        model: str = "deepseek-v4-pro",
        use_thinking_mode: bool = True,
    ):
        self.calls.append((requirement_a, requirement_b, model, use_thinking_mode))
        if self.should_raise:
            raise RuntimeError("mock ai error")
        return {
            "is_conflict": True,
            "raw_response": "ok",
            "reason": f"{requirement_a}->{requirement_b}",
        }

    def conflict_stream_check(
        self,
        requirement_a: str,
        requirement_b: str,
        model: str = "deepseek-v4-pro",
        use_thinking_mode: bool = True,
    ):
        self.calls.append((requirement_a, requirement_b, model, use_thinking_mode))
        yield b'{"type":"token","content":"hello"}\n'
        yield b'{"type":"result","data":{"is_conflict":true,"raw_response":"hello"}}\n'


class _StubDBService:
    def __init__(self):
        self.saved = []
        self.latest_calls = []

    def save_conflict_batch(self, session_id=None, conflicts=None, batch_id=None):
        self.saved.append(
            {
                "session_id": session_id,
                "conflicts": conflicts or [],
                "batch_id": batch_id,
            }
        )
        return [101 + len(self.saved)]

    def get_latest_conflict_batch(self, session_id: str):
        self.latest_calls.append(session_id)
        return {"batch_id": "b-1", "items": [{"is_conflict": True}]}


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub_ai = _StubAIProxy()
    stub_db = _StubDBService()

    monkeypatch.setattr(conflict, "ai_proxy", stub_ai)
    monkeypatch.setattr(conflict, "db_service", stub_db)

    app = build_test_app(conflict.router)

    async with async_client(app) as client:
        yield client, stub_ai, stub_db


async def test_check_conflict_success_and_db_save(fastapi_client):
    client, stub_ai, stub_db = fastapi_client

    response = await client.post(
        "/api/v2/conflict/check",
        json={
            "requirement_a": " A ",
            "requirement_b": "B",
            "save_to_db": True,
            "session_id": " s-1 ",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["record_id"] == 102
    assert body["data"]["is_conflict"] is True

    assert stub_ai.calls == [("A", "B", "deepseek-v4-pro", True)]
    assert stub_db.saved[0]["session_id"] == "s-1"
    assert stub_db.saved[0]["conflicts"][0]["requirement_a"] == "A"


async def test_check_conflict_validation_blank_text_returns_422(fastapi_client):
    client, _, _ = fastapi_client

    response = await client.post(
        "/api/v2/conflict/check",
        json={"requirement_a": "   ", "requirement_b": "ok"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item.get("loc") == ["body", "requirement_a"] for item in detail)


async def test_check_conflict_ai_error_returns_500(fastapi_client):
    client, stub_ai, _ = fastapi_client
    stub_ai.should_raise = True

    response = await client.post(
        "/api/v2/conflict/check",
        json={"requirement_a": "a", "requirement_b": "b"},
    )

    assert response.status_code == 500
    assert response.json()["detail"] == "mock ai error"


async def test_check_conflict_batch_success(fastapi_client):
    client, stub_ai, stub_db = fastapi_client

    response = await client.post(
        "/api/v2/conflict/check/batch",
        json={
            "pairs": [
                {"requirement_a": "a1", "requirement_b": "b1"},
                {"requirement_a": "a2", "requirement_b": "b2"},
            ],
            "save_to_db": True,
            "session_id": "s-batch",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["total"] == 2
    assert body["record_ids"] == [102]
    assert len(body["data"]) == 2
    assert stub_ai.calls == [
        ("a1", "b1", "deepseek-v4-pro", True),
        ("a2", "b2", "deepseek-v4-pro", True),
    ]
    assert len(stub_db.saved[0]["conflicts"]) == 2


async def test_check_conflict_batch_requires_pairs(fastapi_client):
    client, _, _ = fastapi_client

    response = await client.post(
        "/api/v2/conflict/check/batch",
        json={"pairs": []},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item.get("loc") == ["body", "pairs"] for item in detail)


async def test_get_latest_requires_session_id_query(fastapi_client):
    client, _, _ = fastapi_client

    response = await client.get("/api/v2/conflict/latest")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item.get("loc") == ["query", "session_id"] for item in detail)


async def test_get_latest_blank_session_id_returns_400(fastapi_client):
    client, _, _ = fastapi_client

    response = await client.get("/api/v2/conflict/latest", params={"session_id": "   "})
    assert response.status_code == 400
    assert response.json()["detail"] == "session_id 不能为空"


async def test_stream_check_conflict_success_with_thinking_mode(fastapi_client):
    client, stub_ai, _ = fastapi_client

    response = await client.post(
        "/api/v2/conflict/stream_check",
        json={
            "requirement_a": "a",
            "requirement_b": "b",
            "use_thinking_mode": True,
        },
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/x-ndjson")
    assert '{"type":"token","content":"hello"}' in response.text
    assert '{"type":"result","data":{"is_conflict":true,"raw_response":"hello"}}' in response.text
    assert stub_ai.calls == [("a", "b", "deepseek-v4-pro", True)]
