"""
Tests for prompt payload format behavior in requirement agent chat service.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Generator

import pytest

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.agents.requirement_agent import (  # noqa: E402
    RequirementAgentChatService,
)


class _FakeExecutionGraphService:
    def __init__(self):
        self.graph_counter = 0
        self.container_counter = 0
        self.node_counter = 0
        self.edge_counter = 0
        self.graphs = {}
        self.containers = {}
        self.nodes = {}
        self.edges = {}

    def create_runtime_graph(
        self,
        project_id: str,
        name: str,
        description: str = "",
        created_by: str = "",
        meta_json=None,
        layout_json=None,
        status: str = "running",
    ):
        self.graph_counter += 1
        graph_id = f"graph-{self.graph_counter}"
        graph = {
            "graph_id": graph_id,
            "project_id": project_id,
            "name": name,
            "description": description,
            "graph_type": "agent_runtime_execution",
            "status": status,
            "meta_json": meta_json or {},
            "layout_json": layout_json,
            "created_by": created_by,
            "updated_by": created_by,
        }
        self.graphs[graph_id] = graph
        return dict(graph)

    def patch_graph_meta(self, graph_id: str, meta_patch, status: str | None = None, updated_by: str = ""):
        graph = self.graphs[graph_id]
        merged = dict(graph.get("meta_json") or {})
        merged.update(meta_patch or {})
        graph["meta_json"] = merged
        if status is not None:
            graph["status"] = status
        if updated_by:
            graph["updated_by"] = updated_by
        return dict(graph)

    def get_execution_graph(self, graph_id: str):
        graph = self.graphs.get(graph_id)
        return dict(graph) if graph else None

    def get_latest_runtime_graph_by_session(self, session_id: str, project_id: str | None = None, include_deleted: bool = False):
        graphs = [
            graph
            for graph in self.graphs.values()
            if graph.get("meta_json", {}).get("session_id") == session_id
            and (project_id is None or graph.get("project_id") == project_id)
        ]
        if not include_deleted:
            graphs = [graph for graph in graphs if not graph.get("is_deleted")]
        graphs.sort(key=lambda item: item.get("graph_id"))
        return dict(graphs[-1]) if graphs else None

    def get_graph_detail(self, graph_id: str):
        return {
            "graph": self.get_execution_graph(graph_id),
            "containers": [item for item in self.containers.values() if item["graph_id"] == graph_id],
            "nodes": [item for item in self.nodes.values() if item["graph_id"] == graph_id],
            "edges": [item for item in self.edges.values() if item["graph_id"] == graph_id],
        }

    def create_container(
        self,
        graph_id: str,
        container_key: str,
        label: str,
        role_type: str,
        config_json=None,
        order_index: int = 0,
        created_by: str = "",
    ):
        self.container_counter += 1
        container_id = f"container-{self.container_counter}"
        container = {
            "container_id": container_id,
            "graph_id": graph_id,
            "container_key": container_key,
            "label": label,
            "role_type": role_type,
            "config_json": config_json or {},
            "order_index": order_index,
            "created_by": created_by,
        }
        self.containers[container_id] = container
        return dict(container)

    def create_node(
        self,
        graph_id: str,
        node_key: str,
        label: str,
        node_type: str,
        role_type: str,
        container_id: str = None,
        config_json=None,
        input_schema_json=None,
        output_schema_json=None,
        order_index: int = 0,
        created_by: str = "",
    ):
        self.node_counter += 1
        node_id = f"node-{self.node_counter}"
        node = {
            "node_id": node_id,
            "graph_id": graph_id,
            "container_id": container_id,
            "node_key": node_key,
            "label": label,
            "node_type": node_type,
            "role_type": role_type,
            "config_json": config_json or {},
            "input_schema_json": input_schema_json,
            "output_schema_json": output_schema_json,
            "order_index": order_index,
            "created_by": created_by,
        }
        self.nodes[node_id] = node
        return dict(node)

    def get_node(self, node_id: str):
        return dict(self.nodes[node_id])

    def update_node(self, node_id: str, config_json=None, updated_by: str = "", **kwargs):
        node = self.nodes[node_id]
        if config_json is not None:
            node["config_json"] = config_json
        node.update({k: v for k, v in kwargs.items() if v is not None})
        if updated_by:
            node["updated_by"] = updated_by
        return dict(node)

    def create_edge(
        self,
        graph_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        label: str = None,
        condition_expr: str = None,
        config_json=None,
        order_index: int = 0,
        created_by: str = "",
    ):
        self.edge_counter += 1
        edge_id = f"edge-{self.edge_counter}"
        edge = {
            "edge_id": edge_id,
            "graph_id": graph_id,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "edge_type": edge_type,
            "label": label,
            "condition_expr": condition_expr,
            "config_json": config_json or {},
            "order_index": order_index,
            "created_by": created_by,
        }
        self.edges[edge_id] = edge
        return dict(edge)


class _FakeAiProxy:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def chat_completion_with_tools(self, **kwargs):
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("unexpected tool completion call")
        return self._responses.pop(0)


class _FakeTools:
    def __init__(self, handlers):
        self.handlers = list(handlers)
        self.calls = []

    def get_tools_list(self):
        return [{"type": "function", "function": {"name": "dummy", "parameters": {"type": "object"}}}]

    def execute(self, tool_name, arguments, context):
        self.calls.append((tool_name, arguments, dict(context)))
        if not self.handlers:
            raise AssertionError("unexpected tool execute")
        handler = self.handlers.pop(0)
        return handler(tool_name, arguments, context)


def _token_stream(text: str) -> Generator[dict, None, str]:
    yield {"event": "token", "data": {"content": text}}
    return text


class _PromptAwareFakeChatStorage:
    def __init__(self):
        self.sessions: dict[str, dict] = {}
        self.messages: list[dict] = []
        self.updated_sessions: list[dict] = []
        self._session_seq = 0

    def _ensure_session_access(self, session_id: str, user_id: str):
        session = self.sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "user_id": user_id,
                "project_id": None,
                "active_graph_id": None,
                "prompt_payload_format": "json",
            },
        )
        session["user_id"] = user_id
        return dict(session)

    def create_message(
        self,
        session_id: str,
        user_id: str | None,
        role: str,
        content: str,
        metadata=None,
        is_read: bool = False,
    ):
        message = {
            "message_id": f"msg-{len(self.messages) + 1}",
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "metadata": metadata or {},
            "is_read": is_read,
        }
        self.messages.append(message)
        return dict(message)

    def update_session(self, session_id: str, active_graph_id=..., title=None, prompt_payload_format=...):
        session = self.sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "user_id": None,
                "project_id": None,
                "active_graph_id": None,
                "prompt_payload_format": "json",
            },
        )
        if active_graph_id is not ...:
            session["active_graph_id"] = active_graph_id
        if title is not None:
            session["title"] = title
        if prompt_payload_format is not ...:
            session["prompt_payload_format"] = prompt_payload_format
        self.updated_sessions.append(dict(session))
        return True

    def get_or_create_session(self, user_id: str, project_id: str | None = None):
        session = self.sessions.setdefault(
            "sess-1",
            {
                "session_id": "sess-1",
                "user_id": user_id,
                "project_id": project_id,
                "active_graph_id": None,
                "prompt_payload_format": "json",
            },
        )
        session["user_id"] = user_id
        session["project_id"] = project_id
        return dict(session)

    def create_session(
        self,
        user_id: str,
        project_id: str | None = None,
        title: str | None = None,
        prompt_payload_format: str = "json",
    ):
        self._session_seq += 1
        session_id = f"sess-new-{self._session_seq}"
        session = {
            "session_id": session_id,
            "user_id": user_id,
            "project_id": project_id,
            "title": title,
            "active_graph_id": None,
            "prompt_payload_format": prompt_payload_format,
        }
        self.sessions[session_id] = dict(session)
        return dict(session)

    def list_messages(self, session_id: str, user_id: str, limit: int = 100):
        return list(self.messages)[-limit:]


def _build_service(chat_storage: _PromptAwareFakeChatStorage) -> RequirementAgentChatService:
    return RequirementAgentChatService(
        chat_storage=chat_storage,
        execution_graph_service=_FakeExecutionGraphService(),
        tools=_FakeTools([]),
        ai_proxy_client=_FakeAiProxy([]),
    )


@pytest.mark.parametrize(
    "prompt_payload_format, marker",
    [
        ("json", '"project_id": "p-1"'),
        ("yaml", "project_id: p-1"),
        ("markdown", "## 当前任务上下文"),
    ],
)
def test_build_tool_loop_user_message_supports_multiple_formats(prompt_payload_format, marker):
    service = _build_service(_PromptAwareFakeChatStorage())

    rendered = service._build_tool_loop_user_message(
        project_id="p-1",
        user_message="检查需求",
        requirement_id="r-1",
        historical_node_context=[{"node_key": "turn_1__user_input", "output_summary": {"accepted": True}}],
        prompt_payload_format=prompt_payload_format,
    )

    assert marker in rendered
    if prompt_payload_format == "json":
        parsed = json.loads(rendered)
        assert parsed["selected_requirement_id"] == "r-1"
    if prompt_payload_format == "markdown":
        assert "### historical_node_context" in rendered


@pytest.mark.parametrize(
    "prompt_payload_format, marker",
    [
        ("json", '"mode": "chat"'),
        ("yaml", "mode: chat"),
        ("markdown", "## 最终回复生成上下文"),
    ],
)
def test_build_final_reply_prompt_supports_multiple_formats(prompt_payload_format, marker):
    service = _build_service(_PromptAwareFakeChatStorage())

    _, prompt = service._build_final_reply_prompt(
        user_message="给我结果",
        tool_loop_reply="工具已经完成",
        mode="chat",
        context={
            "resolved_requirement_id": "r-1",
            "resolved_requirement_summary": {"title": "登录性能"},
            "tool_results": [{"tool_name": "get_requirement_state"}],
        },
        prompt_payload_format=prompt_payload_format,
    )

    assert marker in prompt
    if prompt_payload_format == "json":
        assert json.loads(prompt)["resolved_requirement_id"] == "r-1"


def test_create_or_get_session_can_update_prompt_payload_format():
    chat_storage = _PromptAwareFakeChatStorage()
    service = _build_service(chat_storage)

    session = service.create_or_get_session(
        user_id="u-1",
        project_id="p-1",
        prompt_payload_format="markdown",
    )

    assert session["prompt_payload_format"] == "markdown"
    assert chat_storage.sessions["sess-1"]["prompt_payload_format"] == "markdown"


def test_update_session_normalizes_prompt_payload_format():
    chat_storage = _PromptAwareFakeChatStorage()
    service = _build_service(chat_storage)
    chat_storage.sessions["sess-1"] = {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "active_graph_id": None,
        "prompt_payload_format": "json",
    }

    updated = service.update_session(
        session_id="sess-1",
        user_id="u-1",
        prompt_payload_format="YAML",
    )

    assert updated["prompt_payload_format"] == "yaml"
    assert chat_storage.sessions["sess-1"]["prompt_payload_format"] == "yaml"


def test_create_session_persists_prompt_payload_format():
    chat_storage = _PromptAwareFakeChatStorage()
    service = _build_service(chat_storage)

    session = service.create_session(
        user_id="u-1",
        project_id="p-1",
        title="会话A",
        prompt_payload_format="markdown",
    )

    assert session["prompt_payload_format"] == "markdown"
    assert chat_storage.sessions[session["session_id"]]["prompt_payload_format"] == "markdown"


def test_stream_requirement_agent_reply_uses_session_prompt_payload_format(monkeypatch):
    chat_storage = _PromptAwareFakeChatStorage()
    chat_storage.sessions["sess-1"] = {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "active_graph_id": None,
        "prompt_payload_format": "markdown",
    }
    graph_service = _FakeExecutionGraphService()
    ai_proxy = _FakeAiProxy(
        [
            {
                "content": "工具阶段已完成",
                "tool_calls": [],
                "finish_reason": "stop",
            }
        ]
    )
    service = RequirementAgentChatService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=_FakeTools([]),
        ai_proxy_client=ai_proxy,
    )
    monkeypatch.setattr(service, "_get_actor_manager", lambda: object())
    captured_final_prompt = {}

    def _capture_stream_llm_reply(**kwargs):
        captured_final_prompt["prompt"] = kwargs.get("prompt", "")
        return _token_stream("最终回复")

    monkeypatch.setattr(service, "_stream_llm_reply", _capture_stream_llm_reply)

    events = list(
        service.stream_requirement_agent_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="查询当前需求",
            requirement_id=None,
        )
    )

    tool_loop_user_message = ai_proxy.calls[0]["messages"][1]["content"]
    assert tool_loop_user_message.startswith("## 当前任务上下文")
    assert "### historical_node_context" in tool_loop_user_message
    assert captured_final_prompt["prompt"].startswith("## 最终回复生成上下文")
    assert events[-1]["event"] == "result"
    assert events[-1]["data"]["reply_text"] == "最终回复"
