"""
Unit tests for the session controller service scratchpad memory behavior.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Generator

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import pytest

from backend_business.config import settings  # noqa: E402
from backend_business.services.agent.agents.session_controller import (  # noqa: E402
    SessionControllerService,
)
from backend_business.services.agent.agents.session_controller.tools import (  # noqa: E402
    SessionControllerTools,
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

    def list_messages(self, session_id: str, user_id: str, limit: int = 100):
        return list(self.messages)[-limit:]


class _FakeAiProxy:
    def __init__(self, tool_responses=None, summary_responses=None):
        self._tool_responses = list(tool_responses or [])
        self._summary_responses = list(summary_responses or [])
        self.tool_calls = []
        self.summary_calls = []

    def chat_completion_with_tools(self, **kwargs):
        self.tool_calls.append(kwargs)
        if not self._tool_responses:
            raise AssertionError("unexpected tool completion call")
        return self._tool_responses.pop(0)

    def chat_completion(self, **kwargs):
        self.summary_calls.append(kwargs)
        if not self._summary_responses:
            return {"content": ""}
        return self._summary_responses.pop(0)


class _FakeTools:
    def __init__(self, handlers):
        self.handlers = list(handlers)

    def get_tools_list(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "invoke_requirement_agent",
                    "parameters": {"type": "object"},
                },
            }
        ]

    def execute(self, tool_name, arguments, context):
        if not self.handlers:
            raise AssertionError("unexpected tool execute")
        handler = self.handlers.pop(0)
        return handler(tool_name, arguments, context)


def _token_stream(text: str) -> Generator[dict, None, str]:
    yield {"event": "token", "data": {"content": text}}
    return text


def test_stream_session_controller_reply_persists_turn_summary_to_scratchpad(monkeypatch):
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    tools = _FakeTools(
        [
            lambda _tool_name, _arguments, context: (
                context.update(
                    {
                        "resolved_requirement_id": "REQ-1",
                        "last_write_result": {
                            "requirement_id": "REQ-1",
                            "version": 3,
                            "priority": "high",
                            "title": "actor视觉测试",
                            "applied_updates": {"priority": "high"},
                        },
                    }
                )
                or {"status": "success", "reply": "已修改", "resolved_requirement_id": "REQ-1", "write_result": context["last_write_result"]}
            )
        ]
    )
    ai_proxy = _FakeAiProxy(
        tool_responses=[
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc-1",
                        "type": "function",
                        "function": {
                            "name": "invoke_requirement_agent",
                            "arguments": "{\"task_description\":\"把 actor视觉测试 的优先级设置为高\"}",
                        },
                    }
                ],
                "finish_reason": "tool_calls",
            },
            {"content": "需求已定位并更新。", "tool_calls": [], "finish_reason": "stop"},
        ],
        summary_responses=[
            {"content": "本轮锁定需求 REQ-1，并将 actor视觉测试 的优先级更新为高，可在下一轮继续直接引用该需求。"},
        ],
    )
    service = SessionControllerService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=tools,
        ai_proxy_client=ai_proxy,
    )
    monkeypatch.setattr(service, "_stream_llm_reply", lambda **kwargs: _token_stream("已将优先级设为高"))

    events = list(
        service.stream_session_controller_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="把 actor视觉测试 的优先级设置为高",
            execution_mode="classic",
        )
    )

    assert events[-1]["event"] == "result"
    graph = graph_service.get_execution_graph("graph-1")
    meta = graph["meta_json"]
    assert meta["resolved_requirement_id"] == "REQ-1"
    assert len(meta["scratchpad_entries"]) == 1
    entry = meta["scratchpad_entries"][0]
    assert entry["entry_type"] == "note"
    assert entry["content"]["resolved_requirement_id"] == "REQ-1"
    assert "actor视觉测试" in entry["content"]["summary"]


def test_stream_session_controller_reply_inherits_scratchpad_into_next_turn_prompt(monkeypatch):
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    previous_graph = graph_service.create_runtime_graph(
        project_id="p-1",
        name="previous",
        created_by="u-1",
        status="succeeded",
        meta_json={
            "session_id": "sess-1",
            "resolved_requirement_id": "REQ-9",
            "scratchpad_entries": [
                {
                    "entry_type": "note",
                    "content": {
                        "turn": 1,
                        "summary": "当前焦点需求是 REQ-9，对应 actor视觉测试。",
                        "resolved_requirement_id": "REQ-9",
                    },
                    "source_subgraph": "session_turn_1",
                    "readonly": True,
                }
            ],
        },
    )
    chat_storage.sessions["sess-1"] = {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "active_graph_id": previous_graph["graph_id"],
    }
    ai_proxy = _FakeAiProxy(
        tool_responses=[
            {"content": "我会沿用上轮焦点需求继续处理。", "tool_calls": [], "finish_reason": "stop"},
        ],
        summary_responses=[
            {"content": "继续沿用 REQ-9 作为当前焦点需求。"},
        ],
    )
    service = SessionControllerService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=_FakeTools([]),
        ai_proxy_client=ai_proxy,
    )
    monkeypatch.setattr(service, "_stream_llm_reply", lambda **kwargs: _token_stream("继续处理 REQ-9"))

    events = list(
        service.stream_session_controller_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="把他的优先级设置为高",
            execution_mode="classic",
        )
    )

    assert events[-1]["event"] == "result"
    system_prompt = ai_proxy.tool_calls[0]["messages"][0]["content"]
    assert "actor视觉测试" in system_prompt
    current_graph = graph_service.get_execution_graph("graph-2")
    assert current_graph["meta_json"]["resolved_requirement_id"] == "REQ-9"


def test_stream_session_controller_reply_consumes_structured_loop_result(monkeypatch):
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    ai_proxy = _FakeAiProxy(
        tool_responses=[
            {
                "content": (
                    '{"mode":"direct_reply","tool_loop_reply":"已确认当前无需调用工具。",'
                    '"assistant_reply_seed":"当前没有需要进一步处理的事项。",'
                    '"should_suspend":false,"approval_pending":false}'
                ),
                "tool_calls": [],
                "finish_reason": "stop",
            },
        ],
        summary_responses=[
            {"content": "本轮无需调度子 Agent，直接完成答复。"},
        ],
    )
    service = SessionControllerService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=_FakeTools([]),
        ai_proxy_client=ai_proxy,
    )
    monkeypatch.setattr(service, "_stream_llm_reply", lambda **kwargs: _token_stream("当前没有需要进一步处理的事项。"))

    events = list(
        service.stream_session_controller_reply(
            session_id="sess-structured-1",
            user_id="u-1",
            project_id="p-1",
            user_message="现在系统需要我做什么？",
            execution_mode="classic",
        )
    )

    assert events[-1]["event"] == "result"
    assert events[-1]["data"]["mode"] == "direct_reply"
    assert events[-1]["data"]["reply_text"] == "当前没有需要进一步处理的事项。"
    graph = graph_service.get_execution_graph("graph-1")
    assert graph["status"] == "succeeded"
    assert graph["meta_json"]["session_controller_mode"] == "direct_reply"


def test_stream_session_controller_reply_waits_for_structured_controller_result_after_delegation(monkeypatch):
    class _FakeRequirementsService:
        pass

    class _FakeRequirementAgentService:
        def run_inline_tool_loop(self, **kwargs):
            return {
                "status": "success",
                "tool_loop_reply": "已读取需求详情",
                "resolved_requirement_id": "REQ-9",
                "write_result": None,
                "approval_pending": False,
                "approval_result": None,
            }

        def stream_inline_tool_loop(self, **kwargs):
            yield {
                "event": "stage",
                "data": {
                    "graph_id": "graph-1",
                    "node_key": "turn_1__req_agent_1_tool_loop_round_1",
                    "status": "succeeded",
                },
            }
            return self.run_inline_tool_loop(**kwargs)

    class _FakeConflictAgentService:
        def run_inline_tool_loop(self, **kwargs):
            return {"status": "success", "tool_loop_reply": "冲突检测完成"}

        def stream_inline_tool_loop(self, **kwargs):
            return self.run_inline_tool_loop(**kwargs)

    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    ai_proxy = _FakeAiProxy(
        tool_responses=[
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc-1",
                        "type": "function",
                        "function": {
                            "name": "invoke_requirement_agent",
                            "arguments": "{\"task_description\":\"给我一个需求的完整信息\"}",
                        },
                    }
                ],
                "finish_reason": "tool_calls",
            },
            {
                "content": (
                    '{"mode":"delegate_requirement","tool_loop_reply":"已读取需求详情并准备向用户汇总。",'
                    '"assistant_reply_seed":"这是一个需求的完整信息摘要",'
                    '"delegated_agent":"requirement_agent",'
                    '"resolved_requirement_id":"REQ-9",'
                    '"dispatched_agents":["requirement_agent"],'
                    '"should_suspend":false,"approval_pending":false}'
                ),
                "tool_calls": [],
                "finish_reason": "stop",
            },
        ],
        summary_responses=[
            {"content": "当前焦点是 REQ-9。"},
        ],
    )
    tools = SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=_FakeRequirementAgentService(),
        conflict_agent_service=_FakeConflictAgentService(),
    )
    service = SessionControllerService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=tools,
        ai_proxy_client=ai_proxy,
    )
    monkeypatch.setattr(
        service,
        "_stream_llm_reply",
        lambda **kwargs: _token_stream("这是一个需求的完整信息摘要"),
    )

    events = list(
        service.stream_session_controller_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="随便给我一个需求的完整信息",
            execution_mode="classic",
        )
    )

    assert events[-1]["event"] == "result"
    assert len(ai_proxy.tool_calls) == 2
    assert events[-1]["data"]["mode"] == "delegate_requirement"
    assert events[-1]["data"]["reply_text"] == "这是一个需求的完整信息摘要"


def test_stream_session_controller_reply_suspends_on_delegated_clarification(monkeypatch):
    class _FakeRequirementsService:
        pass

    class _FakeRequirementAgentService:
        def run_inline_tool_loop(self, **kwargs):
            return {
                "status": "success",
                "tool_loop_reply": "我发现两条标题完全相同的需求，请确认要修改哪一条。",
                "resolved_requirement_id": None,
                "write_result": None,
                "mode": "clarification",
                "clarification_required": True,
                "approval_pending": False,
                "approval_result": None,
            }

        def stream_inline_tool_loop(self, **kwargs):
            yield {
                "event": "stage",
                "data": {
                    "graph_id": "graph-1",
                    "node_key": "turn_1__req_agent_1_tool_loop_round_1",
                    "status": "succeeded",
                },
            }
            return self.run_inline_tool_loop(**kwargs)

    class _FakeConflictAgentService:
        def run_inline_tool_loop(self, **kwargs):
            return {"status": "success", "tool_loop_reply": "冲突检测完成"}

        def stream_inline_tool_loop(self, **kwargs):
            return self.run_inline_tool_loop(**kwargs)

    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    ai_proxy = _FakeAiProxy(
        tool_responses=[
            {
                "content": "",
                "tool_calls": [
                    {
                        "id": "tc-1",
                        "type": "function",
                        "function": {
                            "name": "invoke_requirement_agent",
                            "arguments": "{\"task_description\":\"把这条需求优先级改成高\"}",
                        },
                    }
                ],
                "finish_reason": "tool_calls",
            },
            {
                "content": (
                    '{"mode":"clarify","tool_loop_reply":"我发现两条标题完全相同的需求，请确认要修改哪一条。",'
                    '"clarification_question":"我发现两条标题完全相同的需求，请确认要修改哪一条。",'
                    '"delegated_agent":"requirement_agent",'
                    '"dispatched_agents":["requirement_agent"],'
                    '"should_suspend":true,"suspend_reason":"clarification","approval_pending":false}'
                ),
                "tool_calls": [],
                "finish_reason": "stop",
            },
        ],
        summary_responses=[
            {"content": "当前待用户确认具体要修改的需求。"},
        ],
    )
    tools = SessionControllerTools(
        requirements_service=_FakeRequirementsService(),
        requirement_agent_service=_FakeRequirementAgentService(),
        conflict_agent_service=_FakeConflictAgentService(),
    )
    service = SessionControllerService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        tools=tools,
        ai_proxy_client=ai_proxy,
    )

    def _should_not_be_called(**kwargs):
        raise AssertionError("clarification branch should return delegated reply directly")

    monkeypatch.setattr(service, "_stream_llm_reply", _should_not_be_called)

    events = list(
        service.stream_session_controller_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="把这条需求优先级改成高",
            execution_mode="classic",
        )
    )

    assert events[-1]["event"] == "result"
    assert len(ai_proxy.tool_calls) == 2
    assert events[-1]["data"]["reply_text"] == "我发现两条标题完全相同的需求，请确认要修改哪一条。"
    graph = graph_service.get_execution_graph("graph-1")
    assert graph["status"] == "suspended"
    assert graph["meta_json"]["awaiting_user_input"] is True


def test_stream_session_controller_reply_rejects_graph_mode_when_disabled(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_CONTROLLER_GRAPH_ENABLED", False)
    service = SessionControllerService(
        chat_storage=_FakeChatStorage(),
        execution_graph_service=_FakeExecutionGraphService(),
        tools=_FakeTools([]),
        ai_proxy_client=_FakeAiProxy(),
    )

    with pytest.raises(ValueError, match="execution_mode=graph 当前未启用"):
        list(
            service.stream_session_controller_reply(
                session_id="sess-1",
                user_id="u-1",
                project_id="p-1",
                user_message="测试 graph",
                execution_mode="graph",
            )
        )


def test_stream_session_controller_reply_defaults_to_graph_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "SESSION_CONTROLLER_GRAPH_ENABLED", True)
    service = SessionControllerService(
        chat_storage=_FakeChatStorage(),
        execution_graph_service=_FakeExecutionGraphService(),
        tools=_FakeTools([]),
        ai_proxy_client=_FakeAiProxy(),
    )
    captured = {}

    def _fake_graph_reply(**kwargs):
        captured.update(kwargs)
        yield {"event": "result", "data": {"graph_id": "graph-1", "mode": "direct_reply"}}

    monkeypatch.setattr(service, "stream_graph_executor_reply", _fake_graph_reply)

    events = list(
        service.stream_session_controller_reply(
            session_id="sess-1",
            user_id="u-1",
            project_id="p-1",
            user_message="测试默认 graph",
        )
    )

    assert events[-1]["event"] == "result"
    assert captured == {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "user_message": "测试默认 graph",
        "delegated_max_tool_call_rounds": 15,
        "skip_user_message_creation": False,
    }


def test_stream_session_controller_reply_rejects_unknown_execution_mode():
    service = SessionControllerService(
        chat_storage=_FakeChatStorage(),
        execution_graph_service=_FakeExecutionGraphService(),
        tools=_FakeTools([]),
        ai_proxy_client=_FakeAiProxy(),
    )

    with pytest.raises(ValueError, match="execution_mode 必须是 classic 或 graph"):
        list(
            service.stream_session_controller_reply(
                session_id="sess-1",
                user_id="u-1",
                project_id="p-1",
                user_message="测试非法模式",
                execution_mode="invalid-mode",
            )
        )
