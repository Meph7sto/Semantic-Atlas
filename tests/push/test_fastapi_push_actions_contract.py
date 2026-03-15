"""
FastAPI push action route contract tests.
"""

import os
import sys

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.api.routers import push


class _StubPushActionService:
    def __init__(self):
        self.pushed: list[str] = []
        self.read: list[str] = []
        self.deleted: list[str] = []

    def push_message(self, message_id: str) -> bool:
        if message_id.startswith("missing"):
            return False
        self.pushed.append(message_id)
        return True

    def mark_read(self, message_id: str) -> bool:
        if message_id.startswith("missing"):
            return False
        self.read.append(message_id)
        return True

    def delete_message(self, message_id: str) -> bool:
        if message_id.startswith("missing"):
            return False
        self.deleted.append(message_id)
        return True


@pytest.fixture
def fastapi_client(monkeypatch):
    stub = _StubPushActionService()
    monkeypatch.setattr(push, "push_service", stub)

    app = FastAPI()
    app.include_router(push.router)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, stub


def test_push_mark_read_delete_success(fastapi_client):
    client, stub = fastapi_client

    push_resp = client.post("/api/v2/push/messages/m1/push")
    assert push_resp.status_code == 200
    assert push_resp.json()["message"] == "消息已推送"

    read_resp = client.post("/api/v2/push/messages/m1/read")
    assert read_resp.status_code == 200
    assert read_resp.json()["message"] == "已标记为已读"

    delete_resp = client.delete("/api/v2/push/messages/m1")
    assert delete_resp.status_code == 200
    assert delete_resp.json()["message"] == "消息已删除"

    assert stub.pushed == ["m1"]
    assert stub.read == ["m1"]
    assert stub.deleted == ["m1"]


def test_push_mark_read_delete_not_found(fastapi_client):
    client, _ = fastapi_client

    push_resp = client.post("/api/v2/push/messages/missing-1/push")
    assert push_resp.status_code == 404
    assert push_resp.json()["error"] == "消息不存在"

    read_resp = client.post("/api/v2/push/messages/missing-1/read")
    assert read_resp.status_code == 404
    assert read_resp.json()["error"] == "消息不存在"

    delete_resp = client.delete("/api/v2/push/messages/missing-1")
    assert delete_resp.status_code == 404
    assert delete_resp.json()["error"] == "消息不存在"

