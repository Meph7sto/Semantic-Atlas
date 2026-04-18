"""Integration-style tests for conflict detection agent graph mode."""

from __future__ import annotations

import json
import os
import sys
import uuid

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.agents.conflict_detection_agent.service import (
    ConflictDetectionAgentService,
)
from backend_business.services.agent.tools.conflict_detection_tools import (
    ConflictDetectionTools,
)


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
    def __init__(self) -> None:
        self.requirements = {
            "r-1": {
                "req_id": "r-1",
                "project_id": "project-1",
                "deleted": False,
                "title": "登录性能",
                "description": "系统在 3 秒内完成登录",
                "acceptance_criteria": "3 秒内展示首页",
                "notes": "",
                "status": "draft",
                "priority": "high",
                "parent_id": None,
                "order_index": 1,
            },
            "r-2": {
                "req_id": "r-2",
                "project_id": "project-1",
                "deleted": False,
                "title": "响应时间下限",
                "description": "系统任何操作响应时间不应低于 5 秒",
                "acceptance_criteria": "",
                "notes": "",
                "status": "draft",
                "priority": "medium",
                "parent_id": None,
                "order_index": 2,
            },
        }

    def get_requirement(self, requirement_id: str) -> dict | None:
        return self.requirements.get(requirement_id)

    def list_requirements_window(self, project_id, start_index, count, include_deleted=False):
        return {
            "total": 2,
            "start_index": start_index,
            "count": 2,
            "has_more": False,
            "items": [self.requirements["r-1"], self.requirements["r-2"]],
        }


class FakeGraphService:
    def __init__(self) -> None:
        self.graphs: dict[str, dict] = {}
        self.containers: dict[str, dict] = {}
        self.subgraphs: dict[str, dict] = {}
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}
        self.runtime_bindings: dict[tuple[str | None, str | None, str], dict] = {}
        self._seed_template()

    def _seed_template(self) -> None:
        graph_id = "tpl-conflict-graph"
        self.graphs[graph_id] = {
            "graph_id": graph_id,
            "project_id": "project-1",
            "name": "需求冲突检测",
            "description": "两个需求冲突检测",
            "graph_type": "execution_topology_template",
            "status": "draft",
        }
        self.containers["tpl-container-1"] = {
            "container_id": "tpl-container-1",
            "graph_id": graph_id,
            "container_key": "topology_conflict_agent",
            "label": "Topology Conflict Agent",
            "role_type": "agent",
            "order_index": 0,
        }
        self.nodes["tpl-node-1"] = {
            "node_id": "tpl-node-1",
            "graph_id": graph_id,
            "container_id": "tpl-container-1",
            "node_key": "fetch_states",
            "label": "Fetch",
            "node_type": "llm",
            "role_type": "agent",
            "phase_label": "获取需求",
            "task_prompt": "先获取两个需求的详细内容，然后调用 complete_phase。",
            "conditional_edges": None,
            "order_index": 0,
        }
        self.nodes["tpl-node-2"] = {
            "node_id": "tpl-node-2",
            "graph_id": graph_id,
            "container_id": "tpl-container-1",
            "node_key": "generate_pairs",
            "label": "Pair",
            "node_type": "llm",
            "role_type": "agent",
            "phase_label": "生成对比",
            "task_prompt": "生成待检测需求对。",
            "conditional_edges": None,
            "order_index": 1,
        }
        self.nodes["tpl-node-3"] = {
            "node_id": "tpl-node-3",
            "graph_id": graph_id,
            "container_id": "tpl-container-1",
            "node_key": "semantic_verdict",
            "label": "Verdict",
            "node_type": "llm",
            "role_type": "agent",
            "phase_label": "冲突裁决",
            "task_prompt": "执行冲突检测并给出结论。",
            "conditional_edges": None,
            "order_index": 2,
        }
        self.edges["tpl-edge-1"] = {
            "edge_id": "tpl-edge-1",
            "graph_id": graph_id,
            "source_node_id": "tpl-node-1",
            "target_node_id": "tpl-node-2",
            "edge_type": "seq",
            "order_index": 0,
        }
        self.edges["tpl-edge-2"] = {
            "edge_id": "tpl-edge-2",
            "graph_id": graph_id,
            "source_node_id": "tpl-node-2",
            "target_node_id": "tpl-node-3",
            "edge_type": "seq",
            "order_index": 1,
        }

    def list_execution_graphs(self, project_id: str, graph_types: list[str]) -> list[dict]:
        return [
            graph
            for graph in self.graphs.values()
            if graph.get("project_id") == project_id and graph.get("graph_type") in graph_types
        ]

    def get_execution_graph(self, graph_id: str) -> dict | None:
        return self.graphs.get(graph_id)

    def get_latest_runtime_graph_by_session(self, session_id: str, project_id=None) -> dict | None:
        runtime_graphs = [
            graph
            for graph in self.graphs.values()
            if graph.get("graph_type") == "agent_runtime_execution"
            and (graph.get("meta_json") or {}).get("session_id") == session_id
        ]
        runtime_graphs.sort(key=lambda item: str(item.get("graph_id") or ""))
        return runtime_graphs[-1] if runtime_graphs else None

    def list_runtime_graphs_by_session(self, session_id: str, project_id=None) -> list[dict]:
        return [
            graph
            for graph in self.graphs.values()
            if graph.get("graph_type") == "agent_runtime_execution"
            and (graph.get("meta_json") or {}).get("session_id") == session_id
        ]

    def get_graph_detail(self, graph_id: str, **_kwargs) -> dict:
        return {
            "graph": self.graphs.get(graph_id),
            "containers": [item for item in self.containers.values() if item.get("graph_id") == graph_id],
            "subgraphs": [item for item in self.subgraphs.values() if item.get("graph_id") == graph_id],
            "nodes": [item for item in self.nodes.values() if item.get("graph_id") == graph_id],
            "edges": [item for item in self.edges.values() if item.get("graph_id") == graph_id],
        }

    def create_runtime_graph(self, *, project_id, name, description="", created_by="", **kwargs) -> dict:
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
    ) -> dict:
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

    def create_container(self, *, graph_id, container_key, label, role_type, **kwargs) -> dict:
        container_id = str(uuid.uuid4())
        container = {
            "container_id": container_id,
            "graph_id": graph_id,
            "container_key": container_key,
            "label": label,
            "role_type": role_type,
            "config_json": kwargs.get("config_json"),
            "order_index": kwargs.get("order_index", 0),
        }
        self.containers[container_id] = container
        return container

    def create_subgraph(self, *, graph_id, container_id, subgraph_key, label, task_description, **kwargs) -> dict:
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
            "config_json": kwargs.get("config_json"),
        }
        self.subgraphs[subgraph_id] = subgraph
        return subgraph

    def create_node(self, *, graph_id, node_key, label, node_type, role_type, **kwargs) -> dict:
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
            "config_json": kwargs.get("config_json"),
            "order_index": kwargs.get("order_index", 0),
        }
        self.nodes[node_id] = node
        return node

    def create_edge(self, *, graph_id, source_node_id, target_node_id, edge_type, **kwargs) -> dict:
        edge_id = str(uuid.uuid4())
        edge = {
            "edge_id": edge_id,
            "graph_id": graph_id,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "edge_type": edge_type,
            "label": kwargs.get("label"),
            "condition_expr": kwargs.get("condition_expr"),
            "config_json": kwargs.get("config_json"),
            "order_index": kwargs.get("order_index", 0),
        }
        self.edges[edge_id] = edge
        return edge

    def get_node(self, node_id: str) -> dict:
        return dict(self.nodes[node_id])

    def update_node(self, *, node_id: str, **kwargs) -> dict:
        node = self.nodes[node_id]
        node.update({key: value for key, value in kwargs.items() if value is not None})
        return dict(node)

    def patch_graph_meta(self, graph_id: str, meta_patch: dict, status=None, updated_by="") -> dict:
        graph = self.graphs[graph_id]
        meta = dict(graph.get("meta_json") or {})
        meta.update(meta_patch or {})
        graph["meta_json"] = meta
        if status:
            graph["status"] = status
        return dict(graph)


class FakeAIProxy:
    def __init__(self) -> None:
        self.conflict_calls: list[tuple[str, str]] = []

    def conflict_check(self, text_a: str, text_b: str) -> dict:
        self.conflict_calls.append((text_a, text_b))
        return {
            "is_conflict": True,
            "raw_response": "二者在响应时间要求上互相冲突",
        }

    def chat_completion_with_tools(self, *, messages, tools, **_kwargs) -> dict:
        system_prompt = str(messages[0].get("content") or "")
        has_tool_result = any(message.get("role") == "tool" for message in messages)

        if "执行冲突检测并给出结论" in system_prompt and not has_tool_result:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-check-conflict",
                        "function": {
                            "name": "check_conflict",
                            "arguments": json.dumps(
                                {
                                    "requirement_id_a": "r-1",
                                    "requirement_id_b": "r-2",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }

        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "call-complete-phase",
                    "function": {
                        "name": "complete_phase",
                        "arguments": json.dumps({"conclusion": "阶段完成"}, ensure_ascii=False),
                    },
                }
            ],
        }


class FakeJudgeThenGraphAIProxy(FakeAIProxy):
    def chat_completion_with_tools(self, *, messages, tools, **_kwargs) -> dict:
        system_prompt = str(messages[0].get("content") or "")
        if "意图分类器兼拓扑图选择器" in system_prompt:
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-intent-judge",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps(
                                {
                                    "conclusion": "需要展开拓扑图",
                                    "expand_topology": True,
                                    "target_template_graph_id": "tpl-conflict-graph",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            }
        return super().chat_completion_with_tools(messages=messages, tools=tools, **_kwargs)


def test_stream_graph_executor_reply_runs_subgraphs_on_single_runtime_graph():
    chat_storage = FakeChatStorage()
    graph_service = FakeGraphService()
    requirements_service = FakeRequirementsService()
    ai_proxy = FakeJudgeThenGraphAIProxy()
    tools = ConflictDetectionTools(
        requirements_service=requirements_service,
        conflict_check_fn=ai_proxy.conflict_check,
    )
    service = ConflictDetectionAgentService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        requirements_service=requirements_service,
        tools=tools,
        ai_proxy_client=ai_proxy,
    )

    events = list(
        service.stream_conflict_agent_reply(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            user_message="请检测 r-1 和 r-2 的需求冲突",
            execution_mode="graph",
        )
    )

    graph_event = next(event for event in events if event["event"] == "graph")
    judge_event = next(event for event in events if event["event"] == "intent_judge_completed")
    skeleton_event = next(event for event in events if event["event"] == "skeleton_ready")
    expand_event = next(event for event in events if event["event"] == "topology_expanded")
    result_event = next(event for event in events if event["event"] == "result")
    assistant_event = next(event for event in events if event["event"] == "assistant_message")
    subgraph_events = [event for event in events if event["event"] == "subgraph_status"]
    tool_result_events = [event for event in events if event["event"] == "tool_result"]

    assert graph_event["data"]["graph_id"] == skeleton_event["data"]["graph_id"]
    assert judge_event["data"]["graph_id"] == graph_event["data"]["graph_id"]
    assert expand_event["data"]["graph_id"] == graph_event["data"]["graph_id"]
    assert judge_event["data"]["selected_template_id"] == "tpl-conflict-graph"
    assert skeleton_event["data"]["subgraph_count"] == 0
    assert expand_event["data"]["subgraph_count"] == 3
    assert result_event["data"]["graph_id"] == graph_event["data"]["graph_id"]
    assert result_event["data"]["status"] == "succeeded"
    assert assistant_event["data"]["content"] == "阶段完成"

    running_count = sum(1 for event in subgraph_events if event["data"]["status"] == "running")
    completed_count = sum(1 for event in subgraph_events if event["data"]["status"] == "completed")
    assert running_count == 3
    assert completed_count == 3

    assert len(tool_result_events) == 1
    assert tool_result_events[0]["data"]["tool"] == "check_conflict"
    assert ai_proxy.conflict_calls

    runtime_graphs = [
        graph
        for graph in graph_service.graphs.values()
        if graph.get("graph_type") == "agent_runtime_execution"
    ]
    assert len(runtime_graphs) == 1
    assert runtime_graphs[0]["graph_id"] == graph_event["data"]["graph_id"]
    assert runtime_graphs[0]["status"] == "succeeded"

    runtime_subgraphs = [
        subgraph
        for subgraph in graph_service.subgraphs.values()
        if subgraph.get("graph_id") == runtime_graphs[0]["graph_id"]
    ]
    assert len(runtime_subgraphs) == 3

    runtime_containers = [
        container
        for container in graph_service.containers.values()
        if container.get("graph_id") == runtime_graphs[0]["graph_id"]
    ]
    container_keys = {container.get("container_key") for container in runtime_containers}
    assert {"human_input", "conductor", "conflict_detection_agent"} <= container_keys
    assert "topology_conflict_agent" in container_keys


def test_stream_graph_executor_reply_uses_internal_judge_on_same_runtime_graph():
    chat_storage = FakeChatStorage()
    graph_service = FakeGraphService()
    requirements_service = FakeRequirementsService()
    ai_proxy = FakeJudgeThenGraphAIProxy()
    tools = ConflictDetectionTools(
        requirements_service=requirements_service,
        conflict_check_fn=ai_proxy.conflict_check,
    )
    service = ConflictDetectionAgentService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        requirements_service=requirements_service,
        tools=tools,
        ai_proxy_client=ai_proxy,
    )

    events = list(
        service.stream_conflict_agent_reply(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            user_message="请检测 r-1 和 r-2 的需求冲突",
            execution_mode="graph",
        )
    )

    graph_event = next(event for event in events if event["event"] == "graph")
    judge_event = next(event for event in events if event["event"] == "intent_judge_completed")
    skeleton_event = next(event for event in events if event["event"] == "skeleton_ready")
    expand_event = next(event for event in events if event["event"] == "topology_expanded")
    result_event = next(event for event in events if event["event"] == "result")

    assert judge_event["data"]["graph_id"] == graph_event["data"]["graph_id"]
    assert skeleton_event["data"]["graph_id"] == graph_event["data"]["graph_id"]
    assert expand_event["data"]["graph_id"] == graph_event["data"]["graph_id"]
    assert result_event["data"]["graph_id"] == graph_event["data"]["graph_id"]
    assert judge_event["data"]["selected_template_id"] == "tpl-conflict-graph"
    assert skeleton_event["data"]["subgraph_count"] == 0
    assert expand_event["data"]["subgraph_count"] == 3
    assert result_event["data"]["status"] == "succeeded"

    runtime_graphs = [
        graph
        for graph in graph_service.graphs.values()
        if graph.get("graph_type") == "agent_runtime_execution"
    ]
    assert len(runtime_graphs) == 1
    assert runtime_graphs[0]["graph_id"] == graph_event["data"]["graph_id"]

    runtime_containers = [
        container
        for container in graph_service.containers.values()
        if container.get("graph_id") == runtime_graphs[0]["graph_id"]
    ]
    container_keys = {container.get("container_key") for container in runtime_containers}
    assert {"human_input", "conductor", "conflict_detection_agent"} <= container_keys
    assert "topology_conflict_agent" in container_keys


def test_stream_graph_executor_reply_registers_runtime_binding_with_tool_allowlist():
    chat_storage = FakeChatStorage()
    graph_service = FakeGraphService()
    requirements_service = FakeRequirementsService()
    ai_proxy = FakeJudgeThenGraphAIProxy()
    tools = ConflictDetectionTools(
        requirements_service=requirements_service,
        conflict_check_fn=ai_proxy.conflict_check,
    )
    service = ConflictDetectionAgentService(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        requirements_service=requirements_service,
        tools=tools,
        ai_proxy_client=ai_proxy,
    )

    list(
        service.stream_conflict_agent_reply(
            session_id="session-1",
            user_id="user-1",
            project_id="project-1",
            user_message="请检测 r-1 和 r-2 的需求冲突",
            execution_mode="graph",
        )
    )

    binding = graph_service.runtime_bindings[
        ("conflict_detection_agent", "conflict_detection_agent", "default")
    ]
    assert set(binding["capability_policy_json"]["tool_names"]) == {
        "list_requirements",
        "get_requirement_detail",
        "check_conflict",
    }
