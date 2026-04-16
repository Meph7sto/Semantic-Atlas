"""Session controller chat request contract tests."""

import pytest
from pydantic import ValidationError

from backend_business.api.routers import session_controller_chat
from backend_business.api.routers.session_controller_chat import SessionControllerMessageRequest


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


def test_message_request_rejects_unknown_execution_mode():
    try:
        SessionControllerMessageRequest.model_validate(
            {
                "project_id": "p-1",
                "message": "现在需要我做什么？",
                "execution_mode": "invalid-mode",
            }
        )
    except ValidationError as exc:
        detail = exc.errors()
    else:  # pragma: no cover
        raise AssertionError("invalid execution_mode 应被拒绝")

    assert any(error["loc"][-1] == "execution_mode" for error in detail)


def test_message_request_rejects_graph_mode_when_disabled(monkeypatch):
    monkeypatch.setattr(session_controller_chat.settings, "SESSION_CONTROLLER_GRAPH_ENABLED", False)

    with pytest.raises(ValidationError) as exc_info:
        SessionControllerMessageRequest.model_validate(
            {
                "project_id": "p-1",
                "message": "现在需要我做什么？",
                "execution_mode": "graph",
            }
        )

    assert any(error["loc"][-1] == "execution_mode" for error in exc_info.value.errors())


def test_stream_message_passes_graph_mode_when_enabled(monkeypatch):
    stub = _StubSessionControllerService()
    monkeypatch.setattr(session_controller_chat, "session_controller_service", stub)
    monkeypatch.setattr(session_controller_chat, "_require_project_access", lambda project_id, current_user: None)
    monkeypatch.setattr(session_controller_chat, "sse_response_raw", lambda generator: list(generator))
    monkeypatch.setattr(session_controller_chat.settings, "SESSION_CONTROLLER_GRAPH_ENABLED", True)

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

    body = "".join(response)
    assert "event: graph" in body
    assert stub.last_stream_args == {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "user_message": "现在需要我做什么？",
        "execution_mode": "graph",
        "use_thinking_mode": False,
        "delegated_max_tool_call_rounds": 9,
    }
