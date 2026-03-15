"""
FastAPI agent chat prompt payload format contract tests.
"""

from __future__ import annotations

import os
import sys

from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import agent_chat


class _StubAgentChatPromptService:
    def __init__(self):
        self.last_create_or_get_kwargs = None
        self.last_create_kwargs = None
        self.last_update_kwargs = None

    def create_or_get_session(self, **kwargs):
        self.last_create_or_get_kwargs = kwargs
        return {
            "session_id": "sess-1",
            "project_id": kwargs.get("project_id"),
            "user_id": kwargs.get("user_id"),
            "prompt_payload_format": kwargs.get("prompt_payload_format") or "json",
        }

    def create_session(self, **kwargs):
        self.last_create_kwargs = kwargs
        return {
            "session_id": "sess-new",
            "project_id": kwargs.get("project_id"),
            "user_id": kwargs.get("user_id"),
            "title": kwargs.get("title"),
            "prompt_payload_format": kwargs.get("prompt_payload_format") or "json",
        }

    def update_session(self, **kwargs):
        self.last_update_kwargs = kwargs
        return {
            "session_id": kwargs.get("session_id"),
            "user_id": kwargs.get("user_id"),
            "title": kwargs.get("title"),
            "prompt_payload_format": kwargs.get("prompt_payload_format") or "json",
        }


def _build_client():
    app = FastAPI()
    app.include_router(agent_chat.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-1", "role": "member"}
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)
    return TestClient(app, raise_server_exceptions=False)


def test_create_or_get_session_forwards_prompt_payload_format(monkeypatch):
    stub = _StubAgentChatPromptService()
    monkeypatch.setattr(agent_chat, "requirement_agent_chat_service", stub)
    monkeypatch.setattr(agent_chat, "_require_project_access", lambda project_id, current_user: None)

    with _build_client() as client:
        response = client.post(
            "/api/v2/agent-chat/sessions",
            json={"project_id": "p-1", "prompt_payload_format": "yaml"},
        )

    assert response.status_code == 200
    assert response.json()["prompt_payload_format"] == "yaml"
    assert stub.last_create_or_get_kwargs == {
        "user_id": "u-1",
        "project_id": "p-1",
        "prompt_payload_format": "yaml",
    }


def test_create_session_forwards_prompt_payload_format(monkeypatch):
    stub = _StubAgentChatPromptService()
    monkeypatch.setattr(agent_chat, "requirement_agent_chat_service", stub)
    monkeypatch.setattr(agent_chat, "_require_project_access", lambda project_id, current_user: None)

    with _build_client() as client:
        response = client.post(
            "/api/v2/agent-chat/sessions/new",
            json={"project_id": "p-1", "title": "会话1", "prompt_payload_format": "markdown"},
        )

    assert response.status_code == 200
    assert response.json()["prompt_payload_format"] == "markdown"
    assert stub.last_create_kwargs == {
        "user_id": "u-1",
        "project_id": "p-1",
        "title": "会话1",
        "prompt_payload_format": "markdown",
    }


def test_patch_session_updates_prompt_payload_format(monkeypatch):
    stub = _StubAgentChatPromptService()
    monkeypatch.setattr(agent_chat, "requirement_agent_chat_service", stub)

    with _build_client() as client:
        response = client.patch(
            "/api/v2/agent-chat/sessions/sess-1",
            json={"prompt_payload_format": "json"},
        )

    assert response.status_code == 200
    assert response.json()["prompt_payload_format"] == "json"
    assert stub.last_update_kwargs == {
        "session_id": "sess-1",
        "user_id": "u-1",
        "title": None,
        "prompt_payload_format": "json",
    }


def test_patch_session_requires_at_least_one_field(monkeypatch):
    stub = _StubAgentChatPromptService()
    monkeypatch.setattr(agent_chat, "requirement_agent_chat_service", stub)

    with _build_client() as client:
        response = client.patch("/api/v2/agent-chat/sessions/sess-1", json={})

    assert response.status_code == 400
    assert "至少提供一个可更新字段" in response.text
