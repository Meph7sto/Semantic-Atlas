"""Session controller chat request contract tests."""

import pytest
from pydantic import ValidationError

from backend_business.api.deps.auth import get_current_user
from backend_business.api.routers import session_controller_chat
from backend_business.api.routers.session_controller_chat import (
    MobileMessageRequest,
    SessionControllerMessageRequest,
)


class _StubSessionControllerService:
    def __init__(self) -> None:
        self.last_stream_args = None

    def stream_session_controller_reply(self, **kwargs):
        self.last_stream_args = kwargs
        yield {"event": "graph", "data": {"graph_id": "graph-1"}}
        yield {
            "event": "result",
            "data": {
                "graph_id": "graph-1",
                "status": "succeeded",
                "reply_text": "ok",
                "mode": "direct_reply",
            },
        }


def _build_app():
    app = build_test_app(session_controller_chat.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-1", "role": "member"}
    return app


def test_message_request_rejects_unknown_execution_mode():
    with pytest.raises(ValidationError) as exc_info:
        SessionControllerMessageRequest.model_validate(
            {
                "project_id": "p-1",
                "message": "现在需要我做什么？",
                "execution_mode": "invalid-mode",
            }
        )

    assert any(error["loc"][-1] == "execution_mode" for error in exc_info.value.errors())


def test_message_request_rejects_classic_mode():
    with pytest.raises(ValidationError) as exc_info:
        SessionControllerMessageRequest.model_validate(
            {
                "project_id": "p-1",
                "message": "现在需要我做什么？",
                "execution_mode": "classic",
            }
        )

    assert any(error["loc"][-1] == "execution_mode" for error in exc_info.value.errors())


def test_message_request_defaults_to_graph():
    payload = SessionControllerMessageRequest.model_validate(
        {
            "project_id": "p-1",
            "message": "现在需要我做什么？",
        }
    )

    assert payload.execution_mode == "graph"


def test_mobile_message_request_defaults_to_graph():
    payload = MobileMessageRequest.model_validate(
        {
            "project_id": "p-1",
            "message": "现在需要我做什么？",
        }
    )

    assert payload.execution_mode == "graph"


async def test_capabilities_returns_graph_only():
    async with async_client(_build_app()) as client:
        response = await client.get("/api/v2/session-controller/capabilities")

    assert response.status_code == 200
    assert response.json() == {
        "graph_execution_enabled": True,
        "default_execution_mode": "graph",
        "allowed_execution_modes": ["graph"],
    }


def test_stream_message_passes_graph_mode():
    stub = _StubSessionControllerService()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(session_controller_chat, "session_controller_service", stub)
    monkeypatch.setattr(session_controller_chat, "_require_project_access", lambda project_id, current_user: None)
    monkeypatch.setattr(session_controller_chat, "sse_response_raw", lambda generator: list(generator))
    try:
        response = session_controller_chat.stream_message(
            session_id="sess-1",
            payload=SessionControllerMessageRequest.model_validate(
                {
                    "project_id": "p-1",
                    "message": "现在需要我做什么？",
                    "execution_mode": "graph",
                    "use_thinking_mode": False,
                    "delegated_max_tool_call_rounds": 9,
                }
            ),
            current_user={"user_id": "u-1", "role": "member"},
        )
    finally:
        monkeypatch.undo()

    body = "".join(response)
    assert "event: graph" in body
    assert stub.last_stream_args == {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "user_message": "现在需要我做什么？",
        "execution_mode": "graph",
        "model": "deepseek-v4-pro",
        "use_thinking_mode": False,
        "delegated_max_tool_call_rounds": 9,
    }


def test_stream_message_uses_default_graph_mode():
    stub = _StubSessionControllerService()
    monkeypatch = pytest.MonkeyPatch()
    monkeypatch.setattr(session_controller_chat, "session_controller_service", stub)
    monkeypatch.setattr(session_controller_chat, "_require_project_access", lambda project_id, current_user: None)
    monkeypatch.setattr(session_controller_chat, "sse_response_raw", lambda generator: list(generator))
    try:
        response = session_controller_chat.stream_message(
            session_id="sess-1",
            payload=SessionControllerMessageRequest.model_validate(
                {
                    "project_id": "p-1",
                    "message": "现在需要我做什么？",
                }
            ),
            current_user={"user_id": "u-1", "role": "member"},
        )
    finally:
        monkeypatch.undo()

    body = "".join(response)
    assert "event: graph" in body
    assert stub.last_stream_args["execution_mode"] == "graph"
