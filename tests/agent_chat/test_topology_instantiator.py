"""Tests for TopologyInstantiator — skeleton instantiation.

All tests use an in-memory fake ``ExecutionGraphService`` so that no DB
is required. The fake stores created entities in plain dicts and returns
them in the same shape as the real repository layer.
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

from backend_business.services.agent.execution.topology_instantiator import (
    InstantiationError,
    RuntimeGraphSkeleton,
    TopologyInstantiator,
)


# =========================================================================
# In-memory fake ExecutionGraphService
# =========================================================================


class FakeGraphService:
    """Minimal in-memory stand-in for ExecutionGraphService."""

    def __init__(self) -> None:
        self.graphs: dict[str, dict] = {}
        self.containers: dict[str, dict] = {}
        self.subgraphs: dict[str, dict] = {}
        self.nodes: dict[str, dict] = {}
        self.edges: dict[str, dict] = {}

    # -- seed helpers (used by test fixtures) ----------------------------------

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

    # -- ExecutionGraphService API surface used by TopologyInstantiator --------

    def get_graph_detail(self, graph_id: str, **_kw) -> dict:
        graph = self.graphs.get(graph_id)
        containers = [c for c in self.containers.values() if c.get("graph_id") == graph_id]
        nodes = [n for n in self.nodes.values() if n.get("graph_id") == graph_id]
        edges = [e for e in self.edges.values() if e.get("graph_id") == graph_id]
        return {
            "graph": graph,
            "containers": containers,
            "subgraphs": [],
            "nodes": nodes,
            "edges": edges,
        }

    def create_runtime_graph(self, *, project_id, name, description="", created_by="", **kwargs) -> dict:
        gid = str(uuid.uuid4())
        g = {
            "graph_id": gid,
            "project_id": project_id,
            "name": name,
            "description": description,
            "graph_type": "agent_runtime_execution",
            "status": kwargs.get("status", "running"),
            "meta_json": kwargs.get("meta_json"),
        }
        self.graphs[gid] = g
        return g

    def create_container(self, *, graph_id, container_key, label, role_type, **kwargs) -> dict:
        cid = str(uuid.uuid4())
        c = {
            "container_id": cid,
            "graph_id": graph_id,
            "container_key": container_key,
            "label": label,
            "role_type": role_type,
            "config_json": kwargs.get("config_json"),
            "order_index": kwargs.get("order_index", 0),
        }
        self.containers[cid] = c
        return c

    def create_subgraph(self, *, graph_id, container_id, subgraph_key, label, task_description, **kwargs) -> dict:
        sid = str(uuid.uuid4())
        sg = {
            "subgraph_id": sid,
            "graph_id": graph_id,
            "container_id": container_id,
            "subgraph_key": subgraph_key,
            "label": label,
            "task_description": task_description,
            "status": "pending",
            "order_index": kwargs.get("order_index", 0),
            "config_json": kwargs.get("config_json"),
        }
        self.subgraphs[sid] = sg
        return sg

    def create_node(self, *, graph_id, node_key, label, node_type, role_type, **kwargs) -> dict:
        nid = str(uuid.uuid4())
        n = {
            "node_id": nid,
            "graph_id": graph_id,
            "container_id": kwargs.get("container_id"),
            "subgraph_id": kwargs.get("subgraph_id"),
            "node_key": node_key,
            "label": label,
            "node_type": node_type,
            "role_type": role_type,
            "order_index": kwargs.get("order_index", 0),
        }
        self.nodes[nid] = n
        return n

    def create_edge(self, *, graph_id, source_node_id, target_node_id, edge_type, **kwargs) -> dict:
        eid = str(uuid.uuid4())
        e = {
            "edge_id": eid,
            "graph_id": graph_id,
            "source_node_id": source_node_id,
            "target_node_id": target_node_id,
            "edge_type": edge_type,
            "label": kwargs.get("label"),
            "condition_expr": kwargs.get("condition_expr"),
            "config_json": kwargs.get("config_json"),
            "order_index": kwargs.get("order_index", 0),
        }
        self.edges[eid] = e
        return e


# =========================================================================
# Fixtures
# =========================================================================


def _make_3node_template(svc: FakeGraphService, project_id: str = "proj-1") -> str:
    """Seed a simple 3-node linear template and return the graph_id.

    Container: agent_container
    Nodes:     fetch_states (llm) → generate_pairs (llm) → semantic_verdict (llm)
    Edges:     two seq edges connecting them linearly.
    """
    graph_id = "tpl-3node"
    c1_id = "c-agent"

    svc.seed_template(
        graph_id=graph_id,
        project_id=project_id,
        name="conflict_detection",
        containers=[
            {
                "container_id": c1_id,
                "container_key": "agent_container",
                "label": "Agent Container",
                "role_type": "agent",
                "order_index": 0,
            },
        ],
        nodes=[
            {
                "node_id": "n-fetch",
                "node_key": "fetch_states",
                "label": "Fetch States",
                "node_type": "llm",
                "role_type": "agent",
                "container_id": c1_id,
                "phase_label": "状态获取",
                "task_prompt": "请获取所有需求的状态",
                "conditional_edges": None,
                "order_index": 0,
            },
            {
                "node_id": "n-gen",
                "node_key": "generate_pairs",
                "label": "Generate Pairs",
                "node_type": "llm",
                "role_type": "agent",
                "container_id": c1_id,
                "phase_label": "候选对生成",
                "task_prompt": "请生成候选冲突对",
                "conditional_edges": None,
                "order_index": 1,
            },
            {
                "node_id": "n-verdict",
                "node_key": "semantic_verdict",
                "label": "Semantic Verdict",
                "node_type": "llm",
                "role_type": "agent",
                "container_id": c1_id,
                "phase_label": "语义裁决",
                "task_prompt": "请进行语义裁决",
                "conditional_edges": None,
                "order_index": 2,
            },
        ],
        edges=[
            {
                "edge_id": "e-1",
                "source_node_id": "n-fetch",
                "target_node_id": "n-gen",
                "edge_type": "seq",
                "label": None,
                "condition_expr": None,
                "order_index": 0,
            },
            {
                "edge_id": "e-2",
                "source_node_id": "n-gen",
                "target_node_id": "n-verdict",
                "edge_type": "seq",
                "label": None,
                "condition_expr": None,
                "order_index": 1,
            },
        ],
    )
    return graph_id


def _make_cross_container_template(svc: FakeGraphService, project_id: str = "proj-1") -> str:
    """Seed a 2-container template with invoke + call/return edges.

    Container A (session): parse_intent (llm) → call_agent (invoke)
    Container B (agent):   analyze (llm)
    Edge: call from call_agent → analyze, return from analyze → call_agent
    """
    graph_id = "tpl-cross"
    ca_id = "c-session"
    cb_id = "c-agent"

    svc.seed_template(
        graph_id=graph_id,
        project_id=project_id,
        name="cross_container",
        containers=[
            {
                "container_id": ca_id,
                "container_key": "session_controller",
                "label": "Session Controller",
                "role_type": "agent",
                "order_index": 0,
            },
            {
                "container_id": cb_id,
                "container_key": "analysis_agent",
                "label": "Analysis Agent",
                "role_type": "agent",
                "order_index": 1,
            },
        ],
        nodes=[
            {
                "node_id": "n-parse",
                "node_key": "parse_intent",
                "label": "Parse Intent",
                "node_type": "llm",
                "role_type": "agent",
                "container_id": ca_id,
                "phase_label": "意图解析",
                "task_prompt": "解析用户意图",
                "conditional_edges": None,
                "order_index": 0,
            },
            {
                "node_id": "n-call",
                "node_key": "call_agent",
                "label": "Call Agent",
                "node_type": "invoke",
                "role_type": "agent",
                "container_id": ca_id,
                "phase_label": None,
                "task_prompt": None,
                "conditional_edges": None,
                "order_index": 1,
            },
            {
                "node_id": "n-analyze",
                "node_key": "analyze",
                "label": "Analyze",
                "node_type": "llm",
                "role_type": "agent",
                "container_id": cb_id,
                "phase_label": "分析阶段",
                "task_prompt": "执行分析任务",
                "conditional_edges": None,
                "order_index": 0,
            },
        ],
        edges=[
            {
                "edge_id": "e-seq1",
                "source_node_id": "n-parse",
                "target_node_id": "n-call",
                "edge_type": "seq",
                "label": None,
                "condition_expr": None,
                "order_index": 0,
            },
            {
                "edge_id": "e-call",
                "source_node_id": "n-call",
                "target_node_id": "n-analyze",
                "edge_type": "call",
                "label": "invoke analysis",
                "condition_expr": None,
                "order_index": 1,
            },
            {
                "edge_id": "e-return",
                "source_node_id": "n-analyze",
                "target_node_id": "n-call",
                "edge_type": "return",
                "label": "return result",
                "condition_expr": None,
                "order_index": 2,
            },
        ],
    )
    return graph_id


# =========================================================================
# Tests
# =========================================================================


class TestBasicInstantiation:
    """3-node linear template → 3 subgraphs + start/end nodes."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        self.tpl_id = _make_3node_template(self.svc)
        self.instantiator = TopologyInstantiator()

    def _instantiate(self) -> RuntimeGraphSkeleton:
        return self.instantiator.instantiate(
            template_graph_id=self.tpl_id,
            project_id="proj-1",
            graph_service=self.svc,
            created_by="test",
        )

    def test_creates_3_subgraphs(self):
        sk = self._instantiate()
        assert len(sk.subgraphs) == 3

    def test_each_subgraph_has_start_and_end_nodes(self):
        sk = self._instantiate()
        for sg in sk.subgraphs:
            nodes = [n for n in sk.nodes if n.subgraph_id == sg.subgraph_id]
            node_types = {n.node_type for n in nodes}
            assert "start" in node_types, f"Subgraph {sg.subgraph_key} missing start node"
            assert "end" in node_types, f"Subgraph {sg.subgraph_key} missing end node"

    def test_total_node_count(self):
        sk = self._instantiate()
        # 3 subgraphs × 2 nodes (start + end) = 6
        assert len(sk.nodes) == 6

    def test_all_subgraphs_pending(self):
        sk = self._instantiate()
        for sg in sk.subgraphs:
            assert sg.status == "pending"

    def test_graph_status_is_running(self):
        sk = self._instantiate()
        runtime_graph = self.svc.graphs[sk.graph_id]
        assert runtime_graph["status"] == "running"

    def test_graph_type_is_runtime(self):
        sk = self._instantiate()
        runtime_graph = self.svc.graphs[sk.graph_id]
        assert runtime_graph["graph_type"] == "agent_runtime_execution"

    def test_edges_created(self):
        sk = self._instantiate()
        # 2 seq edges in template → 2 runtime edges
        assert len(sk.edges) == 2
        for e in sk.edges:
            assert e.edge_type == "seq"

    def test_container_inherited(self):
        sk = self._instantiate()
        assert len(sk.containers) == 1
        c = sk.containers[0]
        assert c.container_key == "agent_container"
        assert c.role_type == "agent"
        assert c.source_container_id == "c-agent"

    def test_skeleton_is_frozen(self):
        sk = self._instantiate()
        with pytest.raises(AttributeError):
            sk.graph_id = "new-id"  # type: ignore[misc]


class TestFieldMapping:
    """Verify topology node fields map correctly to subgraph fields."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        self.tpl_id = _make_3node_template(self.svc)
        self.instantiator = TopologyInstantiator()

    def _instantiate(self) -> RuntimeGraphSkeleton:
        return self.instantiator.instantiate(
            template_graph_id=self.tpl_id,
            project_id="proj-1",
            graph_service=self.svc,
        )

    def test_task_prompt_maps_to_task_description(self):
        sk = self._instantiate()
        fetch_sg = next(sg for sg in sk.subgraphs if "fetch" in sg.subgraph_key)
        assert fetch_sg.task_description == "请获取所有需求的状态"

    def test_phase_label_maps_to_label(self):
        sk = self._instantiate()
        fetch_sg = next(sg for sg in sk.subgraphs if "fetch" in sg.subgraph_key)
        assert fetch_sg.label == "状态获取"

    def test_node_type_stored_in_subgraph(self):
        sk = self._instantiate()
        for sg in sk.subgraphs:
            assert sg.node_type == "llm"

    def test_node_type_in_config_json(self):
        sk = self._instantiate()
        for sg in sk.subgraphs:
            assert sg.config_json is not None
            assert sg.config_json["node_type"] == "llm"

    def test_source_node_id_preserved(self):
        sk = self._instantiate()
        source_ids = {sg.source_node_id for sg in sk.subgraphs}
        assert source_ids == {"n-fetch", "n-gen", "n-verdict"}


class TestCrossContainerInstantiation:
    """2-container template with invoke + call/return edges."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        self.tpl_id = _make_cross_container_template(self.svc)
        self.instantiator = TopologyInstantiator()

    def _instantiate(self) -> RuntimeGraphSkeleton:
        return self.instantiator.instantiate(
            template_graph_id=self.tpl_id,
            project_id="proj-1",
            graph_service=self.svc,
        )

    def test_creates_2_containers(self):
        sk = self._instantiate()
        assert len(sk.containers) == 2

    def test_creates_3_subgraphs(self):
        sk = self._instantiate()
        assert len(sk.subgraphs) == 3

    def test_invoke_subgraph_type(self):
        sk = self._instantiate()
        invoke_sg = next(sg for sg in sk.subgraphs if sg.node_type == "invoke")
        assert invoke_sg.node_type == "invoke"
        assert invoke_sg.config_json["node_type"] == "invoke"

    def test_edge_types_correct(self):
        sk = self._instantiate()
        edge_types = sorted(e.edge_type for e in sk.edges)
        assert edge_types == ["call", "return", "seq"]

    def test_edge_ids_are_runtime_node_ids(self):
        """Edge source/target should be runtime node IDs, not template IDs."""
        sk = self._instantiate()
        runtime_node_ids = {n.node_id for n in sk.nodes}
        for e in sk.edges:
            assert e.source_node_id in runtime_node_ids, (
                f"Edge {e.edge_id} source {e.source_node_id} not in runtime nodes"
            )
            assert e.target_node_id in runtime_node_ids, (
                f"Edge {e.edge_id} target {e.target_node_id} not in runtime nodes"
            )


class TestSelectiveContainerInstantiation:
    """Only the entry container plus explicitly selected containers are instantiated."""

    def test_selected_container_keys_limit_runtime_containers_and_subgraphs(self):
        svc = FakeGraphService()
        tpl_id = _make_cross_container_template(svc)
        instantiator = TopologyInstantiator()

        sk = instantiator.instantiate(
            template_graph_id=tpl_id,
            project_id="proj-1",
            graph_service=svc,
            selected_container_keys=["analysis_agent"],
        )

        assert {container.container_key for container in sk.containers} == {
            "session_controller",
            "analysis_agent",
        }
        assert {subgraph.subgraph_key for subgraph in sk.subgraphs} == {
            "sg_parse_intent",
            "sg_call_agent",
            "sg_analyze",
        }

    def test_unknown_selected_container_key_raises(self):
        svc = FakeGraphService()
        tpl_id = _make_cross_container_template(svc)
        instantiator = TopologyInstantiator()

        with pytest.raises(InstantiationError, match="container_key 不存在"):
            instantiator.instantiate(
                template_graph_id=tpl_id,
                project_id="proj-1",
                graph_service=svc,
                selected_container_keys=["missing_agent"],
            )


class TestConvenienceQueries:
    """Test RuntimeGraphSkeleton helper methods."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        self.tpl_id = _make_cross_container_template(self.svc)
        self.instantiator = TopologyInstantiator()
        self.sk = self.instantiator.instantiate(
            template_graph_id=self.tpl_id,
            project_id="proj-1",
            graph_service=self.svc,
        )

    def test_get_entry_container(self):
        entry = self.sk.get_entry_container()
        assert entry.container_key == "session_controller"
        assert entry.order_index == 0

    def test_get_subgraphs_for_container(self):
        entry = self.sk.get_entry_container()
        sgs = self.sk.get_subgraphs_for_container(entry.container_id)
        assert len(sgs) == 2  # parse_intent + call_agent
        assert sgs[0].order_index <= sgs[1].order_index

    def test_get_outgoing_edges(self):
        # The parse_intent subgraph should have 1 outgoing seq edge
        parse_sg = next(sg for sg in self.sk.subgraphs if "parse" in sg.subgraph_key)
        outgoing = self.sk.get_outgoing_edges(parse_sg.subgraph_id)
        assert len(outgoing) == 1
        assert outgoing[0].edge_type == "seq"

    def test_get_entry_container_raises_on_empty(self):
        empty_sk = RuntimeGraphSkeleton(graph_id="empty")
        with pytest.raises(ValueError, match="no containers"):
            empty_sk.get_entry_container()


class TestErrorHandling:
    """Instantiation errors for invalid or missing templates."""

    def setup_method(self) -> None:
        self.svc = FakeGraphService()
        self.instantiator = TopologyInstantiator()

    def test_missing_template_raises(self):
        with pytest.raises(InstantiationError, match="不存在"):
            self.instantiator.instantiate(
                template_graph_id="non-existent",
                project_id="proj-1",
                graph_service=self.svc,
            )

    def test_wrong_graph_type_raises(self):
        self.svc.graphs["rt-graph"] = {
            "graph_id": "rt-graph",
            "project_id": "proj-1",
            "name": "runtime",
            "graph_type": "agent_runtime_execution",
            "status": "running",
        }
        with pytest.raises(InstantiationError, match="graph_type"):
            self.instantiator.instantiate(
                template_graph_id="rt-graph",
                project_id="proj-1",
                graph_service=self.svc,
            )

    def test_no_containers_raises(self):
        self.svc.seed_template(
            graph_id="tpl-empty",
            project_id="proj-1",
            containers=[],
        )
        with pytest.raises(InstantiationError, match="container"):
            self.instantiator.instantiate(
                template_graph_id="tpl-empty",
                project_id="proj-1",
                graph_service=self.svc,
            )

    def test_no_business_nodes_raises(self):
        self.svc.seed_template(
            graph_id="tpl-nobiz",
            project_id="proj-1",
            containers=[
                {
                    "container_id": "c-1",
                    "container_key": "empty_container",
                    "label": "Empty",
                    "role_type": "agent",
                    "order_index": 0,
                },
            ],
            nodes=[
                {
                    "node_id": "n-start",
                    "node_key": "global_start",
                    "label": "Start",
                    "node_type": "start",
                    "role_type": "agent",
                    "container_id": "c-1",
                    "order_index": 0,
                },
            ],
        )
        with pytest.raises(InstantiationError, match="业务节点"):
            self.instantiator.instantiate(
                template_graph_id="tpl-nobiz",
                project_id="proj-1",
                graph_service=self.svc,
            )


class TestConditionalEdgesMapping:
    """Verify conditional_edges from topology node are stored in subgraph config."""

    def test_conditional_edges_in_config(self):
        svc = FakeGraphService()
        svc.seed_template(
            graph_id="tpl-cond",
            project_id="proj-1",
            containers=[
                {
                    "container_id": "c-1",
                    "container_key": "main",
                    "label": "Main",
                    "role_type": "agent",
                    "order_index": 0,
                },
            ],
            nodes=[
                {
                    "node_id": "n-decision",
                    "node_key": "decision_node",
                    "label": "Decision",
                    "node_type": "llm",
                    "role_type": "agent",
                    "container_id": "c-1",
                    "phase_label": "决策",
                    "task_prompt": "做出决策",
                    "conditional_edges": [
                        {"condition": "approved", "target_node_id": "n-next"},
                        {"condition": "rejected", "target_node_id": "n-alt"},
                    ],
                    "order_index": 0,
                },
            ],
        )

        instantiator = TopologyInstantiator()
        sk = instantiator.instantiate(
            template_graph_id="tpl-cond",
            project_id="proj-1",
            graph_service=svc,
        )

        sg = sk.subgraphs[0]
        assert sg.config_json is not None
        assert "conditional_edges" in sg.config_json
        assert len(sg.config_json["conditional_edges"]) == 2
        assert sg.config_json["conditional_edges"][0]["condition"] == "approved"

    def test_legacy_condition_expr_edges_are_adapted_to_conditional_edges(self):
        svc = FakeGraphService()
        svc.seed_template(
            graph_id="tpl-legacy-cond",
            project_id="proj-1",
            containers=[
                {
                    "container_id": "c-1",
                    "container_key": "main",
                    "label": "Main",
                    "role_type": "agent",
                    "order_index": 0,
                },
            ],
            nodes=[
                {
                    "node_id": "n-decision",
                    "node_key": "decision_node",
                    "label": "Decision",
                    "node_type": "llm",
                    "role_type": "agent",
                    "container_id": "c-1",
                    "phase_label": "决策",
                    "task_prompt": "做出决策",
                    "conditional_edges": None,
                    "order_index": 0,
                },
                {
                    "node_id": "n-next",
                    "node_key": "next_node",
                    "label": "Next",
                    "node_type": "llm",
                    "role_type": "agent",
                    "container_id": "c-1",
                    "phase_label": "通过",
                    "task_prompt": "继续",
                    "conditional_edges": None,
                    "order_index": 1,
                },
                {
                    "node_id": "n-alt",
                    "node_key": "alt_node",
                    "label": "Alt",
                    "node_type": "llm",
                    "role_type": "agent",
                    "container_id": "c-1",
                    "phase_label": "拒绝",
                    "task_prompt": "终止",
                    "conditional_edges": None,
                    "order_index": 2,
                },
            ],
            edges=[
                {
                    "edge_id": "e-approved",
                    "source_node_id": "n-decision",
                    "target_node_id": "n-next",
                    "edge_type": "seq",
                    "label": "approve",
                    "condition_expr": "approved",
                    "order_index": 0,
                },
                {
                    "edge_id": "e-rejected",
                    "source_node_id": "n-decision",
                    "target_node_id": "n-alt",
                    "edge_type": "seq",
                    "label": "reject",
                    "condition_expr": "rejected",
                    "order_index": 1,
                },
            ],
        )

        instantiator = TopologyInstantiator()
        sk = instantiator.instantiate(
            template_graph_id="tpl-legacy-cond",
            project_id="proj-1",
            graph_service=svc,
        )

        decision_subgraph = next(
            sg for sg in sk.subgraphs if sg.source_node_id == "n-decision"
        )
        assert decision_subgraph.config_json is not None
        assert decision_subgraph.config_json["conditional_edges"] == [
            {"condition": "approved", "target_node_id": "n-next"},
            {"condition": "rejected", "target_node_id": "n-alt"},
        ]


class TestMetaJsonPreserved:
    """Runtime graph meta_json should record source template ID."""

    def test_source_template_id_in_meta(self):
        svc = FakeGraphService()
        tpl_id = _make_3node_template(svc)
        instantiator = TopologyInstantiator()
        sk = instantiator.instantiate(
            template_graph_id=tpl_id,
            project_id="proj-1",
            graph_service=svc,
        )

        runtime_graph = svc.graphs[sk.graph_id]
        assert runtime_graph["meta_json"]["source_template_id"] == tpl_id


class TestExistingRuntimeGraphReuse:
    """Instantiation can reuse an existing runtime graph record."""

    def test_instantiate_reuses_runtime_graph_id(self):
        svc = FakeGraphService()
        tpl_id = _make_3node_template(svc)
        svc.graphs["rt-existing"] = {
            "graph_id": "rt-existing",
            "project_id": "proj-1",
            "name": "existing-runtime",
            "description": "pre-created runtime graph",
            "graph_type": "agent_runtime_execution",
            "status": "running",
            "meta_json": {"session_id": "s-1"},
        }

        instantiator = TopologyInstantiator()
        sk = instantiator.instantiate(
            template_graph_id=tpl_id,
            project_id="proj-1",
            graph_service=svc,
            runtime_graph_id="rt-existing",
        )

        assert sk.graph_id == "rt-existing"
        runtime_graph_ids = [
            graph_id
            for graph_id, graph in svc.graphs.items()
            if graph.get("graph_type") == "agent_runtime_execution"
        ]
        assert runtime_graph_ids == ["rt-existing"]
