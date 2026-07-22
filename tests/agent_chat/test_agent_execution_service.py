"""Tests for the shared agent execution application boundary."""

from __future__ import annotations

import os

os.environ["SKIP_DB_INIT"] = "1"

from backend_business.services.agent.runtime.agent_definition import AgentDefinition
from backend_business.services.agent.runtime.agent_execution_service import (
    AgentExecutionService,
)


class _Storage:
    def __init__(self) -> None:
        self.sessions = {
            "session-1": {
                "session_id": "session-1",
                "user_id": "user-1",
                "active_graph_id": None,
            }
        }
        self.messages: list[dict] = []
        self.updates: list[dict] = []

    def _ensure_session_access(self, *, session_id: str, user_id: str) -> dict:
        session = self.sessions[session_id]
        assert session["user_id"] == user_id
        return dict(session)

    def create_message(self, **values) -> dict:
        message = {"message_id": f"message-{len(self.messages) + 1}", **values}
        self.messages.append(message)
        return message

    def update_session(self, *, session_id: str, **values) -> bool:
        self.updates.append({"session_id": session_id, **values})
        self.sessions[session_id].update(values)
        return True


class _SessionGraphStore:
    def resolve_session_graph_target(self, *, session: dict, project_id: str) -> dict:
        assert session["session_id"] == "session-1"
        assert project_id == "project-1"
        return {"graph_id": None, "prev_graph_id": "graph-previous"}


class _Recorder:
    def __init__(self, **values) -> None:
        self.values = values
        self.graph_id = values["graph_id"] or "graph-new"


def _returning_generator():
    yield {"event": "delta", "data": {"text": "hello"}}
    return {"status": "done"}


def test_agent_execution_service_owns_common_turn_lifecycle():
    storage = _Storage()
    service = AgentExecutionService(
        definition=AgentDefinition(
            agent_type="example_agent",
            container_key="example_agent",
            label="Example Agent",
        ),
        chat_storage=storage,
        session_graph_store=_SessionGraphStore(),
    )

    turn = service.begin_turn(
        session_id="session-1",
        user_id="user-1",
        project_id="project-1",
        user_message="hello",
        user_metadata={"model": "test-model"},
    )
    recorder = service.create_recorder(
        turn=turn,
        recorder_factory=_Recorder,
        domain_value="value",
    )

    stream = service.stream_generator(_returning_generator())
    assert next(stream) == {"event": "delta", "data": {"text": "hello"}}
    try:
        next(stream)
    except StopIteration as stop:
        assert stop.value == {"status": "done"}
    else:
        raise AssertionError("stream_generator did not preserve the return value")

    assistant = service.persist_assistant(
        turn=turn,
        content="done",
        metadata={"graph_id": recorder.graph_id},
    )
    error = service.persist_error(
        turn=turn,
        graph_id=recorder.graph_id,
        error="failed",
        metadata={"kind": "test"},
    )

    assert turn.definition.agent_type == "example_agent"
    assert turn.user_record["metadata"] == {"model": "test-model"}
    assert recorder.values["prev_graph_id"] == "graph-previous"
    assert recorder.values["domain_value"] == "value"
    assert storage.updates[-1] == {
        "session_id": "session-1",
        "active_graph_id": "graph-new",
    }
    assert assistant["role"] == "assistant"
    assert error["metadata"] == {
        "error": True,
        "graph_id": "graph-new",
        "kind": "test",
    }
