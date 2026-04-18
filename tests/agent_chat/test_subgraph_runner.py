"""Tests for SubgraphRunner — runtime subgraph execution engine.

All tests use stubs/fakes so that no DB, real LLM, or network is required.
The ``FakeGraphService`` seeds templates and generates runtime skeletons
via ``TopologyInstantiator``; the ``FakeAIProxy`` returns pre-configured
complete_phase tool calls.
"""

from __future__ import annotations

import os
import sys
import threading
import uuid

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import pytest

from backend_business.services.agent.execution.subgraph_runner import (
    ContainerResult,
    SubgraphRunner,
    _build_invoke_runtime_context,
    _build_subgraph_context,
)
from backend_business.services.agent.execution.subgraph_state import (
    ContainerExecutionError,
    SuspendSignal,
)
from backend_business.services.agent.execution.topology_instantiator import (
    RuntimeGraphSkeleton,
    TopologyInstantiator,
)
from backend_business.services.agent.runtime import (
    AgentRunResult,
    LocalAgentRuntime,
    RuntimeBinding,
    Scratchpad,
)


# =========================================================================
# Stubs
# =========================================================================


class FakeGraphService:
    """In-memory graph service for template seeding + instantiation."""

    def __init__(self) -> None:
        self.graphs: dict[str, dict] = {}
        self.containers: dict[str, dict] = {}
        self.subgraphs: dict[str, dict] = {}
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}
        self.agent_runs: dict[str, dict] = {}

    def seed_template(
        self,
        *,
        graph_id: str,
        project_id: str,
        name: str = "tpl",
        containers: list[dict] | None = None,
        nodes: list[dict] | None = None,
        edges: list[dict] | None = None,
    ) -> None:
        self.graphs[graph_id] = {
            "graph_id": graph_id,
            "project_id": project_id,
            "name": name,
            "description": "",
            "graph_type": "execution_topology_template",
            "status": "draft",
        }
        for c in containers or []:
            self.containers[c["container_id"]] = {**c, "graph_id": graph_id}
        for n in nodes or []:
            self.nodes[n["node_id"]] = {**n, "graph_id": graph_id}
        for e in edges or []:
            self.edges[e["edge_id"]] = {**e, "graph_id": graph_id}

    def get_graph_detail(self, graph_id: str, **_kw) -> dict:
        graph = self.graphs.get(graph_id)
        containers = [c for c in self.containers.values() if c.get("graph_id") == graph_id]
        nodes = [n for n in self.nodes.values() if n.get("graph_id") == graph_id]
        edges = [e for e in self.edges.values() if e.get("graph_id") == graph_id]
        return {"graph": graph, "containers": containers, "subgraphs": [], "nodes": nodes, "edges": edges}

    def create_runtime_graph(self, *, project_id, name, description="", created_by="", **kw) -> dict:
        gid = str(uuid.uuid4())
        g = {
            "graph_id": gid, "project_id": project_id, "name": name,
            "description": description, "graph_type": "agent_runtime_execution",
            "status": kw.get("status", "running"), "meta_json": kw.get("meta_json"),
        }
        self.graphs[gid] = g
        return g

    def create_container(self, *, graph_id, container_key, label, role_type, **kw) -> dict:
        cid = str(uuid.uuid4())
        c = {
            "container_id": cid, "graph_id": graph_id, "container_key": container_key,
            "label": label, "role_type": role_type, "config_json": kw.get("config_json"),
            "order_index": kw.get("order_index", 0),
        }
        self.containers[cid] = c
        return c

    def create_subgraph(self, *, graph_id, container_id, subgraph_key, label, task_description, **kw) -> dict:
        sid = str(uuid.uuid4())
        sg = {
            "subgraph_id": sid, "graph_id": graph_id, "container_id": container_id,
            "subgraph_key": subgraph_key, "label": label, "task_description": task_description,
            "status": "pending", "order_index": kw.get("order_index", 0),
            "config_json": kw.get("config_json"),
        }
        self.subgraphs[sid] = sg
        return sg

    def create_node(self, *, graph_id, node_key, label, node_type, role_type, **kw) -> dict:
        nid = str(uuid.uuid4())
        n = {
            "node_id": nid, "graph_id": graph_id, "container_id": kw.get("container_id"),
            "subgraph_id": kw.get("subgraph_id"), "node_key": node_key, "label": label,
            "node_type": node_type, "role_type": role_type, "order_index": kw.get("order_index", 0),
            "config_json": kw.get("config_json"),
        }
        self.nodes[nid] = n
        return n

    def create_edge(self, *, graph_id, source_node_id, target_node_id, edge_type, **kw) -> dict:
        eid = str(uuid.uuid4())
        e = {
            "edge_id": eid, "graph_id": graph_id, "source_node_id": source_node_id,
            "target_node_id": target_node_id, "edge_type": edge_type,
            "label": kw.get("label"), "condition_expr": kw.get("condition_expr"),
            "config_json": kw.get("config_json"), "order_index": kw.get("order_index", 0),
        }
        self.edges[eid] = e
        return e

    def update_edge(self, edge_id: str, **kw) -> dict:
        edge = self.edges.get(edge_id, {})
        edge.update({k: v for k, v in kw.items() if v is not None})
        return dict(edge)

    def get_node(self, node_id: str) -> dict:
        return dict(self.nodes.get(node_id, {}))

    def update_node(self, *, node_id, **kw) -> dict:
        node = self.nodes.get(node_id, {})
        node.update({k: v for k, v in kw.items() if v is not None})
        return dict(node)

    def patch_graph_meta(self, graph_id, meta_patch, status=None, updated_by="") -> dict:
        g = self.graphs.get(graph_id, {})
        meta = dict(g.get("meta_json") or {})
        meta.update(meta_patch or {})
        g["meta_json"] = meta
        if status:
            g["status"] = status
        return dict(g)

    def create_agent_run(self, **kwargs) -> dict:
        row = dict(kwargs)
        self.agent_runs[row["run_id"]] = row
        return row

    def update_agent_run(self, run_id, **kwargs) -> dict:
        row = self.agent_runs[run_id]
        row.update({key: value for key, value in kwargs.items() if value is not None})
        return dict(row)


class FakeAIProxy:
    """Returns a pre-configured complete_phase tool call (simulating LLM).

    Each call returns a response with a single complete_phase tool call.
    Custom conclusions and route_keys can be queued.
    """

    def __init__(self, conclusions: list[str] | None = None, route_keys: list[str | None] | None = None) -> None:
        self._conclusions = list(conclusions or ["阶段完成"])
        self._route_keys = list(route_keys or [None])
        self._call_count = 0

    def chat_completion_with_tools(self, *, messages, tools, **_kw) -> dict:
        idx = min(self._call_count, len(self._conclusions) - 1)
        conclusion = self._conclusions[idx]
        route_key = self._route_keys[min(self._call_count, len(self._route_keys) - 1)]
        self._call_count += 1

        arguments = {"conclusion": conclusion}
        if route_key is not None:
            arguments["route_key"] = route_key

        import json
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": f"call_{self._call_count}",
                    "function": {
                        "name": "complete_phase",
                        "arguments": json.dumps(arguments, ensure_ascii=False),
                    },
                },
            ],
        }


class PromptCapturingAIProxy:
    """Queue-based AI proxy that records system prompts for each LLM call."""

    def __init__(self, responses: list[dict]) -> None:
        self._responses = list(responses)
        self.system_prompts: list[str] = []

    def chat_completion_with_tools(self, *, messages, tools, **_kw) -> dict:
        self.system_prompts.append(str(messages[0].get("content") or ""))
        if not self._responses:
            raise AssertionError("unexpected call")
        return self._responses.pop(0)


class FakeToolExecutor:
    """Empty tool executor — no business tools needed for unit tests."""

    def get_tools_list(self) -> list[dict]:
        return []

    def execute(self, tool_name: str, arguments: dict, context: dict) -> dict:
        return {"ok": True}


class FakeRecorder:
    """Minimal recorder stub that satisfies ToolLoopRunner's API."""

    def __init__(self, graph_id: str = "fake-graph") -> None:
        self.graph_id = graph_id
        self.turn_index = 1
        self._containers: dict[str, str] = {"agent": "fake-container-id"}
        self._stages: dict[str, dict] = {}

    def stage_node_key(self, base_key: str) -> str:
        return f"turn_{self.turn_index}__{base_key}"

    def stage_label(self, base_label: str) -> str:
        return f"{base_label} (Turn {self.turn_index})"

    def start_stage(self, *, node_key, label, node_type, role_type, container_key, created_by, input_summary, **_kw):
        self._stages[node_key] = {"status": "running"}

    def record_tool_call_result(self, node_key, *, created_by, tool_name, request_payload, result_payload):
        pass

    def complete_stage(self, node_key, *, created_by, output_summary, **_kw):
        self._stages[node_key] = {"status": "completed"}

    def enter_subgraph(self, *, subgraph_id, start_node_id):
        pass

    def leave_subgraph(self, *, end_node_id, created_by):
        pass


class FailingAIProxy:
    """AI proxy that raises an exception (simulating LLM failure)."""

    def chat_completion_with_tools(self, **_kw) -> dict:
        raise RuntimeError("LLM API 调用失败")


class ConcurrentInvokeAIProxy:
    """Requires delegated child LLM calls to reach the proxy concurrently."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._child_barrier = threading.Barrier(2, timeout=1.0)
        self._call_count = 0

    def chat_completion_with_tools(self, *, messages, tools, **_kw) -> dict:
        with self._lock:
            self._call_count += 1
            call_index = self._call_count

        if call_index >= 2:
            self._child_barrier.wait()

        conclusion = f"阶段{call_index}完成"
        import json

        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": f"call_{call_index}",
                    "function": {
                        "name": "complete_phase",
                        "arguments": json.dumps(
                            {"conclusion": conclusion},
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        }


class _ImmediateFailRuntime:
    def __init__(self, graph_service: FakeGraphService) -> None:
        self._graph_service = graph_service

    def submit(self, run_request) -> str:
        run_id = "run-fail"
        self._graph_service.create_agent_run(
            run_id=run_id,
            graph_id=run_request.graph_id,
            subgraph_id=run_request.subgraph_id,
            container_key=run_request.container_key,
            agent_type=run_request.agent_type,
            runtime_id="rt::worker-a",
            status="queued",
            input_ref=(run_request.input_payload or {}).get("input_ref"),
            parent_run_id=None,
            resume_token=None,
        )
        self._graph_service.update_agent_run(run_id, status="running", started=True)
        return run_id

    def stream(self, agent_run_id: str):
        _ = agent_run_id
        if False:
            yield {}

    def await_result(self, agent_run_id: str) -> AgentRunResult:
        self._graph_service.update_agent_run(
            agent_run_id,
            status="failed",
            error_code="branch_failed",
            error_message="worker branch failed",
            completed=True,
        )
        return AgentRunResult(
            status="failed",
            error_code="branch_failed",
            error_message="worker branch failed",
        )

    def resume(self, agent_run_id: str, user_input):
        _ = agent_run_id, user_input
        raise RuntimeError("not supported")

    def cancel(self, agent_run_id: str) -> None:
        _ = agent_run_id


class _CancellableRuntime:
    def __init__(self, graph_service: FakeGraphService) -> None:
        self._graph_service = graph_service
        self.cancelled_runs: list[str] = []
        self.submitted_runs: list[str] = []
        self._cancel_events: dict[str, threading.Event] = {}

    def submit(self, run_request) -> str:
        run_id = f"run-{len(self.submitted_runs) + 1}"
        self.submitted_runs.append(run_id)
        self._cancel_events[run_id] = threading.Event()
        self._graph_service.create_agent_run(
            run_id=run_id,
            graph_id=run_request.graph_id,
            subgraph_id=run_request.subgraph_id,
            container_key=run_request.container_key,
            agent_type=run_request.agent_type,
            runtime_id="rt::worker-b",
            status="queued",
            input_ref=(run_request.input_payload or {}).get("input_ref"),
            parent_run_id=None,
            resume_token=None,
        )
        self._graph_service.update_agent_run(run_id, status="running", started=True)
        return run_id

    def stream(self, agent_run_id: str):
        _ = agent_run_id
        if False:
            yield {}

    def await_result(self, agent_run_id: str) -> AgentRunResult:
        cancelled = self._cancel_events[agent_run_id].wait(timeout=1.0)
        if not cancelled:
            raise AssertionError("expected branch to be cancelled after sibling failure")
        self._graph_service.update_agent_run(
            agent_run_id,
            status="cancelled",
            error_code="cancelled",
            error_message="branch cancelled",
            completed=True,
        )
        return AgentRunResult(
            status="cancelled",
            error_code="cancelled",
            error_message="branch cancelled",
        )

    def resume(self, agent_run_id: str, user_input):
        _ = agent_run_id, user_input
        raise RuntimeError("not supported")

    def cancel(self, agent_run_id: str) -> None:
        self.cancelled_runs.append(agent_run_id)
        self._cancel_events[agent_run_id].set()


class _StubRuntimeRegistry:
    def __init__(self, bindings: dict[str, RuntimeBinding]) -> None:
        self._bindings = dict(bindings)

    def resolve(
        self,
        *,
        container_key: str,
        agent_type: str,
        runtime_profile: str | None = None,
    ) -> RuntimeBinding:
        _ = agent_type, runtime_profile
        return self._bindings[container_key]


# =========================================================================
# Template fixtures
# =========================================================================


def _make_3node_skeleton(svc: FakeGraphService) -> RuntimeGraphSkeleton:
    """3-node linear template → instantiated skeleton."""
    svc.seed_template(
        graph_id="tpl-3",
        project_id="proj-1",
        containers=[
            {"container_id": "c-1", "container_key": "agent_container", "label": "Agent", "role_type": "agent", "order_index": 0},
        ],
        nodes=[
            {"node_id": "n-1", "node_key": "fetch", "label": "Fetch", "node_type": "llm", "role_type": "agent",
             "container_id": "c-1", "phase_label": "获取", "task_prompt": "获取数据", "conditional_edges": None, "order_index": 0},
            {"node_id": "n-2", "node_key": "analyze", "label": "Analyze", "node_type": "llm", "role_type": "agent",
             "container_id": "c-1", "phase_label": "分析", "task_prompt": "分析数据", "conditional_edges": None, "order_index": 1},
            {"node_id": "n-3", "node_key": "report", "label": "Report", "node_type": "llm", "role_type": "agent",
             "container_id": "c-1", "phase_label": "报告", "task_prompt": "生成报告", "conditional_edges": None, "order_index": 2},
        ],
        edges=[
            {"edge_id": "e-1", "source_node_id": "n-1", "target_node_id": "n-2", "edge_type": "seq", "order_index": 0},
            {"edge_id": "e-2", "source_node_id": "n-2", "target_node_id": "n-3", "edge_type": "seq", "order_index": 1},
        ],
    )
    return TopologyInstantiator().instantiate(
        template_graph_id="tpl-3", project_id="proj-1", graph_service=svc,
    )


def _make_handoff_skeleton(svc: FakeGraphService) -> RuntimeGraphSkeleton:
    """2-node template: llm → handoff."""
    svc.seed_template(
        graph_id="tpl-handoff",
        project_id="proj-1",
        containers=[
            {"container_id": "c-1", "container_key": "agent_container", "label": "Agent", "role_type": "agent", "order_index": 0},
        ],
        nodes=[
            {"node_id": "n-1", "node_key": "step1", "label": "Step1", "node_type": "llm", "role_type": "agent",
             "container_id": "c-1", "phase_label": "Step1", "task_prompt": "执行步骤一", "conditional_edges": None, "order_index": 0},
            {"node_id": "n-2", "node_key": "handoff_node", "label": "Handoff", "node_type": "handoff", "role_type": "agent",
             "container_id": "c-1", "phase_label": "移交", "task_prompt": "", "conditional_edges": None, "order_index": 1},
        ],
        edges=[
            {"edge_id": "e-1", "source_node_id": "n-1", "target_node_id": "n-2", "edge_type": "seq", "order_index": 0},
        ],
    )
    return TopologyInstantiator().instantiate(
        template_graph_id="tpl-handoff", project_id="proj-1", graph_service=svc,
    )


def _make_invoke_skeleton(svc: FakeGraphService) -> RuntimeGraphSkeleton:
    """Cross-container: Container A has [llm → invoke], Container B has [llm]."""
    svc.seed_template(
        graph_id="tpl-invoke",
        project_id="proj-1",
        containers=[
            {"container_id": "ca", "container_key": "session", "label": "Session", "role_type": "agent", "order_index": 0},
            {"container_id": "cb", "container_key": "worker", "label": "Worker", "role_type": "agent", "order_index": 1},
        ],
        nodes=[
            {"node_id": "na-1", "node_key": "parse", "label": "Parse", "node_type": "llm", "role_type": "agent",
             "container_id": "ca", "phase_label": "解析", "task_prompt": "解析意图", "conditional_edges": None, "order_index": 0},
            {"node_id": "na-2", "node_key": "call_worker", "label": "Call Worker", "node_type": "invoke", "role_type": "agent",
             "container_id": "ca", "phase_label": "调用", "task_prompt": "", "conditional_edges": None, "order_index": 1},
            {"node_id": "nb-1", "node_key": "do_work", "label": "Do Work", "node_type": "llm", "role_type": "agent",
             "container_id": "cb", "phase_label": "执行", "task_prompt": "执行任务", "conditional_edges": None, "order_index": 0},
        ],
        edges=[
            {"edge_id": "e-seq", "source_node_id": "na-1", "target_node_id": "na-2", "edge_type": "seq", "order_index": 0},
            {"edge_id": "e-call", "source_node_id": "na-2", "target_node_id": "nb-1", "edge_type": "call", "order_index": 1},
            {"edge_id": "e-ret", "source_node_id": "nb-1", "target_node_id": "na-2", "edge_type": "return", "order_index": 2},
        ],
    )
    return TopologyInstantiator().instantiate(
        template_graph_id="tpl-invoke", project_id="proj-1", graph_service=svc,
    )


def _make_parallel_invoke_skeleton(svc: FakeGraphService) -> RuntimeGraphSkeleton:
    """Cross-container invoke fan-out: one invoke calls two worker containers."""
    svc.seed_template(
        graph_id="tpl-invoke-parallel",
        project_id="proj-1",
        containers=[
            {"container_id": "ca", "container_key": "session", "label": "Session", "role_type": "agent", "order_index": 0},
            {"container_id": "cb", "container_key": "worker_a", "label": "Worker A", "role_type": "agent", "order_index": 1},
            {"container_id": "cc", "container_key": "worker_b", "label": "Worker B", "role_type": "agent", "order_index": 2},
        ],
        nodes=[
            {"node_id": "na-1", "node_key": "parse", "label": "Parse", "node_type": "llm", "role_type": "agent",
             "container_id": "ca", "phase_label": "解析", "task_prompt": "解析意图", "conditional_edges": None, "order_index": 0},
            {"node_id": "na-2", "node_key": "call_workers", "label": "Call Workers", "node_type": "invoke", "role_type": "agent",
             "container_id": "ca", "phase_label": "调用", "task_prompt": "", "conditional_edges": None, "order_index": 1},
            {"node_id": "nb-1", "node_key": "do_work_a", "label": "Do Work A", "node_type": "llm", "role_type": "agent",
             "container_id": "cb", "phase_label": "执行A", "task_prompt": "执行任务A", "conditional_edges": None, "order_index": 0},
            {"node_id": "nc-1", "node_key": "do_work_b", "label": "Do Work B", "node_type": "llm", "role_type": "agent",
             "container_id": "cc", "phase_label": "执行B", "task_prompt": "执行任务B", "conditional_edges": None, "order_index": 0},
        ],
        edges=[
            {"edge_id": "e-seq", "source_node_id": "na-1", "target_node_id": "na-2", "edge_type": "seq", "order_index": 0},
            {"edge_id": "e-call-a", "source_node_id": "na-2", "target_node_id": "nb-1", "edge_type": "call", "order_index": 1},
            {"edge_id": "e-call-b", "source_node_id": "na-2", "target_node_id": "nc-1", "edge_type": "call", "order_index": 2},
            {"edge_id": "e-ret-a", "source_node_id": "nb-1", "target_node_id": "na-2", "edge_type": "return", "order_index": 3},
            {"edge_id": "e-ret-b", "source_node_id": "nc-1", "target_node_id": "na-2", "edge_type": "return", "order_index": 4},
        ],
    )
    return TopologyInstantiator().instantiate(
        template_graph_id="tpl-invoke-parallel", project_id="proj-1", graph_service=svc,
    )


def _make_conditional_skeleton(svc: FakeGraphService) -> RuntimeGraphSkeleton:
    """Template with conditional routing: decision → branch_a / branch_b."""
    svc.seed_template(
        graph_id="tpl-cond",
        project_id="proj-1",
        containers=[
            {"container_id": "c-1", "container_key": "main", "label": "Main", "role_type": "agent", "order_index": 0},
        ],
        nodes=[
            {"node_id": "n-dec", "node_key": "decision", "label": "Decision", "node_type": "llm", "role_type": "agent",
             "container_id": "c-1", "phase_label": "决策", "task_prompt": "做出决策",
             "conditional_edges": [
                 {"condition": "approve", "target_node_id": "n-a"},
                 {"condition": "reject", "target_node_id": "n-b"},
             ],
             "order_index": 0},
            {"node_id": "n-a", "node_key": "branch_a", "label": "Branch A", "node_type": "llm", "role_type": "agent",
             "container_id": "c-1", "phase_label": "分支A", "task_prompt": "执行A",
             "conditional_edges": None, "order_index": 1},
            {"node_id": "n-b", "node_key": "branch_b", "label": "Branch B", "node_type": "llm", "role_type": "agent",
             "container_id": "c-1", "phase_label": "分支B", "task_prompt": "执行B",
             "conditional_edges": None, "order_index": 2},
        ],
        edges=[
            {"edge_id": "e-1", "source_node_id": "n-dec", "target_node_id": "n-a", "edge_type": "seq", "order_index": 0,
             "condition_expr": "approve"},
            {"edge_id": "e-2", "source_node_id": "n-dec", "target_node_id": "n-b", "edge_type": "seq", "order_index": 1,
             "condition_expr": "reject"},
        ],
    )
    return TopologyInstantiator().instantiate(
        template_graph_id="tpl-cond", project_id="proj-1", graph_service=svc,
    )


def _drain(gen) -> list[dict]:
    """Drain a generator, collecting all yielded events and returning them."""
    events = []
    try:
        event = next(gen)
        while True:
            events.append(event)
            event = gen.send(None)
    except StopIteration:
        pass
    return events


def _drain_with_result(gen) -> tuple[list[dict], ContainerResult]:
    """Drain a generator, returning both events and the final result."""
    events = []
    try:
        event = next(gen)
        while True:
            events.append(event)
            event = gen.send(None)
    except StopIteration as stop:
        return events, stop.value
    raise RuntimeError("Generator did not return a result")


def test_invoke_runtime_context_and_subgraph_context_do_not_include_tool_scope():
    runtime_context = _build_invoke_runtime_context(
        invoke_request={
            "delegated_agent": "requirement_agent",
            "requirement_id": "REQ-1",
            "max_tool_call_rounds": 4,
        }
    )
    assert "tool_scope" not in runtime_context
    assert "_tool_scope" not in runtime_context

    svc = FakeGraphService()
    skeleton = _make_invoke_skeleton(svc)
    session_container = next(
        container for container in skeleton.containers if container.container_key == "session"
    )
    session_subgraph = next(
        subgraph
        for subgraph in skeleton.subgraphs
        if subgraph.container_id == session_container.container_id
    )
    context = _build_subgraph_context(
        sg=session_subgraph,
        container=session_container,
        recorder=FakeRecorder(skeleton.graph_id),
        pad=Scratchpad(),
        runtime_context=runtime_context,
    )

    assert "tool_scope" not in context
    assert "_tool_scope" not in context
    assert context["delegated_agent"] == "requirement_agent"


# =========================================================================
# Tests — LLM Subgraph Execution
# =========================================================================


class TestLlmSubgraphExecution:
    """3-node linear template: all llm → Pending → Running → Completed."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        self.skeleton = _make_3node_skeleton(self.svc)
        self.runner = SubgraphRunner()

    def test_all_subgraphs_execute_to_completion(self):
        ai = FakeAIProxy(conclusions=["数据已获取", "分析完成", "报告生成"])
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
            user_message="请执行",
        )
        events, result = _drain_with_result(gen)
        assert isinstance(result, ContainerResult)
        assert result.conclusion != ""

    def test_emits_subgraph_status_events(self):
        ai = FakeAIProxy(conclusions=["c1", "c2", "c3"])
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        events, _ = _drain_with_result(gen)
        status_events = [e for e in events if e.get("event") == "subgraph_status"]
        # 3 subgraphs × 2 events (running + completed) = 6
        assert len(status_events) == 6

    def test_conclusion_contains_last_stage_output(self):
        ai = FakeAIProxy(conclusions=["第一阶段", "第二阶段", "最终结论"])
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        _, result = _drain_with_result(gen)
        assert "最终结论" in result.conclusion

    def test_scratchpad_snapshot_populated(self):
        ai = FakeAIProxy(conclusions=["c1", "c2", "c3"])
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        _, result = _drain_with_result(gen)
        assert len(result.scratchpad_snapshot) > 0

    def test_llm_subgraphs_create_agent_runs(self):
        ai = FakeAIProxy(conclusions=["c1", "c2", "c3"])
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        _events, _result = _drain_with_result(gen)
        assert len(self.svc.agent_runs) == 3


# =========================================================================
# Tests — Handoff Subgraph (Suspend)
# =========================================================================


class TestHandoffSubgraph:
    """llm → handoff: handoff triggers SuspendSignal."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        self.skeleton = _make_handoff_skeleton(self.svc)
        self.runner = SubgraphRunner()

    def test_raises_suspend_signal(self):
        ai = FakeAIProxy(conclusions=["步骤一完成"])
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        with pytest.raises(SuspendSignal) as exc_info:
            _drain(gen)
        assert exc_info.value.subgraph_id is not None

    def test_suspend_signal_carries_handoff_subgraph_id(self):
        ai = FakeAIProxy(conclusions=["步骤一完成"])
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        handoff_sg = next(sg for sg in self.skeleton.subgraphs if sg.node_type == "handoff")
        with pytest.raises(SuspendSignal) as exc_info:
            _drain(gen)
        assert exc_info.value.subgraph_id == handoff_sg.subgraph_id


# =========================================================================
# Tests — Invoke Subgraph (Cross-Container Call)
# =========================================================================


class TestInvokeSubgraph:
    """llm → invoke → (call target container llm) → return."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        self.skeleton = _make_invoke_skeleton(self.svc)
        self.runner = SubgraphRunner()

    def test_invoke_executes_target_container(self):
        # 2 LLM calls: parse (container A) + do_work (container B)
        ai = FakeAIProxy(conclusions=["解析完成", "工作完成"])
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        events, result = _drain_with_result(gen)
        assert isinstance(result, ContainerResult)

    def test_invoke_call_edge_payload_includes_task_description(self):
        import json

        ai = FakeAIProxy(
            conclusions=[
                json.dumps(
                    {
                        "task_description": "用户要求检测 R-1 和 R-2 之间是否存在语义冲突",
                        "operation": "detect_conflict",
                        "requirement_ids": ["R-1", "R-2"],
                    },
                    ensure_ascii=False,
                ),
                "工作完成",
            ]
        )
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        _events, result = _drain_with_result(gen)

        assert isinstance(result, ContainerResult)
        runtime_detail = self.svc.get_graph_detail(self.skeleton.graph_id)
        call_edges = [
            edge for edge in runtime_detail["edges"] if edge.get("edge_type") == "call"
        ]
        assert len(call_edges) == 1
        call_config = call_edges[0].get("config_json") or {}
        assert call_config["task_description"] == "用户要求检测 R-1 和 R-2 之间是否存在语义冲突"
        assert call_config["invoke_payload"]["task_description"] == "用户要求检测 R-1 和 R-2 之间是否存在语义冲突"
        assert call_config["invoke_payload"]["operation"] == "detect_conflict"
        assert call_config["invoke_payload"]["requirement_ids"] == ["R-1", "R-2"]

    def test_invoke_child_scratchpad_does_not_leak_into_parent_container(self):
        import json

        ai = PromptCapturingAIProxy([
            {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps({"conclusion": "解析完成"}, ensure_ascii=False),
                        },
                    }
                ],
            },
            {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-2",
                        "function": {
                            "name": "scratchpad_write",
                            "arguments": json.dumps(
                                {
                                    "entry_type": "note",
                                    "content": "child secret note",
                                },
                                ensure_ascii=False,
                            ),
                        },
                    }
                ],
            },
            {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-3",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps({"conclusion": "工作结果XYZ"}, ensure_ascii=False),
                        },
                    }
                ],
            },
        ])
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        _, result = _drain_with_result(gen)
        found_in_parent = any(
            "child secret note" in str(entry.get("content", ""))
            for entry in result.scratchpad_snapshot
        )
        found_in_store = any(
            "child secret note" in str(entry.get("content", ""))
            for entry in result.scratchpad_store_snapshot
        )
        assert found_in_parent is False
        assert found_in_store is True

    def test_invoke_fans_out_to_multiple_target_containers_concurrently(self):
        parallel_skeleton = _make_parallel_invoke_skeleton(self.svc)
        ai = ConcurrentInvokeAIProxy()
        gen = self.runner.run(
            skeleton=parallel_skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(parallel_skeleton.graph_id),
            actor="test",
        )
        events, result = _drain_with_result(gen)
        assert isinstance(result, ContainerResult)
        assert len([e for e in events if e.get("event") == "subgraph_status" and e["data"].get("status") == "completed"]) >= 4

    def test_invoke_cancels_other_branches_after_first_failure(self):
        parallel_skeleton = _make_parallel_invoke_skeleton(self.svc)
        failing_runtime = _ImmediateFailRuntime(self.svc)
        cancellable_runtime = _CancellableRuntime(self.svc)
        runner = SubgraphRunner(
            agent_runtime_registry=_StubRuntimeRegistry(
                {
                    "session": RuntimeBinding(
                        runtime_id="rt::session",
                        runtime=LocalAgentRuntime(
                            runtime_id="rt::session",
                            execution_graph_service=self.svc,
                        ),
                        implementation_type="local",
                    ),
                    "worker_a": RuntimeBinding(
                        runtime_id="rt::worker-a",
                        runtime=failing_runtime,
                        implementation_type="stub",
                    ),
                    "worker_b": RuntimeBinding(
                        runtime_id="rt::worker-b",
                        runtime=cancellable_runtime,
                        implementation_type="stub",
                    ),
                }
            )
        )

        gen = runner.run(
            skeleton=parallel_skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=FakeAIProxy(conclusions=["解析完成"]),
            graph_service=self.svc,
            recorder=FakeRecorder(parallel_skeleton.graph_id),
            actor="test",
        )

        with pytest.raises(ContainerExecutionError) as exc_info:
            _drain_with_result(gen)

        root_cause = exc_info.value.cause
        assert isinstance(root_cause, ContainerExecutionError)
        assert root_cause.error_code == "branch_failed"
        assert root_cause.agent_run_id == "run-fail"
        assert cancellable_runtime.cancelled_runs == ["run-1"]
        cancelled_runs = [
            row
            for row in self.svc.agent_runs.values()
            if row.get("container_key") == "worker_b"
        ]
        assert len(cancelled_runs) == 1
        assert cancelled_runs[0]["status"] == "cancelled"


# =========================================================================
# Tests — Conditional Routing
# =========================================================================


class TestConditionalRouting:
    """Decision node with conditional_edges → route_key matching."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        self.skeleton = _make_conditional_skeleton(self.svc)
        self.runner = SubgraphRunner()

    def test_route_to_branch_a(self):
        # Decision returns route_key="approve" → should execute branch_a
        ai = FakeAIProxy(
            conclusions=["决策: 通过", "分支A执行完成"],
            route_keys=["approve", None],
        )
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        events, result = _drain_with_result(gen)
        # branch_a should have been executed
        status_events = [e for e in events if e.get("event") == "subgraph_status"]
        completed_ids = [
            e["data"]["subgraph_id"]
            for e in status_events
            if e["data"].get("status") == "completed"
        ]
        branch_a_sg = next(sg for sg in self.skeleton.subgraphs if "branch_a" in sg.subgraph_key)
        assert branch_a_sg.subgraph_id in completed_ids

    def test_route_to_branch_b(self):
        ai = FakeAIProxy(
            conclusions=["决策: 拒绝", "分支B执行完成"],
            route_keys=["reject", None],
        )
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        events, result = _drain_with_result(gen)
        status_events = [e for e in events if e.get("event") == "subgraph_status"]
        completed_ids = [
            e["data"]["subgraph_id"]
            for e in status_events
            if e["data"].get("status") == "completed"
        ]
        branch_b_sg = next(sg for sg in self.skeleton.subgraphs if "branch_b" in sg.subgraph_key)
        assert branch_b_sg.subgraph_id in completed_ids

    def test_no_route_key_falls_through_sequentially(self):
        # No route_key → sequential fallback → branch_a (next by order_index)
        ai = FakeAIProxy(
            conclusions=["决策: 无条件", "顺序执行"],
            route_keys=[None, None],
        )
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        events, result = _drain_with_result(gen)
        status_events = [e for e in events if e.get("event") == "subgraph_status"]
        completed_ids = [
            e["data"]["subgraph_id"]
            for e in status_events
            if e["data"].get("status") == "completed"
        ]
        branch_a_sg = next(sg for sg in self.skeleton.subgraphs if "branch_a" in sg.subgraph_key)
        assert branch_a_sg.subgraph_id in completed_ids


# =========================================================================
# Tests — Resume from Suspended
# =========================================================================


class TestResume:
    """Handoff suspend → resume with user input → continue execution."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        # Template: llm → handoff → llm (need 3 nodes to test resume continuation)
        self.svc.seed_template(
            graph_id="tpl-resume",
            project_id="proj-1",
            containers=[
                {"container_id": "c-1", "container_key": "main", "label": "Main", "role_type": "agent", "order_index": 0},
            ],
            nodes=[
                {"node_id": "n-1", "node_key": "pre", "label": "Pre", "node_type": "llm", "role_type": "agent",
                 "container_id": "c-1", "phase_label": "前置", "task_prompt": "前置处理", "conditional_edges": None, "order_index": 0},
                {"node_id": "n-2", "node_key": "wait_user", "label": "Wait", "node_type": "handoff", "role_type": "agent",
                 "container_id": "c-1", "phase_label": "等待", "task_prompt": "", "conditional_edges": None, "order_index": 1},
                {"node_id": "n-3", "node_key": "post", "label": "Post", "node_type": "llm", "role_type": "agent",
                 "container_id": "c-1", "phase_label": "后续", "task_prompt": "后续处理", "conditional_edges": None, "order_index": 2},
            ],
            edges=[
                {"edge_id": "e-1", "source_node_id": "n-1", "target_node_id": "n-2", "edge_type": "seq", "order_index": 0},
                {"edge_id": "e-2", "source_node_id": "n-2", "target_node_id": "n-3", "edge_type": "seq", "order_index": 1},
            ],
        )
        self.skeleton = TopologyInstantiator().instantiate(
            template_graph_id="tpl-resume", project_id="proj-1", graph_service=self.svc,
        )
        self.runner = SubgraphRunner()

    def test_resume_continues_after_handoff(self):
        # Step 1: run → SuspendSignal at handoff
        ai_run = FakeAIProxy(conclusions=["前置完成"])
        gen_run = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai_run,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        with pytest.raises(SuspendSignal) as exc_info:
            _drain(gen_run)
        suspended_id = exc_info.value.subgraph_id

        # Step 2: resume with user input
        ai_resume = FakeAIProxy(conclusions=["后续完成"])
        gen_resume = self.runner.resume(
            skeleton=self.skeleton,
            suspended_subgraph_id=suspended_id,
            user_input="用户确认继续",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai_resume,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        events, result = _drain_with_result(gen_resume)
        assert isinstance(result, ContainerResult)
        assert "后续完成" in result.conclusion

    def test_resume_emits_status_events(self):
        ai_run = FakeAIProxy(conclusions=["前置完成"])
        gen_run = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai_run,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        with pytest.raises(SuspendSignal) as exc_info:
            _drain(gen_run)
        suspended_id = exc_info.value.subgraph_id

        ai_resume = FakeAIProxy(conclusions=["后续完成"])
        gen_resume = self.runner.resume(
            skeleton=self.skeleton,
            suspended_subgraph_id=suspended_id,
            user_input="继续",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai_resume,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        events, _ = _drain_with_result(gen_resume)
        status_events = [e for e in events if e.get("event") == "subgraph_status"]
        # post subgraph: running + completed = 2 events
        assert len(status_events) == 2


# =========================================================================
# Tests — Error Handling
# =========================================================================


class TestErrorHandling:
    """Errors during subgraph execution raise ContainerExecutionError."""

    def test_llm_failure_raises_container_error(self):
        svc = FakeGraphService()
        skeleton = _make_3node_skeleton(svc)
        runner = SubgraphRunner()

        gen = runner.run(
            skeleton=skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=FailingAIProxy(),
            recorder=FakeRecorder(skeleton.graph_id),
            actor="test",
        )
        with pytest.raises(ContainerExecutionError) as exc_info:
            _drain(gen)
        assert exc_info.value.container_id is not None
        assert exc_info.value.subgraph_id is not None

    def test_failed_subgraph_emits_status_event(self):
        svc = FakeGraphService()
        skeleton = _make_3node_skeleton(svc)
        runner = SubgraphRunner()

        gen = runner.run(
            skeleton=skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=FailingAIProxy(),
            recorder=FakeRecorder(skeleton.graph_id),
            actor="test",
        )
        events = []
        with pytest.raises(ContainerExecutionError):
            while True:
                events.append(next(gen))
        failed_events = [
            e for e in events
            if e.get("event") == "subgraph_status" and e["data"].get("status") == "failed"
        ]
        assert len(failed_events) == 1


# =========================================================================
# Tests — Scratchpad Context
# =========================================================================


class TestScratchpadContext:
    """Verify Scratchpad accumulates stage_output entries across subgraphs."""

    def test_scratchpad_has_entries_for_each_subgraph(self):
        svc = FakeGraphService()
        skeleton = _make_3node_skeleton(svc)
        runner = SubgraphRunner()

        ai = FakeAIProxy(conclusions=["结论1", "结论2", "结论3"])
        gen = runner.run(
            skeleton=skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(skeleton.graph_id),
            actor="test",
        )
        _, result = _drain_with_result(gen)
        stage_outputs = [
            e for e in result.scratchpad_snapshot
            if e.get("entry_type") == "stage_output"
        ]
        # At least 3 stage_output entries (one per subgraph's complete_phase)
        assert len(stage_outputs) >= 3

    def test_next_subgraph_sees_scratchpad_but_not_previous_local_context(self):
        svc = FakeGraphService()
        skeleton = _make_3node_skeleton(svc)
        runner = SubgraphRunner()

        import json

        ai = PromptCapturingAIProxy([
            {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-1",
                        "function": {
                            "name": "dummy",
                            "arguments": json.dumps({"target": "r-1"}, ensure_ascii=False),
                        },
                    }
                ],
            },
            {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-2",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps({"conclusion": "第一阶段完成"}, ensure_ascii=False),
                        },
                    }
                ],
            },
            {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-3",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps({"conclusion": "第二阶段完成"}, ensure_ascii=False),
                        },
                    }
                ],
            },
            {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call-4",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps({"conclusion": "第三阶段完成"}, ensure_ascii=False),
                        },
                    }
                ],
            },
        ])

        tool_executor = FakeToolExecutor()
        tool_executor.get_tools_list = lambda: [
            {"type": "function", "function": {"name": "dummy"}}
        ]
        tool_executor.execute = lambda tool_name, arguments, context: {"ok": True, "req_id": "r-1"}

        _, result = _drain_with_result(runner.run(
            skeleton=skeleton,
            tool_executor=tool_executor,
            ai_proxy_client=ai,
            recorder=FakeRecorder(skeleton.graph_id),
            actor="test",
        ))

        assert "tool_result" in ai.system_prompts[1]
        assert "req_id" in ai.system_prompts[1]
        assert "第一阶段完成" in ai.system_prompts[2]
        assert "tool_result" not in ai.system_prompts[2]
        assert "req_id" not in ai.system_prompts[2]
        assert result.conclusion == "第三阶段完成"
