"""
FastAPI mobile chat route contract tests.
"""

import os
import queue
import sys
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import mobile_chat


class _StubMobileChatService:
    def __init__(self):
        self.last_sessions: dict[str, Any] | None = None
        self.last_messages: dict[str, Any] | None = None
        self.last_create: dict[str, Any] | None = None
        self.last_subscribe: dict[str, Any] | None = None
        self.last_stream: dict[str, Any] | None = None

    def list_sessions(self, user_id: str, limit: int = 200):
        self.last_sessions = {"user_id": user_id, "limit": limit}
        return []

    def list_messages(self, user_id: str, session_id: str, limit: int = 100, since=None):
        self.last_messages = {
            "user_id": user_id,
            "session_id": session_id,
            "limit": limit,
            "since": since,
        }
        return []

    def create_message(self, user_id: str, session_id: str, sender: str, content: str, metadata=None):
        if sender not in ("web", "mobile"):
            raise ValueError("sender must be 'web' or 'mobile'")
        self.last_create = {
            "user_id": user_id,
            "session_id": session_id,
            "sender": sender,
            "content": content,
            "metadata": metadata,
        }
        return {
            "message_id": "mchat_test",
            "user_id": user_id,
            "session_id": session_id,
            "sender": sender,
            "content": content,
            "metadata": metadata,
            "created_at": "2026-02-26T00:00:00Z",
        }

    def subscribe(self, user_id: str, session_id: str):
        self.last_subscribe = {"user_id": user_id, "session_id": session_id}
        return queue.Queue()

    def event_stream(self, q, user_id: str, session_id: str):
        self.last_stream = {"user_id": user_id, "session_id": session_id}
        yield "event: connected\ndata: {}\n\n"


@pytest.fixture
def fastapi_client(monkeypatch):
    stub = _StubMobileChatService()
    monkeypatch.setattr(mobile_chat, "mobile_chat_service", stub)

    app = FastAPI()
    app.include_router(mobile_chat.router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub


def test_list_sessions_user_id_falls_back_to_header_then_anonymous(fastapi_client):
    client, stub = fastapi_client

    resp = client.get("/api/v2/mobile/sessions?user_id=query-user", headers={"X-Actor": "actor-user"})
    assert resp.status_code == 200
    assert stub.last_sessions["user_id"] == "query-user"

    resp = client.get("/api/v2/mobile/sessions", headers={"X-Actor": "actor-user"})
    assert resp.status_code == 200
    assert stub.last_sessions["user_id"] == "actor-user"

    resp = client.get("/api/v2/mobile/sessions")
    assert resp.status_code == 200
    assert stub.last_sessions["user_id"] == "anonymous"


def test_list_messages_uses_query_user_id(fastapi_client):
    client, stub = fastapi_client
    resp = client.get("/api/v2/mobile/messages?session_id=s1&user_id=u-query&limit=20")
    assert resp.status_code == 200
    assert stub.last_messages == {
        "user_id": "u-query",
        "session_id": "s1",
        "limit": 20,
        "since": None,
    }


def test_list_messages_missing_session_id_returns_422(fastapi_client):
    client, _ = fastapi_client
    resp = client.get("/api/v2/mobile/messages")
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(item.get("loc") == ["query", "session_id"] for item in detail)


def test_create_message_user_id_priority_payload_over_header(fastapi_client):
    client, stub = fastapi_client
    resp = client.post(
        "/api/v2/mobile/messages",
        json={
            "user_id": "u-payload",
            "session_id": "s1",
            "sender": "web",
            "content": "hello",
        },
        headers={"X-Actor": "u-header"},
    )
    assert resp.status_code == 200
    assert stub.last_create["user_id"] == "u-payload"


def test_create_message_invalid_sender_returns_400_detail(fastapi_client):
    client, _ = fastapi_client
    resp = client.post(
        "/api/v2/mobile/messages",
        json={
            "session_id": "s1",
            "sender": "bad",
            "content": "hello",
        },
    )
    assert resp.status_code == 400
    assert resp.json()["detail"] == "sender must be 'web' or 'mobile'"


def test_create_message_missing_content_returns_422(fastapi_client):
    client, _ = fastapi_client
    resp = client.post(
        "/api/v2/mobile/messages",
        json={"session_id": "s1", "sender": "web"},
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert any(item.get("loc") == ["body", "content"] for item in detail)


def test_stream_uses_user_id_for_subscription(fastapi_client):
    client, stub = fastapi_client
    resp = client.get("/api/v2/mobile/stream?session_id=s-stream&user_id=u-stream")
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["cache-control"] == "no-cache"
    assert resp.headers["x-accel-buffering"] == "no"
    assert stub.last_subscribe == {"user_id": "u-stream", "session_id": "s-stream"}
    assert stub.last_stream == {"user_id": "u-stream", "session_id": "s-stream"}


