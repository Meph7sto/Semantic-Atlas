"""
FastAPI push route contract tests.
"""

import queue
from typing import Any

import httpx
import pytest
from fastapi import FastAPI


from backend_business.api.deps.auth import get_current_user
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


class _StubApprovalService:
    def approve_from_push_message(self, *, push_message_id: str, approved_by: str):
        return {
            "approval_request_id": "apr-1",
            "push_message_id": push_message_id,
            "status": "applied",
            "approved_by": approved_by,
        }

    def reject_from_push_message(self, *, push_message_id: str, rejected_by: str):
        return {
            "approval_request_id": "apr-1",
            "push_message_id": push_message_id,
            "status": "rejected",
            "rejected_by": rejected_by,
        }


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub = _StubPushService()
    monkeypatch.setattr(push, "push_service", stub)
    monkeypatch.setattr(push, "requirement_change_approval_service", _StubApprovalService())

    app = build_test_app(push.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-1", "role": "member"}

    async with async_client(app) as client:
        yield client, stub


async def test_list_messages_parsing_is_flask_compatible(fastapi_client):
    client, stub = fastapi_client

    response = await client.get(
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


async def test_create_message_missing_required_fields_returns_400(fastapi_client):
    client, _ = fastapi_client

    response = await client.post("/api/v2/push/messages", json={"message_type": "review"})
    assert response.status_code == 400
    assert response.json() == {"success": False, "error": "缺少 title"}


async def test_create_message_value_error_returns_400(fastapi_client):
    client, _ = fastapi_client

    response = await client.post(
        "/api/v2/push/messages",
        json={"message_type": "review", "title": "t", "priority": "urgent"},
    )
    assert response.status_code == 400
    assert "priority must be" in response.json()["error"]


async def test_get_message_and_pending_messages(fastapi_client):
    client, stub = fastapi_client

    detail_resp = await client.get("/api/v2/push/messages/msg-1")
    assert detail_resp.status_code == 200
    assert detail_resp.json()["data"]["message_id"] == "msg-1"

    pending_resp = await client.get(
        "/api/v2/push/messages/pending",
        params={"message_type": "change", "since": "2026-03-03T00:00:00Z"},
    )
    assert pending_resp.status_code == 200
    assert pending_resp.json()["messages"] == [{"message_id": "msg_test"}]
    assert stub.last_pending == {
        "message_type": "change",
        "since": "2026-03-03T00:00:00Z",
    }


async def test_stream_returns_sse_headers(fastapi_client):
    client, _ = fastapi_client

    response = await client.get("/api/v2/push/stream")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["x-accel-buffering"] == "no"
    assert "event: connected" in response.text


async def test_approve_and_reject_message_actions(fastapi_client):
    client, _ = fastapi_client

    approve_resp = await client.post("/api/v2/push/messages/msg-1/approve")
    assert approve_resp.status_code == 200
    assert approve_resp.json()["data"]["status"] == "applied"

    reject_resp = await client.post("/api/v2/push/messages/msg-2/reject")
    assert reject_resp.status_code == 200
    assert reject_resp.json()["data"]["status"] == "rejected"
