"""Tests for SubgraphRunner — runtime subgraph execution engine.

All tests use stubs/fakes so that no DB, real LLM, or network is required.
The ``FakeGraphService`` seeds templates and generates runtime skeletons
via ``TopologyInstantiator``; the ``FakeAIProxy`` returns pre-configured
complete_phase tool calls.
"""

from __future__ import annotations

import os
import sys
import uuid

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import pytest

from backend_business.services.agent.execution.subgraph_runner import (
    ContainerResult,
    SubgraphRunner,
)
from backend_business.services.agent.execution.subgraph_state import (
    ContainerExecutionError,
    SuspendSignal,
)
from backend_business.services.agent.execution.topology_instantiator import (
    RuntimeGraphSkeleton,
    TopologyInstantiator,
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

    def test_invoke_return_conclusion_in_scratchpad(self):
        ai = FakeAIProxy(conclusions=["解析完成", "工作结果XYZ"])
        gen = self.runner.run(
            skeleton=self.skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            recorder=FakeRecorder(self.skeleton.graph_id),
            actor="test",
        )
        _, result = _drain_with_result(gen)
        # The invoke subgraph's scratchpad should contain the return conclusion
        found = any("工作结果XYZ" in str(entry.get("content", "")) for entry in result.scratchpad_snapshot)
        assert found, f"Return conclusion not found in scratchpad: {result.scratchpad_snapshot}"


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
