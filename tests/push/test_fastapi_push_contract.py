"""
FastAPI push route contract tests.
"""

import os
import queue
import sys
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.api.routers import push


class _StubPushService:
    def __init__(self):
        self.last_list: dict[str, Any] | None = None
        self.last_create: dict[str, Any] | None = None
        self.last_pending: dict[str, Any] | None = None

    def list_messages(self, **kwargs):
        self.last_list = kwargs
        return {"messages": [], "total": 0, "pages": 0, "current_page": kwargs["page"]}

    def create_message(self, **kwargs):
        if kwargs.get("priority") not in ("low", "medium", "high"):
            raise ValueError("priority must be 'low', 'medium', or 'high'")
        self.last_create = kwargs
        return {
            "message_id": "msg_test",
            "message_type": kwargs["message_type"],
            "title": kwargs["title"],
        }

    def get_message(self, message_id: str):
        if message_id == "missing":
            return None
        return {"message_id": message_id, "title": "hello"}

    def push_message(self, message_id: str) -> bool:
        return message_id != "missing"

    def mark_read(self, message_id: str) -> bool:
        return message_id != "missing"

    def delete_message(self, message_id: str) -> bool:
        return message_id != "missing"

    def get_pending_messages(self, **kwargs):
        self.last_pending = kwargs
        return [{"message_id": "msg_test"}]

    def subscribe(self):
        return queue.Queue()

    def event_stream(self, q):
        yield "event: connected\ndata: {\"status\": \"connected\"}\n\n"


@pytest.fixture
def fastapi_client(monkeypatch):
    stub = _StubPushService()
    monkeypatch.setattr(push, "push_service", stub)

    app = FastAPI()
    app.include_router(push.router)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub


def test_list_messages_parsing_is_flask_compatible(fastapi_client):
    client, stub = fastapi_client

    response = client.get(
        "/api/v2/push/messages",
        params={"message_type": "review", "pushed": "yes", "page": "abc", "per_page": "x"},
    )

    assert response.status_code == 200
    assert response.json()["success"] is True
    assert stub.last_list == {
        "message_type": "review",
        "pushed": True,
        "page": 1,
        "per_page": 20,
    }


def test_create_message_missing_required_fields_returns_400(fastapi_client):
    client, _ = fastapi_client

    response = client.post("/api/v2/push/messages", json={"message_type": "review"})
    assert response.status_code == 400
    assert response.json() == {"success": False, "error": "缺少 title"}


def test_create_message_value_error_returns_400(fastapi_client):
    client, _ = fastapi_client

    response = client.post(
        "/api/v2/push/messages",
        json={"message_type": "review", "title": "t", "priority": "urgent"},
    )
    assert response.status_code == 400
    assert "priority must be" in response.json()["error"]


def test_get_message_and_pending_messages(fastapi_client):
    client, stub = fastapi_client

    detail_resp = client.get("/api/v2/push/messages/msg-1")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["message_id"] == "msg-1"

    pending_resp = client.get(
        "/api/v2/push/messages/pending",
        params={"message_type": "change", "since": "2026-03-03T00:00:00Z"},
    )
    assert pending_resp.status_code == 200
    assert pending_resp.json()["messages"] == [{"message_id": "msg_test"}]
    assert stub.last_pending == {
        "message_type": "change",
        "since": "2026-03-03T00:00:00Z",
    }


def test_stream_returns_sse_headers(fastapi_client):
    client, _ = fastapi_client

    response = client.get("/api/v2/push/stream")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert "event: connected" in response.text
