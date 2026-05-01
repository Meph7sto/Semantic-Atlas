"""
Requirement classification agent chat router contract tests.
"""

from backend_business.api.routers import requirement_classification_agent_chat
from backend_business.api.routers.schemas.agent_chat_schemas import (
    AgentChatMessageRequest,
    AgentChatSessionRequest,
)


class _StubClassificationAgentChatService:
    def __init__(self):
        self.last_session_args = None
        self.last_messages_args = None
        self.last_graph_chain_args = None
        self.last_stream_args = None
        self.last_graph_id = None

    def create_or_get_session(self, user_id: str, project_id: str | None = None, **kwargs):
        self.last_session_args = {
            "user_id": user_id,
            "project_id": project_id,
            **kwargs,
        }
        return {"session_id": "sess-1", "project_id": project_id, "user_id": user_id}

    def list_messages(self, *, session_id: str, user_id: str, limit: int = 100):
        self.last_messages_args = (session_id, user_id, limit)
        return [{"message_id": "m-1", "role": "assistant", "content": "hello"}]

    def list_session_graph_chain(self, *, session_id: str, user_id: str):
        self.last_graph_chain_args = (session_id, user_id)
        return {
            "session_id": session_id,
            "active_graph_id": "graph-2",
            "graphs": [
                {
                    "graph": {"graph_id": "graph-1", "project_id": "p-1", "status": "succeeded"},
                    "containers": [],
                    "nodes": [],
                    "edges": [],
                },
                {
                    "graph": {
                        "graph_id": "graph-2",
                        "project_id": "p-1",
                        "status": "running",
                        "meta_json": {"prev_graph_id": "graph-1"},
                    },
                    "containers": [],
                    "nodes": [],
                    "edges": [],
                },
            ],
        }

    def stream_requirement_classification_agent_reply(self, **kwargs):
        self.last_stream_args = kwargs
        yield {"event": "graph", "data": {"graph_id": "graph-1"}}
        yield {"event": "token", "data": {"content": "ok"}}
        yield {
            "event": "result",
            "data": {
                "graph_id": "graph-1",
                "reply_text": "ok",
                "classification_result": {"requirement_id": "REQ-1"},
                "resolved_requirement_id": "REQ-1",
                "mode": "classification",
            },
        }

    def get_graph(self, graph_id: str):
        self.last_graph_id = graph_id
        return {"graph_id": graph_id, "project_id": "p-1", "status": "running"}

    def get_graph_detail(self, graph_id: str):
        self.last_graph_id = graph_id
        return {
            "graph": {"graph_id": graph_id, "project_id": "p-1", "status": "running"},
            "containers": [],
            "nodes": [],
            "edges": [],
        }


def test_create_session_uses_current_user(monkeypatch):
    stub = _StubClassificationAgentChatService()
    monkeypatch.setattr(
        requirement_classification_agent_chat,
        "requirement_classification_agent_service",
        stub,
    )
    monkeypatch.setattr(
        requirement_classification_agent_chat,
        "_require_project_access",
        lambda project_id, current_user: None,
    )

    response = requirement_classification_agent_chat.create_or_get_session(
        AgentChatSessionRequest(project_id="p-1"),
        current_user={"user_id": "u-1", "role": "member"},
    )

    assert response["session_id"] == "sess-1"
    assert stub.last_session_args["user_id"] == "u-1"
    assert stub.last_session_args["project_id"] == "p-1"


def test_list_messages_returns_router_shape(monkeypatch):
    stub = _StubClassificationAgentChatService()
    monkeypatch.setattr(
        requirement_classification_agent_chat,
        "requirement_classification_agent_service",
        stub,
    )

    response = requirement_classification_agent_chat.list_messages(
        session_id="sess-1",
        limit=20,
        current_user={"user_id": "u-1", "role": "member"},
    )

    assert response["messages"][0]["message_id"] == "m-1"
    assert stub.last_messages_args == ("sess-1", "u-1", 20)


def test_get_session_graph_chain_returns_router_shape(monkeypatch):
    stub = _StubClassificationAgentChatService()
    monkeypatch.setattr(
        requirement_classification_agent_chat,
        "requirement_classification_agent_service",
        stub,
    )

    response = requirement_classification_agent_chat.get_session_graph_chain(
        session_id="sess-1",
        current_user={"user_id": "u-1", "role": "member"},
    )

    assert response["session_id"] == "sess-1"
    assert response["active_graph_id"] == "graph-2"
    assert response["graphs"][1]["graph"]["meta_json"]["prev_graph_id"] == "graph-1"
    assert stub.last_graph_chain_args == ("sess-1", "u-1")


def test_stream_message_passes_requirement_id(monkeypatch):
    stub = _StubClassificationAgentChatService()
    monkeypatch.setattr(
        requirement_classification_agent_chat,
        "requirement_classification_agent_service",
        stub,
    )
    monkeypatch.setattr(
        requirement_classification_agent_chat,
        "_require_project_access",
        lambda project_id, current_user: None,
    )
    monkeypatch.setattr(
        requirement_classification_agent_chat,
        "sse_response_raw",
        lambda generator: list(generator),
    )

    response = requirement_classification_agent_chat.stream_message(
        session_id="sess-1",
        payload=AgentChatMessageRequest.model_validate(
            {"project_id": "p-1", "message": "请分类", "requirement_id": "REQ-1"}
        ),
        current_user={"user_id": "u-1", "role": "member"},
    )

    body = "".join(response)
    assert "event: graph" in body
    assert "event: token" in body
    assert stub.last_stream_args == {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "user_message": "请分类",
        "requirement_id": "REQ-1",
        "model": "deepseek-v4-pro",
        "use_thinking_mode": True,
    }


def test_get_graph_detail_returns_detail(monkeypatch):
    stub = _StubClassificationAgentChatService()
    monkeypatch.setattr(
        requirement_classification_agent_chat,
        "requirement_classification_agent_service",
        stub,
    )
    monkeypatch.setattr(
        requirement_classification_agent_chat,
        "_require_project_access",
        lambda project_id, current_user: None,
    )

    response = requirement_classification_agent_chat.get_graph_detail(
        graph_id="graph-1",
        current_user={"user_id": "u-1", "role": "member"},
    )

    assert response["graph"]["graph_id"] == "graph-1"
    assert stub.last_graph_id == "graph-1"
