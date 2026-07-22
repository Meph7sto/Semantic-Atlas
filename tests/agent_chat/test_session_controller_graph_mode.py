"""Integration-style tests for SessionController GraphExecutor mode."""

from __future__ import annotations

import json
import os
import pathlib
import re
import sys
import uuid

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.agents.session_controller.service import (  # noqa: E402
    SessionControllerService,
)
from backend_business.services.agent.agents.session_controller.graph_template import (  # noqa: E402
    ensure_session_controller_template,
)
from backend_business.services.agent.agents.session_controller.tools import (  # noqa: E402
    SessionControllerTools,
)
from backend_business.services.agent.runtime.agent_definition import (  # noqa: E402
    AgentDefinition,
    AgentDelegation,
)
from backend_business.services.agent.runtime.agent_registry import (  # noqa: E402
    BUILTIN_AGENT_REGISTRY,
    AgentRegistry,
)


def _extract_candidate_template_id(system_prompt: str) -> str:
    match = re.search(r"\[([^\]]+)\]", system_prompt)
    if not match:
        raise AssertionError(f"candidate template id not found in prompt: {system_prompt}")
    return match.group(1)


class FakeChatStorage:
    def __init__(self) -> None:
        self.sessions = {
            "session-1": {
                "session_id": "session-1",
                "user_id": "user-1",
                "project_id": "project-1",
                "active_graph_id": None,
            }
        }
        self.messages: list[dict] = []

    def _ensure_session_access(self, session_id: str, user_id: str) -> dict:
        session = self.sessions[session_id]
        assert session["user_id"] == user_id
        return dict(session)

    def create_message(self, session_id, user_id, role, content, metadata, is_read):
        message = {
            "message_id": str(uuid.uuid4()),
            "session_id": session_id,
            "user_id": user_id,
            "role": role,
            "content": content,
            "metadata": metadata,
            "is_read": is_read,
        }
        self.messages.append(message)
        return message

    def update_session(self, session_id: str, **kwargs) -> None:
        self.sessions[session_id].update(kwargs)


class FakeRequirementsService:
    def list_requirements_window(self, project_id, start_index, count, include_deleted=False):
        return {
            "total": 1,
            "start_index": start_index,
            "count": 1,
            "has_more": False,
            "items": [
                {
                    "req_id": "REQ-9",
                    "title": "登录性能",
                    "description": "系统在 3 秒内完成登录",
                    "status": "draft",
                    "priority": "high",
                }
            ],
        }

    def search_requirements(self, project_id, keyword, start_index, count):
        return self.list_requirements_window(project_id, start_index, count)


class FakeGraphService:
    def __init__(self) -> None:
        self.graphs: dict[str, dict] = {}
        self.containers: dict[str, dict] = {}
        self.subgraphs: dict[str, dict] = {}
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}
        self.runtime_bindings: dict[tuple[str | None, str | None, str], dict] = {}

    def create_execution_graph(self, *, project_id, name, description="", created_by="", meta_json=None):
        graph_id = str(uuid.uuid4())
        graph = {
            "graph_id": graph_id,
            "project_id": project_id,
            "name": name,
            "description": description,
            "graph_type": "execution_topology_template",
            "status": "draft",
            "meta_json": dict(meta_json or {}),
        }
        self.graphs[graph_id] = graph
        return graph

    def list_execution_graphs(self, project_id: str, include_deleted: bool = False, graph_types=None):
        requested_types = set(graph_types or ["execution_topology_template"])
        return [
            graph
            for graph in self.graphs.values()
            if graph.get("project_id") == project_id and graph.get("graph_type") in requested_types
        ]

    def get_execution_graph(self, graph_id: str) -> dict | None:
        graph = self.graphs.get(graph_id)
        return dict(graph) if graph else None

    def get_latest_runtime_graph_by_session(self, session_id: str, project_id=None) -> dict | None:
        runtime_graphs = [
            graph
            for graph in self.graphs.values()
            if graph.get("graph_type") == "agent_runtime_execution"
            and (graph.get("meta_json") or {}).get("session_id") == session_id
            and (project_id is None or graph.get("project_id") == project_id)
        ]
        runtime_graphs.sort(key=lambda item: str(item.get("graph_id") or ""))
        return dict(runtime_graphs[-1]) if runtime_graphs else None

    def list_runtime_graphs_by_session(self, session_id: str, project_id=None) -> list[dict]:
        runtime_graphs = [
            graph
            for graph in self.graphs.values()
            if graph.get("graph_type") == "agent_runtime_execution"
            and (graph.get("meta_json") or {}).get("session_id") == session_id
            and (project_id is None or graph.get("project_id") == project_id)
        ]
        runtime_graphs.sort(key=lambda item: str(item.get("graph_id") or ""))
        return [dict(graph) for graph in runtime_graphs]

    def create_runtime_graph(self, *, project_id, name, description="", created_by="", **kwargs):
        graph_id = str(uuid.uuid4())
        graph = {
            "graph_id": graph_id,
            "project_id": project_id,
            "name": name,
            "description": description,
            "graph_type": "agent_runtime_execution",
            "status": kwargs.get("status", "running"),
            "meta_json": dict(kwargs.get("meta_json") or {}),
        }
        self.graphs[graph_id] = graph
        return graph

    def ensure_agent_runtime_binding(
        self,
        *,
        container_key=None,
        agent_type=None,
        runtime_profile="default",
        implementation_type="local",
        endpoint=None,
        enabled=True,
        capability_policy_json=None,
        quota_policy_json=None,
        memory_policy_json=None,
    ):
        binding = {
            "runtime_id": str(uuid.uuid4()),
            "container_key": container_key,
            "agent_type": agent_type,
            "runtime_profile": runtime_profile,
            "implementation_type": implementation_type,
            "endpoint": endpoint,
            "enabled": enabled,
            "capability_policy_json": dict(capability_policy_json or {}),
            "quota_policy_json": dict(quota_policy_json or {}),
            "memory_policy_json": dict(memory_policy_json or {}),
        }
        self.runtime_bindings[(container_key, agent_type, runtime_profile)] = binding
        return binding

    def get_graph_detail(self, graph_id: str, **_kwargs) -> dict:
        return {
            "graph": self.graphs.get(graph_id),
            "containers": [item for item in self.containers.values() if item.get("graph_id") == graph_id],
            "subgraphs": [item for item in self.subgraphs.values() if item.get("graph_id") == graph_id],
            "nodes": [item for item in self.nodes.values() if item.get("graph_id") == graph_id],
            "edges": [item for item in self.edges.values() if item.get("graph_id") == graph_id],
        }

    def create_container(self, *, graph_id, container_key, label, role_type, **kwargs):
        container_id = str(uuid.uuid4())
        container = {
            "container_id": container_id,
            "graph_id": graph_id,
            "container_key": container_key,
            "label": label,
            "role_type": role_type,
            "config_json": dict(kwargs.get("config_json") or {}),
            "order_index": kwargs.get("order_index", 0),
        }
        self.containers[container_id] = container
        return container

    def create_subgraph(self, *, graph_id, container_id, subgraph_key, label, task_description, **kwargs):
        subgraph_id = str(uuid.uuid4())
        subgraph = {
            "subgraph_id": subgraph_id,
            "graph_id": graph_id,
            "container_id": container_id,
            "subgraph_key": subgraph_key,
            "label": label,
            "task_description": task_description,
            "status": "pending",
            "order_index": kwargs.get("order_index", 0),
            "config_json": dict(kwargs.get("config_json") or {}),
        }
        self.subgraphs[subgraph_id] = subgraph
        return subgraph

    def create_node(self, *, graph_id, node_key, label, node_type, role_type, **kwargs):
        node_id = str(uuid.uuid4())
        node = {
            "node_id": node_id,
            "graph_id": graph_id,
            "container_id": kwargs.get("container_id"),
            "subgraph_id": kwargs.get("subgraph_id"),
            "node_key": node_key,
            "label": label,
            "node_type": node_type,
            "role_type": role_type,
            "phase_label": kwargs.get("phase_label"),
            "task_prompt": kwargs.get("task_prompt"),
            "conditional_edges": kwargs.get("conditional_edges"),
            "config_json": dict(kwargs.get("config_json") or {}),
            "order_index": kwargs.get("order_index", 0),
        }
        self.nodes[node_id] = node
        return node

    def get_node(self, node_id: str) -> dict:
        return dict(self.nodes[node_id])

    def update_node(self, *, node_id: str, updated_by: str = "", **kwargs) -> dict:
        node = self.nodes[node_id]
        for key, value in kwargs.items():
            if value is not None:
                node[key] = value
        return dict(node)

    def create_edge(self, *, graph_id, source_node_id, target_node_id, edge_type, **kwargs):
        edge_id = str(uuid.uuid4())
        edge = {
            "edge_id": edge_id,
            "graph_id": graph_id,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "edge_type": edge_type,
            "label": kwargs.get("label"),
            "condition_expr": kwargs.get("condition_expr"),
            "config_json": dict(kwargs.get("config_json") or {}),
            "order_index": kwargs.get("order_index", 0),
        }
        self.edges[edge_id] = edge
        return edge

    def patch_graph_meta(self, graph_id: str, meta_patch: dict, status=None, updated_by="") -> dict:
        graph = self.graphs[graph_id]
        meta = dict(graph.get("meta_json") or {})
        meta.update(meta_patch or {})
        graph["meta_json"] = meta
        if status:
            graph["status"] = status
        return dict(graph)


class StrictFakeGraphService(FakeGraphService):
    def create_container(self, *, graph_id, container_key, label, role_type, **kwargs):
        for container in self.containers.values():
            if (
                container.get("graph_id") == graph_id
                and container.get("container_key") == container_key
            ):
                raise ValueError(f"容器 key '{container_key}' 在图中已存在")
        return super().create_container(
            graph_id=graph_id,
            container_key=container_key,
            label=label,
            role_type=role_type,
            **kwargs,
        )


def test_session_controller_template_is_regenerated_when_catalog_changes():
    graph_service = FakeGraphService()
    original_graph_id = ensure_session_controller_template(
        execution_graph_service=graph_service,
        project_id="project-1",
        actor="user-1",
        agent_registry=BUILTIN_AGENT_REGISTRY,
    )
    assert (
        ensure_session_controller_template(
            execution_graph_service=graph_service,
            project_id="project-1",
            actor="user-1",
            agent_registry=BUILTIN_AGENT_REGISTRY,
        )
        == original_graph_id
    )

    custom_definition = AgentDefinition(
        agent_type="custom_agent",
        container_key="custom_agent",
        label="Custom Agent",
        delegation=AgentDelegation(
            tool_name="invoke_custom_agent",
            route_key="invoke_custom",
            decision_mode="delegate_custom",
            tool_description="Delegate custom work",
            tool_parameters={
                "type": "object",
                "properties": {"task_description": {"type": "string"}},
                "required": ["task_description"],
            },
            invoke_label="Invoke Custom Agent",
            invoke_phase_label="Delegate custom agent",
            invoke_task_prompt="Delegate the custom task.",
            runtime_label="Custom Agent Runtime",
            runtime_phase_label="Run custom agent",
            runtime_task_prompt="Execute the custom task.",
            prompt_builder_kind="custom_delegate",
            runtime_node_key="custom_agent_runtime",
            result_contract="custom_result",
            call_edge_label="call_custom_agent",
        ),
    )
    extended_registry = AgentRegistry(
        [*BUILTIN_AGENT_REGISTRY.all_definitions(), custom_definition]
    )

    extended_graph_id = ensure_session_controller_template(
        execution_graph_service=graph_service,
        project_id="project-1",
        actor="user-1",
        agent_registry=extended_registry,
    )

    assert extended_graph_id != original_graph_id
    assert any(
        container["graph_id"] == extended_graph_id
        and container["container_key"] == "custom_agent"
        for container in graph_service.containers.values()
    )
    assert any(
        node["graph_id"] == extended_graph_id
        and node["node_key"] == "custom_agent_runtime"
        for node in graph_service.nodes.values()
    )


class DelegatingGraphAIProxy:
    def __init__(self) -> None:
        self.calls = 0

    def chat_completion_with_tools(self, *, messages, tools, **_kwargs) -> dict:
        self.calls += 1
        system_prompt = str(messages[0].get("content") or "")
        has_tool_result = any(message.get("role") == "tool" for message in messages)

        if "意图分类器兼拓扑图选择器" in system_prompt:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-judge-expand",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps(
                                {
                                    "conclusion": "需要展开拓扑图并委托需求 Agent。",
                                    "expand_topology": True,
                                    "target_template_graph_id": _extract_candidate_template_id(system_prompt),
                                    "target_container_keys": ["requirement_agent"],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }

        if "总控决策阶段" in system_prompt and not has_tool_result:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-delegate",
                        "function": {
                            "name": "invoke_requirement_agent",
                            "arguments": json.dumps(
                                {"task_description": "给我一个需求的完整信息"},
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        if "总控决策阶段" in system_prompt and has_tool_result:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-complete-decision",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps(
                                {
                                    "conclusion": json.dumps(
                                        {
                                            "mode": "delegate_requirement",
                                            "tool_loop_reply": "已读取需求详情",
                                            "assistant_reply_seed": "这是一个需求的完整信息摘要",
                                            "delegated_agent": "requirement_agent",
                                            "resolved_requirement_id": "REQ-9",
                                            "dispatched_agents": ["requirement_agent"],
                                            "approval_pending": False,
                                            "should_suspend": False,
                                            "suspend_reason": None,
                                        },
                                        ensure_ascii=False,
                                    ),
                                    "route_key": "invoke_requirement",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        if "你是需求管理 Agent" in system_prompt:
            return {
                "content": "已读取需求详情",
                "finish_reason": "stop",
                "tool_calls": [],
            }
        if "最终回复阶段" in system_prompt:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-final-reply",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps(
                                {"conclusion": "这是一个需求的完整信息摘要"},
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        raise AssertionError(f"unexpected prompt in DelegatingGraphAIProxy: {system_prompt}")

    def chat_completion(self, **_kwargs) -> dict:
        return {"content": "本轮调用 requirement_agent 并返回需求摘要。"}


class ClarifyThenResumeAIProxy:
    def __init__(self) -> None:
        self.calls = 0
        self.decision_calls = 0

    def chat_completion_with_tools(self, *, messages, tools, **_kwargs) -> dict:
        self.calls += 1
        system_prompt = str(messages[0].get("content") or "")

        if "意图分类器兼拓扑图选择器" in system_prompt:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-judge-expand",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps(
                                {
                                    "conclusion": "这是复杂任务，需要展开拓扑图处理。",
                                    "expand_topology": True,
                                    "target_template_graph_id": _extract_candidate_template_id(system_prompt),
                                    "target_container_keys": ["requirement_agent"],
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        if "总控决策阶段" in system_prompt:
            self.decision_calls += 1
        if self.decision_calls == 1 and "总控决策阶段" in system_prompt:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-clarify-decision",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps(
                                {
                                    "conclusion": json.dumps(
                                        {
                                            "mode": "clarify",
                                            "tool_loop_reply": "请确认你要修改的是 REQ-9 吗？",
                                            "assistant_reply_seed": "请确认你要修改的是 REQ-9 吗？",
                                            "clarification_question": "请确认你要修改的是 REQ-9 吗？",
                                            "delegated_agent": None,
                                            "resolved_requirement_id": "REQ-9",
                                            "dispatched_agents": [],
                                            "approval_pending": False,
                                            "should_suspend": True,
                                            "suspend_reason": "clarification",
                                        },
                                        ensure_ascii=False,
                                    ),
                                    "route_key": "suspend",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        if "挂起回复阶段" in system_prompt:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-suspend-reply",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps(
                                {"conclusion": "请确认你要修改的是 REQ-9 吗？"},
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        if self.decision_calls == 2 and "总控决策阶段" in system_prompt:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-resume-decision",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps(
                                {
                                    "conclusion": json.dumps(
                                        {
                                            "mode": "direct_reply",
                                            "tool_loop_reply": "已收到你的确认，将继续处理 REQ-9。",
                                            "assistant_reply_seed": "已收到你的确认，将继续处理 REQ-9。",
                                            "delegated_agent": None,
                                            "resolved_requirement_id": "REQ-9",
                                            "dispatched_agents": [],
                                            "approval_pending": False,
                                            "should_suspend": False,
                                            "suspend_reason": None,
                                        },
                                        ensure_ascii=False,
                                    ),
                                    "route_key": "reply",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        if "最终回复阶段" in system_prompt:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-resume-final",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps(
                                {"conclusion": "已收到你的确认，将继续处理 REQ-9。"},
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        raise AssertionError(f"unexpected prompt sequence call={self.calls}: {system_prompt}")

    def chat_completion(self, **_kwargs) -> dict:
        return {"content": "本轮已记录会话摘要。"}


class NoTopologySessionControllerAIProxy:
    def __init__(self) -> None:
        self.calls = 0

    def chat_completion_with_tools(self, *, messages, tools, **_kwargs) -> dict:
        self.calls += 1
        system_prompt = str(messages[0].get("content") or "")
        if self.calls == 1 and "意图分类器兼拓扑图选择器" in system_prompt:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-judge-no-topology",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps(
                                {
                                    "conclusion": "用户只是随口聊一句，不需要展开拓扑图。",
                                    "expand_topology": False,
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        if self.calls == 2:
            return {
                "content": "这只是一个普通回复，不需要调度复杂执行图。",
                "finish_reason": "stop",
                "tool_calls": [],
            }
        raise AssertionError(f"unexpected prompt sequence call={self.calls}: {system_prompt}")

    def chat_completion(self, **_kwargs) -> dict:
        return {"content": "本轮是普通对话，无需展开拓扑图。"}


class FakeRequirementAgentService:
    def __init__(self) -> None:
        self.inline_calls: list[dict] = []
        self.tools = _FakeDelegatedTools()

    def run_inline_tool_loop(self, **kwargs):
        self.inline_calls.append(dict(kwargs))
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
                "graph_id": kwargs["recorder"].graph_id,
                "node_key": "delegated_requirement_stage",
                "status": "succeeded",
            },
        }
        return self.run_inline_tool_loop(**kwargs)


class FakeConflictAgentService:
    def __init__(self) -> None:
        self.tools = _FakeDelegatedTools()

    def run_inline_tool_loop(self, **kwargs):
        return {"status": "success", "tool_loop_reply": "冲突检测完成"}

    def stream_inline_tool_loop(self, **kwargs):
        return self.run_inline_tool_loop(**kwargs)


class _FakeDelegatedTools:
    def __init__(self) -> None:
        self.context_snapshots: list[dict] = []

    def get_tools_list(self, context=None):
        self.context_snapshots.append(dict(context or {}))
        return []

    def execute(self, tool_name, arguments, context):
        raise AssertionError(f"unexpected delegated tool call: {tool_name}")


class _NamedTools:
    def __init__(self, tool_names: list[str]) -> None:
        self._tool_names = list(tool_names)

    def get_tools_list(self, context=None):
        _ = context
        return [
            {"type": "function", "function": {"name": tool_name}}
            for tool_name in self._tool_names
        ]


def _build_service(ai_proxy, *, requirement_agent_service=None, graph_service=None):
    chat_storage = FakeChatStorage()
    graph_service = graph_service or FakeGraphService()
    requirements_service = FakeRequirementsService()
    requirement_agent_service = requirement_agent_service or FakeRequirementAgentService()
    tools = SessionControllerTools(
        requirements_service=requirements_service,
        requirement_agent_service=requirement_agent_service,
        conflict_agent_service=FakeConflictAgentService(),
        requirement_classification_agent_service=FakeConflictAgentService(),
    )
    service = SessionControllerService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        requirements_service=requirements_service,
        tools=tools,
        ai_proxy_client=ai_proxy,
    )
    return service, chat_storage, graph_service, requirement_agent_service


def test_stream_graph_executor_reply_delegates_requirement_agent_and_succeeds():
    service, chat_storage, graph_service, requirement_agent_service = _build_service(DelegatingGraphAIProxy())

    events = list(
        service.stream_session_controller_reply(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            user_message="随便给我一个需求的完整信息",
            execution_mode="graph",
        )
    )

    graph_event = next(event for event in events if event["event"] == "graph")
    result_event = next(event for event in events if event["event"] == "result")
    assistant_event = next(event for event in events if event["event"] == "assistant_message")
    tool_result_events = [event for event in events if event["event"] == "tool_result"]
    subgraph_events = [event for event in events if event["event"] == "subgraph_status"]

    assert result_event["data"]["graph_id"] == graph_event["data"]["graph_id"]
    assert result_event["data"]["mode"] == "delegate_requirement"
    assert result_event["data"]["status"] == "succeeded"
    assert result_event["data"]["reply_text"] == "这是一个需求的完整信息摘要"
    assert assistant_event["data"]["metadata"]["execution_mode"] == "graph"
    assert assistant_event["data"]["content"] == "这是一个需求的完整信息摘要"

    assert any(event["data"]["tool"] == "invoke_requirement_agent" for event in tool_result_events)
    assert sum(1 for event in subgraph_events if event["data"]["status"] == "completed") >= 3
    assert requirement_agent_service.inline_calls == []

    runtime_graph = graph_service.get_execution_graph(graph_event["data"]["graph_id"])
    runtime_detail = graph_service.get_graph_detail(graph_event["data"]["graph_id"])
    assert runtime_graph["status"] == "succeeded"
    assert runtime_graph["meta_json"]["session_controller_mode"] == "delegate_requirement"
    assert runtime_graph["meta_json"]["resolved_requirement_id"] == "REQ-9"
    assert {
        item["container_key"] for item in runtime_detail["containers"]
    } == {"conductor", "requirement_agent"}
    assert not any(
        item["subgraph_key"] == "sg_invoke_conflict_detection"
        for item in runtime_detail["subgraphs"]
    )
    assert not any(
        item["subgraph_key"] == "sg_invoke_requirement_classification_agent"
        for item in runtime_detail["subgraphs"]
    )
    snapshot = runtime_graph["meta_json"]["scratchpad_snapshot"]
    assert any(entry.get("entry_type") == "note" for entry in snapshot)

    def _node_id_containing(fragment: str) -> str:
        for node in runtime_detail["nodes"]:
            if fragment in str(node.get("node_key") or ""):
                return str(node["node_id"])
        raise AssertionError(f"node fragment not found: {fragment}")

    def _has_edge(*, source_fragment: str, target_fragment: str, edge_type: str) -> bool:
        source_node_id = _node_id_containing(source_fragment)
        target_node_id = _node_id_containing(target_fragment)
        return any(
            edge.get("source_node_id") == source_node_id
            and edge.get("target_node_id") == target_node_id
            and edge.get("edge_type") == edge_type
            for edge in runtime_detail["edges"]
        )

    assert _has_edge(
        source_fragment="intent_judge_r1",
        target_fragment="controller_intake_start",
        edge_type="seq",
    )
    assert _has_edge(
        source_fragment="controller_intake_end",
        target_fragment="invoke_requirement_agent_start",
        edge_type="seq",
    )
    assert _has_edge(
        source_fragment="invoke_requirement_agent_start",
        target_fragment="invoke_requirement_agent_end",
        edge_type="seq",
    )
    assert _has_edge(
        source_fragment="requirement_agent_runtime_end",
        target_fragment="invoke_requirement_agent_end",
        edge_type="return",
    )
    assert _has_edge(
        source_fragment="invoke_requirement_agent_end",
        target_fragment="final_reply_start",
        edge_type="seq",
    )


def test_stream_graph_executor_reply_reuses_instantiated_requirement_container():
    graph_service = StrictFakeGraphService()
    service, _chat_storage, graph_service, requirement_agent_service = _build_service(
        DelegatingGraphAIProxy(),
        graph_service=graph_service,
    )

    events = list(
        service.stream_session_controller_reply(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            user_message="帮我看看现在一共有多少个需求",
            execution_mode="graph",
        )
    )

    result_event = next(event for event in events if event["event"] == "result")
    assert result_event["data"]["status"] == "succeeded"
    assert requirement_agent_service.inline_calls == []

    runtime_detail = graph_service.get_graph_detail(result_event["data"]["graph_id"])
    requirement_containers = [
        item for item in runtime_detail["containers"]
        if item["container_key"] == "requirement_agent"
    ]
    assert len(requirement_containers) == 1


def test_stream_graph_executor_reply_suspends_and_resumes_same_graph():
    service, chat_storage, graph_service, _ = _build_service(ClarifyThenResumeAIProxy())

    first_events = list(
        service.stream_session_controller_reply(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            user_message="把这条需求优先级改成高",
            execution_mode="graph",
        )
    )
    first_graph_event = next(event for event in first_events if event["event"] == "graph")
    first_result_event = next(event for event in first_events if event["event"] == "result")

    assert first_result_event["data"]["graph_id"] == first_graph_event["data"]["graph_id"]
    assert first_result_event["data"]["status"] == "suspended"
    assert first_result_event["data"]["mode"] == "clarify"
    assert first_result_event["data"]["reply_text"] == "请确认你要修改的是 REQ-9 吗？"

    suspended_graph = graph_service.get_execution_graph(first_graph_event["data"]["graph_id"])
    assert suspended_graph["status"] == "suspended"
    assert suspended_graph["meta_json"]["awaiting_user_input"] is True
    assert suspended_graph["meta_json"]["suspended_subgraph_id"]

    second_events = list(
        service.stream_session_controller_reply(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            user_message="是的，就是 REQ-9",
            execution_mode="graph",
        )
    )
    second_graph_event = next(event for event in second_events if event["event"] == "graph")
    second_result_event = next(event for event in second_events if event["event"] == "result")

    assert second_graph_event["data"]["graph_id"] == first_graph_event["data"]["graph_id"]
    assert second_result_event["data"]["graph_id"] == first_graph_event["data"]["graph_id"]
    assert second_result_event["data"]["status"] == "succeeded"
    assert second_result_event["data"]["mode"] == "direct_reply"
    assert second_result_event["data"]["reply_text"] == "已收到你的确认，将继续处理 REQ-9。"

    resumed_graph = graph_service.get_execution_graph(first_graph_event["data"]["graph_id"])
    assert resumed_graph["status"] == "succeeded"
    assert resumed_graph["meta_json"]["session_controller_mode"] == "direct_reply"
    assert chat_storage.sessions["session-1"]["active_graph_id"] == first_graph_event["data"]["graph_id"]


def test_stream_graph_executor_reply_skips_topology_for_simple_message():
    service, _chat_storage, graph_service, _ = _build_service(
        NoTopologySessionControllerAIProxy()
    )

    events = list(
        service.stream_session_controller_reply(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            user_message="花",
            execution_mode="graph",
        )
    )

    result_event = next(event for event in events if event["event"] == "result")
    graph_id = result_event["data"]["graph_id"]
    graph_detail = graph_service.get_graph_detail(graph_id)
    runtime_graph = graph_service.get_execution_graph(graph_id)

    assert result_event["data"]["status"] == "succeeded"
    assert result_event["data"]["mode"] == "direct_reply"
    assert result_event["data"]["reply_text"] == "这只是一个普通回复，不需要调度复杂执行图。"
    assert runtime_graph["status"] == "succeeded"
    assert runtime_graph["meta_json"]["session_controller_mode"] == "direct_reply"
    assert runtime_graph["meta_json"].get("source_template_id") is None
    assert [item["container_key"] for item in graph_detail["containers"]] == ["conductor"]
    assert graph_detail["subgraphs"] == []
    assert not any(
        node["node_type"] in {"start", "end"} and node["node_key"] != "start"
        for node in graph_detail["nodes"]
    )


def test_stream_graph_executor_reply_forwards_delegated_round_limit():
    requirement_agent_service = FakeRequirementAgentService()
    service, _chat_storage, _graph_service, requirement_agent_service = _build_service(
        DelegatingGraphAIProxy(),
        requirement_agent_service=requirement_agent_service,
    )

    list(
        service.stream_session_controller_reply(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            user_message="随便给我一个需求的完整信息",
            execution_mode="graph",
            delegated_max_tool_call_rounds=7,
        )
    )

    assert requirement_agent_service.inline_calls == []
    delegated_contexts = requirement_agent_service.tools.context_snapshots
    assert delegated_contexts
    assert any(context.get("max_tool_call_rounds") == 7 for context in delegated_contexts)


def test_ensure_graph_runtime_bindings_persists_explicit_tool_allowlists():
    graph_service = FakeGraphService()
    requirement_agent_service = FakeRequirementAgentService()
    conflict_agent_service = FakeConflictAgentService()
    classification_agent_service = FakeConflictAgentService()
    traceability_agent_service = FakeConflictAgentService()
    requirement_agent_service.tools = _NamedTools(
        [
            "search_requirements",
            "list_requirements",
            "get_requirement_state",
            "update_requirement_content",
        ]
    )
    conflict_agent_service.tools = _NamedTools(
        ["list_requirements", "get_requirement_detail", "check_conflict"]
    )
    classification_agent_service.tools = _NamedTools(
        [
            "list_requirements",
            "search_requirements",
            "get_requirement_detail",
            "classify_requirement",
        ]
    )
    traceability_agent_service.tools = _NamedTools(
        [
            "search_requirements",
            "list_requirements",
            "get_requirement_state",
            "trace_requirement_relation",
        ]
    )
    tools = SessionControllerTools(
        requirements_service=FakeRequirementsService(),
        requirement_agent_service=requirement_agent_service,
        conflict_agent_service=conflict_agent_service,
        requirement_classification_agent_service=classification_agent_service,
        agent_services={"traceability_agent": traceability_agent_service},
    )
    service = SessionControllerService(
        chat_storage=FakeChatStorage(),
        execution_graph_service=graph_service,
        requirements_service=FakeRequirementsService(),
        tools=tools,
        ai_proxy_client=DelegatingGraphAIProxy(),
    )

    service._ensure_graph_runtime_bindings()

    conductor_binding = graph_service.runtime_bindings[
        ("conductor", "session_controller", "default")
    ]
    requirement_binding = graph_service.runtime_bindings[
        ("requirement_agent", "requirement_agent", "default")
    ]
    conflict_binding = graph_service.runtime_bindings[
        ("conflict_detection", "conflict_detection", "default")
    ]
    classification_binding = graph_service.runtime_bindings[
        (
            "requirement_classification_agent",
            "requirement_classification_agent",
            "default",
        )
    ]
    traceability_binding = graph_service.runtime_bindings[
        ("traceability_agent", "traceability_agent", "default")
    ]

    assert set(conductor_binding["capability_policy_json"]["tool_names"]) == {
        "list_requirements",
        "search_requirements",
        "invoke_requirement_agent",
        "invoke_conflict_detection",
        "invoke_requirement_classification_agent",
        "invoke_traceability_agent",
    }
    assert set(requirement_binding["capability_policy_json"]["tool_names"]) == {
        "search_requirements",
        "list_requirements",
        "get_requirement_state",
        "update_requirement_content",
    }
    assert set(conflict_binding["capability_policy_json"]["tool_names"]) == {
        "list_requirements",
        "get_requirement_detail",
        "check_conflict",
    }
    assert set(classification_binding["capability_policy_json"]["tool_names"]) == {
        "list_requirements",
        "search_requirements",
        "get_requirement_detail",
        "classify_requirement",
    }
    assert set(traceability_binding["capability_policy_json"]["tool_names"]) == {
        "search_requirements",
        "list_requirements",
        "get_requirement_state",
        "trace_requirement_relation",
    }


def test_session_controller_specific_logic_stays_out_of_generic_execution_layer():
    root = pathlib.Path(ROOT_DIR)
    subgraph_runner_text = (
        root / "backend_business/services/agent/execution/subgraph_runner.py"
    ).read_text(encoding="utf-8")
    tools_text = (
        root / "backend_business/services/agent/agents/session_controller/tools.py"
    ).read_text(encoding="utf-8")
    delegation_text = (
        root / "backend_business/services/agent/agents/session_controller/delegation.py"
    ).read_text(encoding="utf-8")

    assert "graph_prompt_builders" not in subgraph_runner_text
    assert 'prompt_builder_kind == "session_controller_' not in subgraph_runner_text
    assert "run_inline_tool_loop" not in tools_text
    assert "_queue_native_" not in tools_text
    assert "run_inline_tool_loop" not in delegation_text
    assert "stream_inline_tool_loop" not in delegation_text
    assert "_native_invoke_enabled" not in delegation_text
