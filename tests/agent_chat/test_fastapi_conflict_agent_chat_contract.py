"""Conflict agent chat request contract tests."""

import pytest
from pydantic import ValidationError

from backend_business.api.routers import conflict_agent_chat
from backend_business.api.routers.conflict_agent_chat import ConflictAgentMessageRequest


class _StubConflictAgentChatService:
    def __init__(self):
        self.last_stream_args = None

    def stream_conflict_agent_reply(self, **kwargs):
        self.last_stream_args = kwargs
        yield {"event": "graph", "data": {"graph_id": "graph-1"}}
        yield {"event": "result", "data": {"graph_id": "graph-1", "status": "succeeded", "reply_text": "ok"}}


def test_message_request_rejects_template_graph_id():
    try:
        ConflictAgentMessageRequest.model_validate(
            {
                "project_id": "p-1",
                "message": "请检测 r-1 和 r-2 的冲突",
                "execution_mode": "graph",
                "template_graph_id": "tpl-conflict-graph",
            }
        )
    except ValidationError as exc:
        detail = exc.errors()
    else:  # pragma: no cover
        raise AssertionError("template_graph_id 应被严格拒绝")

    assert any(error["loc"][-1] == "template_graph_id" for error in detail)


def test_message_request_rejects_classic_mode():
    with pytest.raises(ValidationError) as exc_info:
        ConflictAgentMessageRequest.model_validate(
            {
                "project_id": "p-1",
                "message": "请检测 r-1 和 r-2 的冲突",
                "execution_mode": "classic",
            }
        )

    assert any(error["loc"][-1] == "execution_mode" for error in exc_info.value.errors())


def test_message_request_defaults_to_graph():
    payload = ConflictAgentMessageRequest.model_validate(
        {
            "project_id": "p-1",
            "message": "请检测 r-1 和 r-2 的冲突",
        }
    )

    assert payload.execution_mode == "graph"


def test_stream_message_passes_graph_mode_without_template_override(monkeypatch):
    stub = _StubConflictAgentChatService()
    monkeypatch.setattr(conflict_agent_chat, "conflict_detection_agent_service", stub)
    monkeypatch.setattr(conflict_agent_chat, "_require_project_access", lambda project_id, current_user: None)
    monkeypatch.setattr(conflict_agent_chat, "sse_response_raw", lambda generator: list(generator))

    response = conflict_agent_chat.stream_message(
        session_id="sess-1",
        payload=ConflictAgentMessageRequest.model_validate(
            {
                "project_id": "p-1",
                "message": "请检测 r-1 和 r-2 的冲突",
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
        "user_message": "请检测 r-1 和 r-2 的冲突",
        "execution_mode": "graph",
    }
