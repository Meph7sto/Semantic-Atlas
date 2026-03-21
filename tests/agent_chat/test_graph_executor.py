"""Tests for GraphExecutor — top-level graph execution orchestrator.

All tests use stubs/fakes so that no DB, real LLM, or network is required.
Reuses the same FakeGraphService / FakeAIProxy / FakeToolExecutor / FakeRecorder
pattern established in test_subgraph_runner.py.
"""

from __future__ import annotations

import json
import os
import sys
import uuid

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import pytest

from backend_business.services.agent.execution.graph_executor import (
    ExecutionResult,
    GraphExecutor,
)
from backend_business.services.agent.execution.topology_instantiator import (
    TopologyInstantiator,
)


# =========================================================================
# Stubs (shared pattern with test_subgraph_runner.py)
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
    """Returns a pre-configured complete_phase tool call (simulating LLM)."""

    def __init__(
        self,
        conclusions: list[str] | None = None,
        route_keys: list[str | None] | None = None,
    ) -> None:
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

    def __init__(self, graph_id: str = "fake-graph", graph_service: FakeGraphService | None = None) -> None:
        self.graph_id = graph_id
        self._graph_service = graph_service
        self.turn_index = 1
        self._containers: dict[str, str] = {"agent": "fake-container-id"}
        self._stages: dict[str, dict] = {}

    def stage_node_key(self, base_key: str) -> str:
        return f"turn_{self.turn_index}__{base_key}"

    def stage_label(self, base_label: str) -> str:
        return f"{base_label} (Turn {self.turn_index})"

    def start_stage(self, *, node_key, label, node_type, role_type, container_key, created_by, input_summary, **_kw):
        self._stages[node_key] = {"status": "running"}
        if self._graph_service is None or self.graph_id not in self._graph_service.graphs:
            return

        detail = self._graph_service.get_graph_detail(self.graph_id)
        containers = detail.get("containers") or []
        container = next(
            (item for item in containers if item.get("container_key") == container_key),
            None,
        )
        container_id = container.get("container_id") if container else None
        self._graph_service.create_node(
            graph_id=self.graph_id,
            container_id=container_id,
            node_key=node_key,
            label=label,
            node_type=node_type,
            role_type=role_type,
        )

    def record_tool_call_result(self, node_key, *, created_by, tool_name, request_payload, result_payload):
        pass

    def complete_stage(self, node_key, *, created_by, output_summary, **_kw):
        self._stages[node_key] = {"status": "completed"}


class FailingAIProxy:
    """AI proxy that raises an exception (simulating LLM failure)."""

    def chat_completion_with_tools(self, **_kw) -> dict:
        raise RuntimeError("LLM API 调用失败")


# =========================================================================
# Template fixture helpers
# =========================================================================


def _seed_3node_template(svc: FakeGraphService) -> None:
    """Seed a 3-node linear LLM template."""
    svc.seed_template(
        graph_id="tpl-3",
        project_id="proj-1",
        containers=[
            {"container_id": "c-1", "container_key": "agent_container", "label": "Agent",
             "role_type": "agent", "order_index": 0},
        ],
        nodes=[
            {"node_id": "n-1", "node_key": "fetch", "label": "Fetch", "node_type": "llm",
             "role_type": "agent", "container_id": "c-1", "phase_label": "获取",
             "task_prompt": "获取数据", "conditional_edges": None, "order_index": 0},
            {"node_id": "n-2", "node_key": "analyze", "label": "Analyze", "node_type": "llm",
             "role_type": "agent", "container_id": "c-1", "phase_label": "分析",
             "task_prompt": "分析数据", "conditional_edges": None, "order_index": 1},
            {"node_id": "n-3", "node_key": "report", "label": "Report", "node_type": "llm",
             "role_type": "agent", "container_id": "c-1", "phase_label": "报告",
             "task_prompt": "生成报告", "conditional_edges": None, "order_index": 2},
        ],
        edges=[
            {"edge_id": "e-1", "source_node_id": "n-1", "target_node_id": "n-2",
             "edge_type": "seq", "order_index": 0},
            {"edge_id": "e-2", "source_node_id": "n-2", "target_node_id": "n-3",
             "edge_type": "seq", "order_index": 1},
        ],
    )


def _seed_handoff_template(svc: FakeGraphService) -> None:
    """Seed a 3-node template: llm → handoff → llm (for resume testing)."""
    svc.seed_template(
        graph_id="tpl-handoff",
        project_id="proj-1",
        containers=[
            {"container_id": "c-1", "container_key": "main", "label": "Main",
             "role_type": "agent", "order_index": 0},
        ],
        nodes=[
            {"node_id": "n-1", "node_key": "pre", "label": "Pre", "node_type": "llm",
             "role_type": "agent", "container_id": "c-1", "phase_label": "前置",
             "task_prompt": "前置处理", "conditional_edges": None, "order_index": 0},
            {"node_id": "n-2", "node_key": "wait_user", "label": "Wait", "node_type": "handoff",
             "role_type": "agent", "container_id": "c-1", "phase_label": "等待",
             "task_prompt": "", "conditional_edges": None, "order_index": 1},
            {"node_id": "n-3", "node_key": "post", "label": "Post", "node_type": "llm",
             "role_type": "agent", "container_id": "c-1", "phase_label": "后续",
             "task_prompt": "后续处理", "conditional_edges": None, "order_index": 2},
        ],
        edges=[
            {"edge_id": "e-1", "source_node_id": "n-1", "target_node_id": "n-2",
             "edge_type": "seq", "order_index": 0},
            {"edge_id": "e-2", "source_node_id": "n-2", "target_node_id": "n-3",
             "edge_type": "seq", "order_index": 1},
        ],
    )


def _drain_with_result(gen) -> tuple[list[dict], ExecutionResult]:
    """Drain a generator, returning both events and the final ExecutionResult."""
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
# Tests — Happy Path (template → skeleton → run → Succeeded)
# =========================================================================


class TestHappyPath:
    """3-node linear LLM template → GraphExecutor.execute() → Succeeded."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        _seed_3node_template(self.svc)
        self.executor = GraphExecutor()

    def test_execute_returns_succeeded(self):
        ai = FakeAIProxy(conclusions=["数据已获取", "分析完成", "报告生成"])
        gen = self.executor.execute(
            template_graph_id="tpl-3",
            project_id="proj-1",
            user_message="请执行",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(),
            actor="test",
        )
        events, result = _drain_with_result(gen)
        assert isinstance(result, ExecutionResult)
        assert result.status == "succeeded"
        assert result.graph_id != ""
        assert result.final_output is not None
        assert result.error is None

    def test_execute_emits_skeleton_ready_event(self):
        ai = FakeAIProxy(conclusions=["c1", "c2", "c3"])
        gen = self.executor.execute(
            template_graph_id="tpl-3",
            project_id="proj-1",
            user_message="请执行",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(),
            actor="test",
        )
        events, _ = _drain_with_result(gen)
        skeleton_events = [e for e in events if e.get("event") == "skeleton_ready"]
        assert len(skeleton_events) == 1
        assert "graph_id" in skeleton_events[0]["data"]
        assert skeleton_events[0]["data"]["subgraph_count"] == 3

    def test_graph_status_persisted_as_succeeded(self):
        ai = FakeAIProxy(conclusions=["c1", "c2", "c3"])
        gen = self.executor.execute(
            template_graph_id="tpl-3",
            project_id="proj-1",
            user_message="请执行",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(),
            actor="test",
        )
        _, result = _drain_with_result(gen)
        graph = self.svc.graphs.get(result.graph_id, {})
        assert graph.get("status") == "succeeded"


# =========================================================================
# Tests — Handoff Suspend + Resume → Succeeded
# =========================================================================


class TestHandoffAndResume:
    """llm → handoff → suspended, then resume → llm → succeeded."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        _seed_handoff_template(self.svc)
        self.executor = GraphExecutor()

    def _instantiate_and_execute(
        self, ai: FakeAIProxy,
    ) -> tuple[ExecutionResult, "RuntimeGraphSkeleton"]:
        """Instantiate skeleton first, then drive the runner.

        Returns both the result and the skeleton so that resume() can
        reuse the *same* skeleton (with matching subgraph IDs).
        """
        from backend_business.services.agent.execution.topology_instantiator import RuntimeGraphSkeleton

        skeleton = TopologyInstantiator().instantiate(
            template_graph_id="tpl-handoff",
            project_id="proj-1",
            graph_service=self.svc,
            created_by="test",
        )
        gen = self.executor._drive_runner(
            skeleton=skeleton,
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(skeleton.graph_id),
            actor="test",
            user_message="请执行",
        )
        _, result = _drain_with_result(gen)
        return result, skeleton

    def test_execute_returns_suspended(self):
        ai = FakeAIProxy(conclusions=["前置完成"])
        gen = self.executor.execute(
            template_graph_id="tpl-handoff",
            project_id="proj-1",
            user_message="请执行",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(),
            actor="test",
        )
        _, result = _drain_with_result(gen)
        assert result.status == "suspended"
        assert result.suspended_subgraph_id is not None
        assert result.error is None

    def test_graph_status_persisted_as_suspended(self):
        ai = FakeAIProxy(conclusions=["前置完成"])
        gen = self.executor.execute(
            template_graph_id="tpl-handoff",
            project_id="proj-1",
            user_message="请执行",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(),
            actor="test",
        )
        _, result = _drain_with_result(gen)
        graph = self.svc.graphs.get(result.graph_id, {})
        assert graph.get("status") == "suspended"

    def test_resume_returns_succeeded(self):
        # Step 1: instantiate + run → suspended (keeping the skeleton)
        ai_run = FakeAIProxy(conclusions=["前置完成"])
        run_result, skeleton = self._instantiate_and_execute(ai_run)
        assert run_result.status == "suspended"

        # Step 2: resume with the SAME skeleton → succeeded
        ai_resume = FakeAIProxy(conclusions=["后续完成"])
        gen_resume = self.executor.resume(
            skeleton=skeleton,
            suspended_subgraph_id=run_result.suspended_subgraph_id,
            user_input="用户确认继续",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai_resume,
            graph_service=self.svc,
            recorder=FakeRecorder(skeleton.graph_id),
            actor="test",
        )
        _, resume_result = _drain_with_result(gen_resume)
        assert resume_result.status == "succeeded"
        assert resume_result.final_output is not None


# =========================================================================
# Tests — Execution Failure → Failed
# =========================================================================


class TestExecutionFailure:
    """LLM failure → GraphExecutor returns Failed status."""

    def test_execute_returns_failed_on_llm_error(self):
        svc = FakeGraphService()
        _seed_3node_template(svc)
        executor = GraphExecutor()

        gen = executor.execute(
            template_graph_id="tpl-3",
            project_id="proj-1",
            user_message="请执行",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=FailingAIProxy(),
            graph_service=svc,
            recorder=FakeRecorder(),
            actor="test",
        )
        _, result = _drain_with_result(gen)
        assert result.status == "failed"
        assert result.error is not None
        assert result.error != ""

    def test_graph_status_persisted_as_failed(self):
        svc = FakeGraphService()
        _seed_3node_template(svc)
        executor = GraphExecutor()

        gen = executor.execute(
            template_graph_id="tpl-3",
            project_id="proj-1",
            user_message="请执行",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=FailingAIProxy(),
            graph_service=svc,
            recorder=FakeRecorder(),
            actor="test",
        )
        _, result = _drain_with_result(gen)
        graph = svc.graphs.get(result.graph_id, {})
        assert graph.get("status") == "failed"

    def test_execute_returns_failed_on_invalid_template(self):
        svc = FakeGraphService()
        # No template seeded → instantiation error
        executor = GraphExecutor()

        gen = executor.execute(
            template_graph_id="nonexistent-tpl",
            project_id="proj-1",
            user_message="请执行",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=FakeAIProxy(),
            graph_service=svc,
            recorder=FakeRecorder(),
            actor="test",
        )
        _, result = _drain_with_result(gen)
        assert result.status == "failed"
        assert "实例化" in (result.error or "")


# =========================================================================
# Stubs — Judge Gate AI Proxies
# =========================================================================


class NoTopologyJudgeAIProxy:
    """AI proxy for the 'no topology needed' path.

    First call (from judge ToolLoopRunner): calls complete_phase with expand_topology=false.
    Second call (from normal conversation ToolLoopRunner): returns a plain reply.
    """

    def __init__(self, reply: str = "这是一个普通对话回复。") -> None:
        self._reply = reply
        self._call_count = 0

    def chat_completion_with_tools(self, *, messages, tools, **_kw) -> dict:
        self._call_count += 1
        if self._call_count == 1:
            # Judge call → complete_phase with expand_topology=false
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call_judge_1",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps({
                                "conclusion": "任务足够简单，不需要展开拓扑图",
                                "expand_topology": False,
                            }),
                        },
                    },
                ],
            }
        # Normal conversation call from ToolLoopRunner
        return {
            "content": self._reply,
            "finish_reason": "stop",
            "tool_calls": [],
        }


class RelevantJudgeThenLLMAIProxy:
    """AI proxy that judges as relevant (via complete_phase), then acts as normal LLM.

    First call (from judge ToolLoopRunner): calls complete_phase with explicit topology decision.
    Subsequent calls (from SubgraphRunner ToolLoopRunner): return complete_phase tool calls.
    """

    def __init__(
        self,
        *,
        selected_template_id: str,
        conclusions: list[str],
    ) -> None:
        self._selected_template_id = selected_template_id
        self._conclusions = conclusions
        self._call_count = 0

    def chat_completion_with_tools(self, *, messages, tools, **_kw) -> dict:
        self._call_count += 1
        if self._call_count == 1:
            # Judge call → complete_phase with explicit topology selection
            return {
                "content": "",
                "finish_reason": "tool_calls",
                "tool_calls": [
                    {
                        "id": "call_judge_1",
                        "function": {
                            "name": "complete_phase",
                            "arguments": json.dumps({
                                "conclusion": "需要展开拓扑图进行冲突检测",
                                "expand_topology": True,
                                "target_template_graph_id": self._selected_template_id,
                            }),
                        },
                    },
                ],
            }
        # Subsequent LLM calls → complete_phase
        idx = min(self._call_count - 2, len(self._conclusions) - 1)
        conclusion = self._conclusions[idx]
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": f"call_{self._call_count}",
                    "function": {
                        "name": "complete_phase",
                        "arguments": json.dumps(
                            {"conclusion": conclusion}, ensure_ascii=False
                        ),
                    },
                },
            ],
        }


class InvalidJudgeDecisionAIProxy:
    """Judge returns an explicit but invalid topology selection."""

    def chat_completion_with_tools(self, *, messages, tools, **_kw) -> dict:
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": "call_judge_invalid",
                    "function": {
                        "name": "complete_phase",
                        "arguments": json.dumps({
                            "conclusion": "需要展开拓扑图",
                            "expand_topology": True,
                            "target_template_graph_id": "tpl-missing",
                        }),
                    },
                },
            ],
        }


class ExplodingJudgeAIProxy:
    """Judge call fails before returning any decision."""

    def chat_completion_with_tools(self, *, messages, tools, **_kw) -> dict:
        raise RuntimeError("judge model unavailable")


# =========================================================================
# Tests — Judge Gate (integrated into GraphExecutor via ToolLoopRunner)
# =========================================================================


class TestJudgeGate:
    """Judge gate: [start] → [judge via ToolLoopRunner] → topology or normal conversation."""

    _CANDIDATES = [
        {"graph_id": "tpl-3", "name": "三阶段检测", "description": "三阶段冲突检测"},
        {"graph_id": "tpl-dummy", "name": "备选模板", "description": "备选"},
    ]

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        _seed_3node_template(self.svc)

    def test_no_topology_enters_normal_conversation(self):
        """No topology needed → normal conversation via ToolLoopRunner → succeeded."""
        ai = NoTopologyJudgeAIProxy(reply="你好！有什么可以帮助你的吗？")
        executor = GraphExecutor()

        gen = executor.execute(
            candidate_templates=self._CANDIDATES,
            project_id="proj-1",
            user_message="今天天气怎么样？",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(graph_service=self.svc),
            actor="test",
        )
        events, result = _drain_with_result(gen)

        # Result: succeeded with the conversation reply
        assert result.status == "succeeded"
        assert result.graph_id != ""
        assert result.final_output == "你好！有什么可以帮助你的吗？"

        # Judge event is emitted
        judge_events = [e for e in events if e["event"] == "intent_judge_completed"]
        assert len(judge_events) == 1
        assert judge_events[0]["data"]["selected_template_id"] is None
        assert judge_events[0]["data"]["expand_topology"] is False

        # Gate skeleton is still created before judge
        skeleton_events = [e for e in events if e["event"] == "skeleton_ready"]
        assert len(skeleton_events) == 1
        assert skeleton_events[0]["data"]["subgraph_count"] == 0

        # DB: start node in the graph (created by _run_intent_gate)
        graph_nodes = [
            n for n in self.svc.nodes.values()
            if n.get("graph_id") == result.graph_id
        ]
        start_nodes = [n for n in graph_nodes if n["node_key"] == "start"]
        assert len(start_nodes) == 1
        judge_nodes = [
            n for n in graph_nodes
            if "intent_judge_r" in str(n.get("node_key") or "")
        ]
        assert len(judge_nodes) == 1

        graph_edges = [
            e for e in self.svc.edges.values()
            if e.get("graph_id") == result.graph_id
        ]
        assert any(
            e.get("source_node_id") == start_nodes[0]["node_id"]
            and e.get("target_node_id") == judge_nodes[0]["node_id"]
            and e.get("edge_type") == "seq"
            for e in graph_edges
        )

        # Graph status succeeded
        graph = self.svc.graphs.get(result.graph_id, {})
        assert graph.get("status") == "succeeded"

    def test_relevant_proceeds_to_topology_execution(self):
        """Relevant message → instantiate topology → execute → succeeded."""
        ai = RelevantJudgeThenLLMAIProxy(
            selected_template_id="tpl-3",
            conclusions=["数据已获取", "分析完成", "报告生成"],
        )
        executor = GraphExecutor()

        gen = executor.execute(
            candidate_templates=self._CANDIDATES,
            project_id="proj-1",
            user_message="请检测需求冲突",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(graph_service=self.svc),
            actor="test",
        )
        events, result = _drain_with_result(gen)

        assert result.status == "succeeded"
        assert result.graph_id != ""
        assert result.final_output is not None

        # Both judge and skeleton events
        judge_events = [e for e in events if e["event"] == "intent_judge_completed"]
        assert len(judge_events) == 1
        assert judge_events[0]["data"]["selected_template_id"] == "tpl-3"
        assert judge_events[0]["data"]["expand_topology"] is True

        skeleton_events = [e for e in events if e["event"] == "skeleton_ready"]
        assert len(skeleton_events) == 1
        assert skeleton_events[0]["data"]["subgraph_count"] == 0

        expand_events = [e for e in events if e["event"] == "topology_expanded"]
        assert len(expand_events) == 1
        assert expand_events[0]["data"]["subgraph_count"] == 3

        skeleton_index = events.index(skeleton_events[0])
        judge_index = events.index(judge_events[0])
        expand_index = events.index(expand_events[0])
        assert skeleton_index < judge_index < expand_index

    def test_no_candidates_backward_compatible(self):
        """When no candidate_templates is set, behaviour is identical to before."""
        ai = FakeAIProxy(conclusions=["c1", "c2", "c3"])
        executor = GraphExecutor()

        gen = executor.execute(
            template_graph_id="tpl-3",
            project_id="proj-1",
            user_message="请执行",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(),
            actor="test",
        )
        events, result = _drain_with_result(gen)

        assert result.status == "succeeded"
        # No judge events emitted
        judge_events = [e for e in events if e["event"] == "intent_judge_completed"]
        assert len(judge_events) == 0

    def test_container_not_duplicated_when_topology_expanded(self):
        """When judge selects a topology, the pre-existing container is reused."""
        ai = RelevantJudgeThenLLMAIProxy(
            selected_template_id="tpl-3",
            conclusions=["c1", "c2", "c3"],
        )
        executor = GraphExecutor()

        gen = executor.execute(
            candidate_templates=self._CANDIDATES,
            project_id="proj-1",
            user_message="请检测需求冲突",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(graph_service=self.svc),
            actor="test",
        )
        _, result = _drain_with_result(gen)

        # Count containers belonging to the runtime graph
        runtime_containers = [
            c for c in self.svc.containers.values()
            if c.get("graph_id") == result.graph_id
        ]
        # Should be exactly 1 (reused), not 2 (duplicated)
        assert len(runtime_containers) == 1

    def test_invalid_judge_selection_fails_instead_of_falling_back(self):
        ai = InvalidJudgeDecisionAIProxy()
        executor = GraphExecutor()

        gen = executor.execute(
            candidate_templates=self._CANDIDATES,
            project_id="proj-1",
            user_message="请检测需求冲突",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(graph_service=self.svc),
            actor="test",
        )
        events, result = _drain_with_result(gen)

        assert result.status == "failed"
        assert "不在候选列表中" in (result.error or "")
        assert [e for e in events if e["event"] == "intent_judge_completed"] == []

    def test_judge_exception_fails_instead_of_falling_back(self):
        ai = ExplodingJudgeAIProxy()
        executor = GraphExecutor()

        gen = executor.execute(
            candidate_templates=self._CANDIDATES,
            project_id="proj-1",
            user_message="请检测需求冲突",
            tool_executor=FakeToolExecutor(),
            ai_proxy_client=ai,
            graph_service=self.svc,
            recorder=FakeRecorder(graph_service=self.svc),
            actor="test",
        )
        events, result = _drain_with_result(gen)

        assert result.status == "failed"
        assert "judge 执行异常" in (result.error or "")
        assert "judge model unavailable" in (result.error or "")
        assert [e for e in events if e["event"] == "intent_judge_completed"] == []
        graph = self.svc.graphs.get(result.graph_id, {})
        assert graph.get("status") == "failed"
