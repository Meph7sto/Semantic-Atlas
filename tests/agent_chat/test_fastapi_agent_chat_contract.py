"""
FastAPI agent chat router contract tests.
"""


import httpx
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError


from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import agent_chat


class _StubAgentChatService:
    def __init__(self):
        self.last_session_args = None
        self.last_messages_args = None
        self.last_graph_chain_args = None
        self.last_stream_args = None
        self.last_graph_id = None

    def create_or_get_session(self, user_id: str, project_id: str | None = None):
        self.last_session_args = (user_id, project_id)
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

    def stream_requirement_agent_reply(self, **kwargs):
        self.last_stream_args = kwargs
        yield {"event": "graph", "data": {"graph_id": "graph-1"}}
        yield {"event": "token", "data": {"content": "ok"}}
        yield {"event": "result", "data": {"graph_id": "graph-1", "reply_text": "ok", "write_result": None, "mode": "chat"}}

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


def _build_app():
    app = build_test_app(agent_chat.router)
    app.dependency_overrides[get_current_user] = lambda: {"user_id": "u-1", "role": "member"}
    return app


async def test_create_session_uses_current_user(monkeypatch):
    stub = _StubAgentChatService()
    monkeypatch.setattr(agent_chat, "requirement_agent_chat_service", stub)
    monkeypatch.setattr(agent_chat, "_require_project_access", lambda project_id, current_user: None)

    async with async_client(_build_app()) as client:
        response = await client.post("/api/v2/agent-chat/sessions", json={"project_id": "p-1"})

    assert response.status_code == 200
    assert response.json()["session_id"] == "sess-1"
    assert stub.last_session_args == ("u-1", "p-1")


async def test_list_messages_returns_router_shape(monkeypatch):
    stub = _StubAgentChatService()
    monkeypatch.setattr(agent_chat, "requirement_agent_chat_service", stub)

    async with async_client(_build_app()) as client:
        response = await client.get("/api/v2/agent-chat/sessions/sess-1/messages?limit=20")

    assert response.status_code == 200
    assert response.json()["messages"][0]["message_id"] == "m-1"
    assert stub.last_messages_args == ("sess-1", "u-1", 20)


async def test_get_session_graph_chain_returns_router_shape(monkeypatch):
    stub = _StubAgentChatService()
    monkeypatch.setattr(agent_chat, "requirement_agent_chat_service", stub)
    monkeypatch.setattr(agent_chat, "_require_project_access", lambda project_id, current_user: None)

    async with async_client(_build_app()) as client:
        response = await client.get("/api/v2/agent-chat/sessions/sess-1/graph-chain")

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "sess-1"
    assert body["active_graph_id"] == "graph-2"
    assert body["graphs"][1]["graph"]["meta_json"]["prev_graph_id"] == "graph-1"
    assert stub.last_graph_chain_args == ("sess-1", "u-1")


async def test_stream_message_returns_sse_events(monkeypatch):
    stub = _StubAgentChatService()
    monkeypatch.setattr(agent_chat, "requirement_agent_chat_service", stub)
    monkeypatch.setattr(agent_chat, "_require_project_access", lambda project_id, current_user: None)

    async with async_client(_build_app()) as client:
        response = await client.post(
            "/api/v2/agent-chat/sessions/sess-1/messages/stream",
            json={"project_id": "p-1", "requirement_id": "r-1", "message": "修改标题"},
        )

    assert response.status_code == 200
    assert "event: graph" in response.text
    assert "event: token" in response.text
    assert "graph-1" in response.text
    assert stub.last_stream_args == {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "user_message": "修改标题",
        "requirement_id": "r-1",
    }


async def test_get_graph_detail_returns_detail(monkeypatch):
    stub = _StubAgentChatService()
    monkeypatch.setattr(agent_chat, "requirement_agent_chat_service", stub)
    monkeypatch.setattr(agent_chat, "_require_project_access", lambda project_id, current_user: None)

    async with async_client(_build_app()) as client:
        response = await client.get("/api/v2/agent-chat/graphs/graph-1/detail")

    assert response.status_code == 200
    assert response.json()["graph"]["graph_id"] == "graph-1"
    assert stub.last_graph_id == "graph-1"
