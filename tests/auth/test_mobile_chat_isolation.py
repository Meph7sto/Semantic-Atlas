"""
Tests for mobile chat user isolation behavior.
"""

import os
import queue
import sys
from typing import Any

import pytest
from flask import Flask

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import backend_business.services.mobile_chat_service as mobile_chat_module
from backend_business.routes import mobile_chat_routes
from backend_business.services.mobile_chat_service import MobileChatService


class _FakeCursor:
    def __init__(self, rows=None):
        self.rows = rows or []
        self.executions = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params=None):
        self.executions.append((query, params))

    def fetchall(self):
        return self.rows


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
    monkeypatch.setattr(mobile_chat_routes, "mobile_chat_service", stub)

    app = Flask(__name__)
    app.register_blueprint(mobile_chat_routes.mobile_chat_bp, url_prefix="/api/mobile")
    with app.test_client() as client:
        yield client, stub


def test_list_sessions_user_id_falls_back_to_header_then_anonymous(mobile_client):
    client, stub = mobile_client

    resp = client.get("/api/mobile/sessions?user_id=query-user", headers={"X-Actor": "actor-user"})
    assert resp.status_code == 200
    assert stub.last_sessions["user_id"] == "query-user"

    resp = client.get("/api/mobile/sessions", headers={"X-Actor": "actor-user"})
    assert resp.status_code == 200
    assert stub.last_sessions["user_id"] == "actor-user"

    resp = client.get("/api/mobile/sessions")
    assert resp.status_code == 200
    assert stub.last_sessions["user_id"] == "anonymous"


def test_list_messages_uses_query_user_id(mobile_client):
    client, stub = mobile_client
    resp = client.get("/api/mobile/messages?session_id=s1&user_id=u-query&limit=20")
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
        "/api/mobile/messages",
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
    resp = client.get("/api/mobile/stream?session_id=s-stream&user_id=u-stream")
    _ = resp.get_data(as_text=True)
    assert resp.status_code == 200
    assert stub.last_subscribe == {"user_id": "u-stream", "session_id": "s-stream"}
    assert stub.last_stream == {"user_id": "u-stream", "session_id": "s-stream"}


def test_service_sql_uses_user_id(monkeypatch):
    cursor = _FakeCursor(rows=[{"message_id": "m1", "user_id": "u1"}])
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
