"""
Unit tests for the requirement agent chat service.
"""

from __future__ import annotations

import json
import os
import sys
from collections.abc import Generator

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.agents.requirement_agent import (  # noqa: E402
    RequirementAgentChatService,
    _RuntimeGraphRecorder,
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


class _FakeChatStorage:
    def __init__(self):
        self.messages = []
        self.updated_sessions = []
        self.ensure_calls = []
        self.sessions = {}

    def _ensure_session_access(self, session_id: str, user_id: str):
        self.ensure_calls.append((session_id, user_id))
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

    def update_session(self, session_id: str, active_graph_id=..., title=None):
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
        self.updated_sessions.append({"session_id": session_id, "active_graph_id": session.get("active_graph_id")})
        return True

    def get_or_create_session(self, user_id: str, project_id: str | None = None):
        session = self.sessions.setdefault(
            "sess-1",
            {
                "session_id": "sess-1",
                "user_id": user_id,
                "project_id": project_id,
                "active_graph_id": None,
            },
        )
        session["user_id"] = user_id
        session["project_id"] = project_id
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
        return [{"type": "function", "function": {"name": "dummy", "parameters": {"type": "object"}}}]

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


def test_runtime_graph_recorder_persists_input_output_and_tool_calls():
    graph_service = _FakeExecutionGraphService()
    recorder = _RuntimeGraphRecorder(
        execution_graph_service=graph_service,
        project_id="p-1",
        user_id="u-1",
        requirement_id="r-1",
        session_id="sess-1",
        user_message="修改标题",
    )

    recorder.start_stage(
        node_key="requirements_agent_tool_loop_round_1",
        label="Tool Loop Round 1",
        node_type="llm",
        role_type="agent",
        container_key="requirements_agent",
        created_by="u-1",
        input_summary={"round": 1},
    )
    recorder.record_tool_call_result(
        "requirements_agent_tool_loop_round_1",
        created_by="u-1",
        tool_name="search_requirements",
        request_payload={"keyword": "登录"},
        result_payload={"total": 1, "items": [{"requirement_id": "r-1"}]},
    )
    recorder.complete_stage(
        "requirements_agent_tool_loop_round_1",
        created_by="u-1",
        output_summary={"finish_reason": "tool_calls"},
    )

    node = _find_node_by_key(graph_service, "requirements_agent_tool_loop_round_1")
    config = node["config_json"]

    assert config["run_status"] == "succeeded"
    assert config["input"][0]["kind"] == "task"
    assert config["output"] == {"finish_reason": "tool_calls"}
    assert config["tool_call_results"][0]["tool_name"] == "search_requirements"
    assert config["tool_call_results"][0]["request"] == {"keyword": "登录"}
    assert config["tool_call_results"][0]["result"]["items"][0]["requirement_id"] == "r-1"


def test_stream_requirement_agent_reply_list_then_text(monkeypatch):
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    tools = _FakeTools(
        [
            lambda _tool_name, _arguments, context: {
                "total": 2,
                "start_index": 1,
                "count": 2,
                "has_more": False,
                "items": [
                    {"requirement_id": "r-1", "title": "登录", "status": "draft", "priority": "high", "parent_id": None, "order_index": 1, "description_excerpt": "登录描述"},
                    {"requirement_id": "r-2", "title": "注册", "status": "draft", "priority": "medium", "parent_id": None, "order_index": 2, "description_excerpt": "注册描述"},
                ],
            }
        ]
    )
    service = RequirementAgentChatService(
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
                            "function": {"name": "list_requirements", "arguments": "{\"start_index\":1,\"count\":2}"},
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
                {"content": "我已经查看了项目需求。", "tool_calls": [], "finish_reason": "stop"},
            ]
        ),
    )
    monkeypatch.setattr(service, "_get_actor_manager", lambda: object())
    monkeypatch.setattr(service, "_stream_llm_reply", lambda **kwargs: _token_stream("已列出需求"))

    events = list(
        service.stream_requirement_agent_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="先列一下需求",
            requirement_id=None,
        )
    )

    assert events[-1]["event"] == "result"
    assert events[-1]["data"]["reply_text"] == "已列出需求"
    assert events[-1]["data"]["mode"] == "chat"

    round_node = _find_node_by_key(graph_service, "turn_1__requirements_agent_tool_loop_round_1")
    assert round_node["config_json"]["output"]["finish_reason"] == "tool_calls"
    assert round_node["config_json"]["tool_call_results"][0]["tool_name"] == "list_requirements"
    assert round_node["config_json"]["tool_call_results"][0]["result"]["total"] == 2
    assert graph_service.get_execution_graph("graph-1")["status"] == "succeeded"


def test_stream_requirement_agent_reply_multi_round_search_then_get_state(monkeypatch):
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    tools = _FakeTools(
        [
            lambda _tool_name, _arguments, context: (
                context.update({"resolved_requirement_id": "r-9"})
                or context.setdefault("resolved_requirement_ids", set()).add("r-9")
                or {
                    "total": 1,
                    "start_index": 1,
                    "count": 1,
                    "has_more": False,
                    "items": [
                        {"requirement_id": "r-9", "title": "登录性能", "status": "draft", "priority": "high", "parent_id": None, "order_index": 3, "description_excerpt": "3 秒内登录"},
                    ],
                }
            ),
            lambda _tool_name, _arguments, context: (
                context.update(
                    {
                        "resolved_requirement_id": "r-9",
                        "resolved_requirement_summary": {
                            "requirement_id": "r-9",
                            "version": 4,
                            "status": "draft",
                            "priority": "high",
                            "title": "登录性能",
                            "description": "系统在 3 秒内完成登录",
                            "acceptance_criteria": ["3 秒内展示首页"],
                        },
                    }
                )
                or context["resolved_requirement_summary"]
            ),
        ]
    )
    service = RequirementAgentChatService(
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
                            "function": {"name": "search_requirements", "arguments": "{\"keyword\":\"登录性能\"}"},
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc-2",
                            "type": "function",
                            "function": {"name": "get_requirement_state", "arguments": "{\"requirement_id\":\"r-9\"}"},
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
                {"content": "我已经确认这条需求当前是 draft。", "tool_calls": [], "finish_reason": "stop"},
            ]
        ),
    )
    monkeypatch.setattr(service, "_get_actor_manager", lambda: object())
    monkeypatch.setattr(service, "_stream_llm_reply", lambda **kwargs: _token_stream("已确认需求状态"))

    events = list(
        service.stream_requirement_agent_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="查一下登录性能需求状态",
            requirement_id=None,
        )
    )

    assert events[-1]["data"]["resolved_requirement_id"] == "r-9"
    assert _find_node_by_key(graph_service, "turn_1__requirements_agent_tool_loop_round_2")["config_json"]["tool_call_results"][0]["tool_name"] == "get_requirement_state"


def test_stream_requirement_agent_reply_update_records_write_result(monkeypatch):
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()

    def _update_handler(_tool_name, _arguments, context):
        context["write_performed"] = True
        context["resolved_requirement_id"] = "r-1"
        context["last_write_result"] = {
            "requirement_id": "r-1",
            "version": 6,
            "status": "draft",
            "priority": "high",
            "title": "新标题",
            "description": "旧描述",
            "acceptance_criteria": ["用户能完成登录"],
            "write_status": "success",
            "event_id": "evt-1",
            "applied_updates": {"title": "新标题"},
        }
        return context["last_write_result"]

    service = RequirementAgentChatService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=_FakeTools([_update_handler]),
        ai_proxy_client=_FakeAiProxy(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "type": "function",
                            "function": {"name": "update_requirement_content", "arguments": "{\"requirement_id\":\"r-1\",\"updates\":{\"title\":\"新标题\"}}"},
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
                {"content": "我已经完成更新。", "tool_calls": [], "finish_reason": "stop"},
            ]
        ),
    )
    monkeypatch.setattr(service, "_get_actor_manager", lambda: object())
    monkeypatch.setattr(service, "_stream_llm_reply", lambda **kwargs: _token_stream("已更新需求"))

    events = list(
        service.stream_requirement_agent_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="把标题改成新标题",
            requirement_id="r-1",
        )
    )

    assert events[-1]["data"]["mode"] == "requirement_update"
    assert events[-1]["data"]["write_result"]["version"] == 6
    round_node = _find_node_by_key(graph_service, "turn_1__requirements_agent_tool_loop_round_1")
    assert round_node["config_json"]["tool_call_results"][0]["tool_name"] == "update_requirement_content"
    assert round_node["config_json"]["tool_call_results"][0]["result"]["write_status"] == "success"


def test_stream_requirement_agent_reply_missing_requirement_id_clarifies(monkeypatch):
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()

    def _reject_update(_tool_name, _arguments, context):
        context["clarification_required"] = True
        raise ValueError("缺少明确 requirement_id：请先定位到唯一需求")

    service = RequirementAgentChatService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=_FakeTools([_reject_update]),
        ai_proxy_client=_FakeAiProxy(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "type": "function",
                            "function": {"name": "update_requirement_content", "arguments": "{\"requirement_id\":\"r-1\",\"updates\":{\"title\":\"新标题\"}}"},
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
                {"content": "请先告诉我要修改哪一条需求，或者直接提供需求 ID。", "tool_calls": [], "finish_reason": "stop"},
            ]
        ),
    )
    monkeypatch.setattr(service, "_get_actor_manager", lambda: object())
    monkeypatch.setattr(
        service,
        "_stream_llm_reply",
        lambda **kwargs: _token_stream("请先告诉我要修改哪一条需求，或者直接提供需求 ID。"),
    )

    events = list(
        service.stream_requirement_agent_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="帮我把需求改一下",
            requirement_id=None,
        )
    )

    assert events[-1]["data"]["mode"] == "clarification"
    assert graph_service.get_execution_graph("graph-1")["status"] == "suspended"
    round_node = _find_node_by_key(graph_service, "turn_1__requirements_agent_tool_loop_round_1")
    assert round_node["config_json"]["tool_call_results"][0]["result"]["is_error"] is True


def test_stream_requirement_agent_reply_fails_on_tool_round_limit(monkeypatch):
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    responses = []
    for index in range(6):
        responses.append(
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": f"tc-{index + 1}",
                        "type": "function",
                        "function": {"name": "list_requirements", "arguments": "{}"},
                    }
                ],
                "finish_reason": "tool_calls",
            }
        )

    service = RequirementAgentChatService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=_FakeTools(
            [lambda _tool_name, _arguments, _context: {"total": 0, "start_index": 1, "count": 0, "has_more": False, "items": []}] * 6
        ),
        ai_proxy_client=_FakeAiProxy(responses),
    )
    monkeypatch.setattr(service, "_get_actor_manager", lambda: object())

    events = list(
        service.stream_requirement_agent_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="一直调工具",
            requirement_id=None,
        )
    )

    assert events[-1]["event"] == "error"
    assert "工具调用轮数超过上限 6" in events[-1]["data"]["error"]
    assert graph_service.get_execution_graph("graph-1")["status"] == "failed"


def test_stream_requirement_agent_reply_creates_graph_chain_per_session(monkeypatch):
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    service = RequirementAgentChatService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=_FakeTools(
            [
                lambda _tool_name, _arguments, _context: {
                    "total": 1,
                    "start_index": 1,
                    "count": 1,
                    "has_more": False,
                    "items": [{"requirement_id": "r-1", "title": "登录", "status": "draft"}],
                },
                lambda _tool_name, _arguments, _context: {
                    "total": 1,
                    "start_index": 2,
                    "count": 1,
                    "has_more": False,
                    "items": [{"requirement_id": "r-2", "title": "注册", "status": "draft"}],
                },
            ]
        ),
        ai_proxy_client=_FakeAiProxy(
            [
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc-1",
                            "type": "function",
                            "function": {"name": "list_requirements", "arguments": "{\"start_index\":1,\"count\":1}"},
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
                {"content": "第一轮完成。", "tool_calls": [], "finish_reason": "stop"},
                {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "tc-2",
                            "type": "function",
                            "function": {"name": "list_requirements", "arguments": "{\"start_index\":2,\"count\":1}"},
                        }
                    ],
                    "finish_reason": "tool_calls",
                },
                {"content": "第二轮完成。", "tool_calls": [], "finish_reason": "stop"},
            ]
        ),
    )
    monkeypatch.setattr(service, "_get_actor_manager", lambda: object())
    monkeypatch.setattr(service, "_stream_llm_reply", lambda **kwargs: _token_stream("已完成"))

    first_events = list(
        service.stream_requirement_agent_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="先列一条",
            requirement_id=None,
        )
    )
    second_events = list(
        service.stream_requirement_agent_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="再列一条",
            requirement_id=None,
        )
    )

    assert first_events[-1]["data"]["graph_id"] == "graph-1"
    assert second_events[-1]["data"]["graph_id"] == "graph-2"
    assert graph_service.graph_counter == 2
    assert chat_storage.sessions["sess-1"]["active_graph_id"] == "graph-2"
    assert graph_service.get_execution_graph("graph-2")["meta_json"]["prev_graph_id"] == "graph-1"
    assert _find_node_by_key(graph_service, "turn_1__requirements_agent_tool_loop_round_1")
    assert [
        node
        for node in graph_service.nodes.values()
        if node["graph_id"] == "graph-2" and node["node_key"] == "turn_1__requirements_agent_tool_loop_round_1"
    ]
    second_turn_user_payload = json.loads(service.ai_proxy.calls[2]["messages"][1]["content"])
    assert second_turn_user_payload["historical_node_context"]
    assert second_turn_user_payload["historical_node_context"][-1]["node_key"] == "turn_1__conductor_reply"


def test_list_session_graph_chain_orders_by_prev_graph_id():
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    service = RequirementAgentChatService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=_FakeTools([]),
        ai_proxy_client=_FakeAiProxy([]),
    )

    chat_storage.sessions["sess-1"] = {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "active_graph_id": "graph-2",
    }

    graph_service.create_runtime_graph(
        project_id="p-1",
        name="g1",
        created_by="u-1",
        meta_json={"session_id": "sess-1", "prev_graph_id": None},
        status="succeeded",
    )
    graph_service.create_runtime_graph(
        project_id="p-1",
        name="g2",
        created_by="u-1",
        meta_json={"session_id": "sess-1", "prev_graph_id": "graph-1"},
        status="succeeded",
    )

    chain = service.list_session_graph_chain(session_id="sess-1", user_id="u-1")

    assert [item["graph"]["graph_id"] for item in chain["graphs"]] == ["graph-1", "graph-2"]
    assert chain["active_graph_id"] == "graph-2"
