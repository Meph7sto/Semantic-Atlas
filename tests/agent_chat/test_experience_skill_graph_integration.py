from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import uuid

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.execution.graph_executor import GraphExecutor
from backend_business.services.agent.execution.subgraph_runner import SubgraphRunner
from backend_business.services.agent.execution.topology_instantiator import (
    TopologyInstantiator,
)
from backend_business.services.agent.experience import SkillLoader, SkillRegistry, SkillRetriever

_SEED_CONFLICT_SKILL = """---
skill_id: exp_session_controller_conflict_delegate_seed_20260418_001
experience_target: session_controller_conflict_delegate
container_key: conflict_detection
prompt_builder_kind: session_controller_conflict_delegate
node_type: llm
task_pattern_summary: 检测两个需求之间是否冲突
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- 当用户要求检查需求冲突时使用

## 推荐步骤

1. 先定位目标需求
2. 再读取需求详情
3. 最后基于工具结果输出结论

## 常见陷阱

- 不要跳过详情读取

## 结果呈现建议

- 先给出结论，再说明原因
"""


class _RecordingOrchestrator:
    def __init__(self) -> None:
        self.calls: list[dict] = []
        self.feedback_calls: list[dict] = []

    def safe_process_outcome(self, **kwargs):
        self.calls.append(dict(kwargs))
        return None

    def record_injection_feedback(self, **kwargs):
        self.feedback_calls.append(dict(kwargs))
        return None


class _FakeGraphService:
    def __init__(self) -> None:
        self.graphs: dict[str, dict] = {}
        self.containers: dict[str, dict] = {}
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}

    def seed_template(self) -> None:
        graph_id = "tpl-exp"
        self.graphs[graph_id] = {
            "graph_id": graph_id,
            "project_id": "proj-1",
            "graph_type": "execution_topology_template",
        }
        self.containers["c-1"] = {
            "container_id": "c-1",
            "graph_id": graph_id,
            "container_key": "conflict_detection",
            "label": "Conflict",
            "role_type": "agent",
            "order_index": 0,
        }
        self.nodes["n-1"] = {
            "node_id": "n-1",
            "graph_id": graph_id,
            "container_id": "c-1",
            "node_key": "conflict_step",
            "label": "Conflict Step",
            "node_type": "llm",
            "role_type": "agent",
            "phase_label": "冲突检测",
            "task_prompt": "检测冲突",
            "conditional_edges": None,
            "order_index": 0,
            "config_json": {"prompt_builder": "session_controller_conflict_delegate"},
        }

    def get_graph_detail(self, graph_id: str, **_kw) -> dict:
        return {
            "graph": self.graphs.get(graph_id),
            "containers": [
                item for item in self.containers.values() if item.get("graph_id") == graph_id
            ],
            "subgraphs": [],
            "nodes": [item for item in self.nodes.values() if item.get("graph_id") == graph_id],
            "edges": [item for item in self.edges.values() if item.get("graph_id") == graph_id],
        }

    def get_execution_graph(self, graph_id: str) -> dict | None:
        graph = self.graphs.get(graph_id)
        return dict(graph) if graph else None

    def create_runtime_graph(self, *, project_id, name, description="", created_by="", **kw) -> dict:
        graph_id = str(uuid.uuid4())
        graph = {
            "graph_id": graph_id,
            "project_id": project_id,
            "name": name,
            "description": description,
            "graph_type": "agent_runtime_execution",
            "status": kw.get("status", "running"),
            "meta_json": kw.get("meta_json"),
        }
        self.graphs[graph_id] = graph
        return graph

    def create_container(self, *, graph_id, container_key, label, role_type, **kw) -> dict:
        container_id = str(uuid.uuid4())
        container = {
            "container_id": container_id,
            "graph_id": graph_id,
            "container_key": container_key,
            "label": label,
            "role_type": role_type,
            "order_index": kw.get("order_index", 0),
            "config_json": kw.get("config_json"),
        }
        self.containers[container_id] = container
        return container

    def create_subgraph(self, *, graph_id, container_id, subgraph_key, label, task_description, **kw) -> dict:
        subgraph_id = str(uuid.uuid4())
        return {
            "subgraph_id": subgraph_id,
            "graph_id": graph_id,
            "container_id": container_id,
            "subgraph_key": subgraph_key,
            "label": label,
            "task_description": task_description,
            "status": "pending",
            "order_index": kw.get("order_index", 0),
            "config_json": kw.get("config_json"),
        }

    def create_node(self, *, graph_id, node_key, label, node_type, role_type, **kw) -> dict:
        node_id = str(uuid.uuid4())
        node = {
            "node_id": node_id,
            "graph_id": graph_id,
            "container_id": kw.get("container_id"),
            "subgraph_id": kw.get("subgraph_id"),
            "node_key": node_key,
            "label": label,
            "node_type": node_type,
            "role_type": role_type,
            "order_index": kw.get("order_index", 0),
            "config_json": kw.get("config_json") or {},
        }
        self.nodes[node_id] = node
        return node

    def create_edge(self, *, graph_id, source_node_id, target_node_id, edge_type, **kw) -> dict:
        edge_id = str(uuid.uuid4())
        edge = {
            "edge_id": edge_id,
            "graph_id": graph_id,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "edge_type": edge_type,
            "order_index": kw.get("order_index", 0),
            "config_json": kw.get("config_json"),
        }
        self.edges[edge_id] = edge
        return edge

    def get_node(self, node_id: str) -> dict:
        return dict(self.nodes[node_id])

    def update_node(self, *, node_id, **kw) -> dict:
        self.nodes[node_id].update({key: value for key, value in kw.items() if value is not None})
        return dict(self.nodes[node_id])

    def patch_graph_meta(self, graph_id, meta_patch, status=None, updated_by=""):
        graph = self.graphs[graph_id]
        meta = dict(graph.get("meta_json") or {})
        meta.update(meta_patch or {})
        graph["meta_json"] = meta
        if status is not None:
            graph["status"] = status
        return dict(graph)


class _FakeRecorder:
    def __init__(self, graph_id: str = "fake-graph") -> None:
        self.graph_id = graph_id
        self.turn_index = 1
        self._containers = {"agent": "fake-container-id"}
        self._stages: dict[str, dict] = {}
        self._task_context: dict[str, str] = {}

    def stage_node_key(self, base_key: str) -> str:
        return f"turn_{self.turn_index}__{base_key}"

    def stage_label(self, base_label: str) -> str:
        return f"{base_label} (Turn {self.turn_index})"

    def start_stage(self, *, node_key, label, node_type, role_type, container_key, created_by, input_summary, **_kw):
        self._stages[node_key] = {"status": "running"}

    def record_tool_call_result(self, node_key, *, created_by, tool_name, request_payload, result_payload):
        _ = node_key, created_by, tool_name, request_payload, result_payload

    def complete_stage(self, node_key, *, created_by, output_summary, **_kw):
        self._stages[node_key] = {"status": "completed", "output_summary": output_summary}

    def enter_subgraph(self, *, subgraph_id, start_node_id):
        _ = subgraph_id, start_node_id

    def leave_subgraph(self, *, end_node_id, created_by):
        _ = end_node_id, created_by


class _FakeToolExecutor:
    def get_tools_list(self, context=None) -> list[dict]:
        _ = context
        return []

    def execute(self, tool_name: str, arguments: dict, context: dict) -> dict:
        _ = tool_name, arguments, context
        return {"ok": True}


class _FakeAIProxy:
    def __init__(self, reply: str | None = None) -> None:
        self._reply = reply
        self._call_count = 0
        self.system_prompts: list[str] = []

    def chat_completion_with_tools(self, *, messages, tools, **_kw) -> dict:
        self._call_count += 1
        if messages:
            self.system_prompts.append(str(messages[0].get("content") or ""))
        if self._reply is not None:
            return {
                "content": self._reply,
                "finish_reason": "stop",
                "tool_calls": [],
            }
        return {
            "content": "",
            "finish_reason": "tool_calls",
            "tool_calls": [
                {
                    "id": f"call_{self._call_count}",
                    "function": {
                        "name": "complete_phase",
                        "arguments": json.dumps(
                            {"conclusion": "阶段完成"},
                            ensure_ascii=False,
                        ),
                    },
                }
            ],
        }


def _drain_with_result(gen):
    events = []
    try:
        while True:
            events.append(next(gen))
    except StopIteration as stop:
        return events, stop.value


def _seed_root(root: Path) -> None:
    target_dir = root / "session_controller_conflict_delegate"
    (target_dir / "archive").mkdir(parents=True, exist_ok=True)
    (target_dir / "current.md").write_text(_SEED_CONFLICT_SKILL, encoding="utf-8")
    (root / "_registry.yaml").write_text(
        "version: 1\n"
        "targets:\n"
        "  session_controller_conflict_delegate:\n"
        "    skill_id: exp_session_controller_conflict_delegate_seed_20260418_001\n"
        "    current_skill_path: session_controller_conflict_delegate/current.md\n"
        "    iteration: 1\n"
        "    invocation_count: 0\n"
        "    injection_miss_count: 0\n",
        encoding="utf-8",
    )


def test_subgraph_runner_invokes_experience_writeback_for_llm_subgraph():
    service = _FakeGraphService()
    service.seed_template()
    skeleton = TopologyInstantiator().instantiate(
        template_graph_id="tpl-exp",
        project_id="proj-1",
        graph_service=service,
    )
    orchestrator = _RecordingOrchestrator()
    runner = SubgraphRunner(experience_orchestrator=orchestrator)

    _events, result = _drain_with_result(
        runner.run(
            skeleton=skeleton,
            tool_executor=_FakeToolExecutor(),
            ai_proxy_client=_FakeAIProxy(reply="冲突检测完成"),
            graph_service=service,
            recorder=_FakeRecorder(skeleton.graph_id),
            actor="tester",
            user_message="请检测两个需求是否冲突",
        )
    )

    assert result.conclusion == "冲突检测完成"
    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["target"].target_id == "session_controller_conflict_delegate"


def test_graph_executor_invokes_experience_writeback_for_normal_conversation():
    service = _FakeGraphService()
    orchestrator = _RecordingOrchestrator()
    executor = GraphExecutor(experience_orchestrator=orchestrator)

    _events, result = _drain_with_result(
        executor._drive_normal_conversation(
            graph_id="graph-1",
            container_id="container-1",
            user_message="你好",
            tool_executor=_FakeToolExecutor(),
            ai_proxy_client=_FakeAIProxy(reply="你好，我在。"),
            graph_service=service,
            recorder=_FakeRecorder("graph-1"),
            actor="tester",
            stage_container_key="agent",
        )
    )

    assert result.status == "succeeded"
    assert len(orchestrator.calls) == 1
    assert orchestrator.calls[0]["runtime_status"] == "succeeded"


def test_graph_executor_invokes_root_writeback_for_graph_execution():
    service = _FakeGraphService()
    service.seed_template()
    skeleton = TopologyInstantiator().instantiate(
        template_graph_id="tpl-exp",
        project_id="proj-1",
        graph_service=service,
    )
    orchestrator = _RecordingOrchestrator()
    executor = GraphExecutor(experience_orchestrator=orchestrator)

    _events, result = _drain_with_result(
        executor._drive_runner(
            skeleton=skeleton,
            tool_executor=_FakeToolExecutor(),
            ai_proxy_client=_FakeAIProxy(reply="冲突检测完成"),
            graph_service=service,
            recorder=_FakeRecorder(skeleton.graph_id),
            actor="tester",
            user_message="请检测两个需求是否冲突",
        )
    )

    assert result.status == "succeeded"
    assert len(orchestrator.calls) == 2
    assert orchestrator.calls[-1]["runtime_status"] == "succeeded"


def test_subgraph_runner_injects_matching_skill_into_graph_prompt(tmp_path: Path):
    root = tmp_path / ".agent_skills"
    _seed_root(root)
    service = _FakeGraphService()
    service.seed_template()
    skeleton = TopologyInstantiator().instantiate(
        template_graph_id="tpl-exp",
        project_id="proj-1",
        graph_service=service,
    )
    ai_proxy = _FakeAIProxy(reply="冲突检测完成")
    recorder = _FakeRecorder(skeleton.graph_id)
    recorder._task_context = {
        "user_message": "请检查支付需求和退款需求是否冲突",
        "project_id": "proj-1",
    }
    runner = SubgraphRunner(
        experience_retriever=SkillRetriever(root),
        skill_loader=SkillLoader(),
    )

    _events, result = _drain_with_result(
        runner.run(
            skeleton=skeleton,
            tool_executor=_FakeToolExecutor(),
            ai_proxy_client=ai_proxy,
            graph_service=service,
            recorder=recorder,
            actor="tester",
            user_message="请检查支付需求和退款需求是否冲突",
        )
    )

    assert result.conclusion == "冲突检测完成"
    assert ai_proxy.system_prompts
    assert "## 已命中的经验技能" in ai_proxy.system_prompts[0]
    assert "exp_session_controller_conflict_delegate_seed_20260418_001" in ai_proxy.system_prompts[0]
    meta = service.get_execution_graph(skeleton.graph_id).get("meta_json") or {}
    assert meta["injected_skill_id"] == "exp_session_controller_conflict_delegate_seed_20260418_001"
    entry = SkillRegistry(root).get_target("session_controller_conflict_delegate")
    assert entry is not None
    assert entry["invocation_count"] == 1
    assert entry["skill_hit_count"] == 1
