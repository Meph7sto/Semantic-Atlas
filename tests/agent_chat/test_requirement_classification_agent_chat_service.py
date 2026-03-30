"""
Unit tests for the requirement classification agent chat service.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.agents.requirement_classification_agent import (  # noqa: E402
    RequirementClassificationAgentService,
    RequirementClassificationGraphRecorder,
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

    def list_runtime_graphs_by_session(self, session_id: str, project_id: str | None = None, include_deleted: bool = False):
        graphs = [
            graph
            for graph in self.graphs.values()
            if graph.get("meta_json", {}).get("session_id") == session_id
            and (project_id is None or graph.get("project_id") == project_id)
        ]
        if not include_deleted:
            graphs = [graph for graph in graphs if not graph.get("is_deleted")]
        graphs.sort(key=lambda item: item.get("graph_id"), reverse=True)
        return [dict(graph) for graph in graphs]

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
        subgraph_id: str = None,
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
            "subgraph_id": subgraph_id,
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


class _FakeChatStorage:
    def __init__(self):
        self.messages = []
        self.updated_sessions = []
        self.sessions = {}

    def _ensure_session_access(self, session_id: str, user_id: str):
        session = self.sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "user_id": user_id,
                "project_id": None,
                "active_graph_id": None,
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

    def update_session(self, session_id: str, active_graph_id=..., title=None, **kwargs):
        session = self.sessions.setdefault(
            session_id,
            {
                "session_id": session_id,
                "user_id": None,
                "project_id": None,
                "active_graph_id": None,
            },
        )
        if active_graph_id is not ...:
            session["active_graph_id"] = active_graph_id
        if title is not None:
            session["title"] = title
        session.update({k: v for k, v in kwargs.items() if v is not None})
        self.updated_sessions.append({"session_id": session_id, "active_graph_id": session.get("active_graph_id")})
        return True

    def get_or_create_session(self, user_id: str, project_id: str | None = None, agent_type: str | None = None):
        session = self.sessions.setdefault(
            "sess-1",
            {
                "session_id": "sess-1",
                "user_id": user_id,
                "project_id": project_id,
                "active_graph_id": None,
                "agent_type": agent_type,
            },
        )
        session["user_id"] = user_id
        session["project_id"] = project_id
        session["agent_type"] = agent_type
        return dict(session)

    def list_messages(self, session_id: str, user_id: str, limit: int = 100):
        return list(self.messages)[-limit:]


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
        return [
            {
                "type": "function",
                "function": {
                    "name": "classify_requirement",
                    "parameters": {"type": "object"},
                },
            }
        ]

    def execute(self, tool_name, arguments, context):
        self.calls.append((tool_name, arguments, dict(context)))
        if not self.handlers:
            raise AssertionError("unexpected tool execute")
        handler = self.handlers.pop(0)
        return handler(tool_name, arguments, context)


def _find_node_by_key(graph_service: _FakeExecutionGraphService, node_key: str) -> dict:
    for node in graph_service.nodes.values():
        if node["node_key"] == node_key:
            return node
    raise AssertionError(f"node not found: {node_key}")


def _token_stream(text: str) -> Generator[dict, None, str]:
    yield {"event": "token", "data": {"content": text}}
    return text


def _make_service():
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    tools = _FakeTools(
        [
            lambda _tool_name, _arguments, _context: {
                "requirement_id": "REQ-1",
                "title": "系统应支持批量导入需求数据",
                "level": "L2",
                "requirement_nature": "functional",
                "domain_tags": ["需求管理", "导入导出"],
                "priority_suggestion": "P2",
                "reasoning": "这是一个功能需求。",
                "evidence": ["title: 系统应支持批量导入需求数据"],
                "raw_classifier_label": "功能性需求",
            }
        ]
    )
    service = RequirementClassificationAgentService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=tools,
        ai_proxy_client=_FakeAiProxy(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "type": "function",
                            "function": {
                                "name": "classify_requirement",
                                "arguments": '{"requirement_id":"REQ-1"}',
                            },
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
                {
                    "content": "我已经完成需求分类。",
                    "tool_calls": [],
                    "finish_reason": "stop",
                },
            ]
        ),
    )
    return service, chat_storage, graph_service


def test_stream_classification_agent_reply_emits_graph_and_result_events(monkeypatch):
    service, chat_storage, graph_service = _make_service()
    monkeypatch.setattr(service, "_stream_llm_reply", lambda **kwargs: _token_stream("已完成分类"))

    events = list(
        service.stream_requirement_classification_agent_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="请分类 REQ-1",
            requirement_id="REQ-1",
        )
    )

    event_names = [event["event"] for event in events]
    assert "graph" in event_names
    assert event_names[-1] == "result"
    assert events[-1]["data"]["classification_result"]["requirement_id"] == "REQ-1"
    assert events[-1]["data"]["mode"] == "classification"
    assert chat_storage.messages[-1]["metadata"]["classification_result"]["level"] == "L2"

    graph = graph_service.get_execution_graph("graph-1")
    assert graph["status"] == "succeeded"
    assert graph["meta_json"]["classification_result"]["priority_suggestion"] == "P2"
    round_node = _find_node_by_key(graph_service, "turn_1__requirement_classification_agent_tool_loop_round_1")
    assert round_node["config_json"]["tool_call_results"][0]["tool_name"] == "classify_requirement"


def test_run_inline_tool_loop_returns_classification_summary():
    service, _, graph_service = _make_service()
    recorder = RequirementClassificationGraphRecorder(
        execution_graph_service=graph_service,
        project_id="p-1",
        user_id="u-1",
        requirement_id="REQ-1",
        session_id="sess-inline",
        user_message="分类 REQ-1",
    )

    result = service.run_inline_tool_loop(
        recorder=recorder,
        user_id="u-1",
        user_message="分类 REQ-1",
        project_id="p-1",
        requirement_id="REQ-1",
    )

    assert result["status"] == "success"
    assert result["resolved_requirement_id"] == "REQ-1"
    assert result["classification_result"]["level"] == "L2"
