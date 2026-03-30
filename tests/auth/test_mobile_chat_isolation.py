"""
Tests for mobile chat user isolation behavior.
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
import backend_business.services.mobile_chat_service as mobile_chat_module
from backend_business.services.mobile_chat_service import MobileChatService


class _FakeCursor:
    def __init__(self, rows=None, one_rows=None):
        self.rows = rows or []
        self.one_rows = list(one_rows or [])
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executions.append((query, params))

    def fetchall(self):
        return self.rows

    def fetchone(self):
        if self.one_rows:
            return self.one_rows.pop(0)
        return None


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, *args, **kwargs):
        return self._cursor


class _FakeDB:
    def __init__(self, cursor):
        self._cursor = cursor

    def _connect(self):
        return _FakeConnection(self._cursor)


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
def mobile_client(monkeypatch):
    stub = _StubMobileChatService()
    monkeypatch.setattr(mobile_chat, "mobile_chat_service", stub)

    app = FastAPI()
    app.include_router(mobile_chat.router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub


def test_list_sessions_user_id_falls_back_to_header_then_anonymous(mobile_client):
    client, stub = mobile_client

    resp = client.get("/api/v2/mobile/sessions?user_id=query-user", headers={"X-Actor": "actor-user"})
    assert resp.status_code == 200
    assert stub.last_sessions["user_id"] == "query-user"

    resp = client.get("/api/v2/mobile/sessions", headers={"X-Actor": "actor-user"})
    assert resp.status_code == 200
    assert stub.last_sessions["user_id"] == "actor-user"

    resp = client.get("/api/v2/mobile/sessions")
    assert resp.status_code == 200
    assert stub.last_sessions["user_id"] == "anonymous"


def test_list_messages_uses_query_user_id(mobile_client):
    client, stub = mobile_client
    resp = client.get("/api/v2/mobile/messages?session_id=s1&user_id=u-query&limit=20")
    assert resp.status_code == 200
    assert stub.last_messages == {
        "user_id": "u-query",
        "session_id": "s1",
        "limit": 20,
        "since": None,
    }


def test_create_message_user_id_priority_payload_over_header(mobile_client):
    client, stub = mobile_client
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


def test_stream_uses_user_id_for_subscription(mobile_client):
    client, stub = mobile_client
    resp = client.get("/api/v2/mobile/stream?session_id=s-stream&user_id=u-stream")
    _ = resp.text
    assert resp.status_code == 200
    assert stub.last_subscribe == {"user_id": "u-stream", "session_id": "s-stream"}
    assert stub.last_stream == {"user_id": "u-stream", "session_id": "s-stream"}


def test_service_sql_uses_user_id(monkeypatch):
    cursor = _FakeCursor(rows=[{"message_id": "m1", "user_id": "u1"}], one_rows=[None, None])
    fake_db = _FakeDB(cursor)
    monkeypatch.setattr(mobile_chat_module, "db_service", fake_db)

    service = MobileChatService()
    service.create_message(
        user_id="u1",
        session_id="s1",
        sender="web",
        content="msg",
    )
    _, insert_params = cursor.executions[-1]
    assert insert_params[1] == "u1"
    assert insert_params[2] == "s1"

    service.list_messages(user_id="u1", session_id="s1", limit=10)
    _, list_params = cursor.executions[-1]
    assert list_params[0] == "u1"
    assert list_params[1] == "s1"
    assert list_params[-1] == 10


def test_service_deduplicates_recent_mobile_message(monkeypatch):
    duplicate_row = {
        "message_id": "m_existing",
        "user_id": "u1",
        "session_id": "s1",
        "sender": "mobile",
        "content": "hello",
        "metadata": '{"client_message_id":"cmid-1"}',
        "created_at": "2026-03-29T12:00:00Z",
    }
    cursor = _FakeCursor(one_rows=[duplicate_row])
    fake_db = _FakeDB(cursor)
    monkeypatch.setattr(mobile_chat_module, "db_service", fake_db)

    service = MobileChatService()
    message = service.create_message(
        user_id="u1",
        session_id="s1",
        sender="mobile",
        content="hello",
        metadata={"client_message_id": "cmid-1"},
    )

    assert message["message_id"] == "m_existing"
    assert message["metadata"]["client_message_id"] == "cmid-1"
    assert len(cursor.executions) == 1
    assert "COALESCE(" in cursor.executions[0][0]


def test_service_deduplicates_recent_mobile_message_by_content_window(monkeypatch):
    duplicate_row = {
        "message_id": "m_existing",
        "user_id": "u1",
        "session_id": "s1",
        "sender": "mobile",
        "content": "hello",
        "metadata": None,
        "created_at": "2026-03-29T12:00:00Z",
    }
    cursor = _FakeCursor(one_rows=[duplicate_row])
    fake_db = _FakeDB(cursor)
    monkeypatch.setattr(mobile_chat_module, "db_service", fake_db)

    service = MobileChatService()
    message = service.create_message(
        user_id="u1",
        session_id="s1",
        sender="mobile",
        content="hello",
    )

    assert message["message_id"] == "m_existing"
    assert len(cursor.executions) == 1
    assert "created_at >= NOW()" in cursor.executions[0][0]


def test_service_does_not_dedupe_web_message_by_content_window(monkeypatch):
    cursor = _FakeCursor()
    fake_db = _FakeDB(cursor)
    monkeypatch.setattr(mobile_chat_module, "db_service", fake_db)

    service = MobileChatService()
    message = service.create_message(
        user_id="u1",
        session_id="s1",
        sender="web",
        content="hello",
    )

    assert message["sender"] == "web"
    assert len(cursor.executions) == 1
    assert "INSERT INTO mobile_chat_messages" in cursor.executions[0][0]


def test_service_broadcast_is_scoped_by_user_and_session():
    service = MobileChatService()
    q_u1_s1 = service.subscribe("u1", "s1")
    q_u2_s1 = service.subscribe("u2", "s1")
    q_u1_s2 = service.subscribe("u1", "s2")

    service._broadcast(
        {
            "message_id": "m1",
            "user_id": "u1",
            "session_id": "s1",
            "sender": "web",
            "content": "hello",
        }
    )

    assert not q_u1_s1.empty()
    assert q_u2_s1.empty()
    assert q_u1_s2.empty()
