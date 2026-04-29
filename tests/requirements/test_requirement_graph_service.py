import aiohttp
import importlib
import json
from pathlib import Path
import shutil
import uuid

import pytest

from backend_business.services.requirement_graph import helpers as graph_helpers
from backend_business.services.requirement_graph_service import (
    RequirementGraphService,
    _GraphBuilder,
    _as_list,
    _req_node_id,
)


class _FakeCursor:
    def __init__(self, db):
        self.db = db
        self.requirements = db.requirements
        self._rows = []
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):
        if "FROM manage_requirements" in query:
            self._rows = [dict(item) for item in self.requirements]
            self._row = None
            return
        if "FROM requirements_l123" in query:
            self._rows = [dict(item) for item in self.db.l123_requirements]
            self._row = None
            return
        if "FROM low_level_requirements" in query:
            self._rows = [dict(item) for item in self.db.l4_requirements]
            self._row = None
            return
        if "FROM low_level_requirement_links" in query:
            self._rows = [dict(item) for item in self.db.l4_links]
            self._row = None
            return
        if "FROM manage_projects" in query:
            if "SELECT current_session_id" in query:
                project_id = params[0]
                session_id = self.db.project_sessions.get(project_id)
                self._row = (session_id,) if session_id else None
            elif "SELECT project_id" in query:
                session_id = params[0]
                project_id = self.db.session_projects.get(session_id)
                self._row = (project_id,) if project_id else None
            else:
                self._row = None
            self._rows = []
            return
        raise AssertionError(f"Unexpected query: {query}")

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self, db):
        self.db = db

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, cursor_factory=None):
        return _FakeCursor(self.db)


class _FakeDB:
    def __init__(
        self,
        requirements=None,
        *,
        latest_trace_batch=None,
        latest_conflict_batch=None,
        latest_classification=None,
        project_sessions=None,
        session_projects=None,
        l123_requirements=None,
        l4_requirements=None,
        l4_links=None,
    ):
        self.requirements = requirements or []
        self.latest_trace_batch = latest_trace_batch
        self.latest_conflict_batch = latest_conflict_batch
        self.latest_classification = latest_classification
        self.project_sessions = project_sessions or {}
        self.session_projects = session_projects or {}
        self.l123_requirements = l123_requirements or []
        self.l4_requirements = l4_requirements or []
        self.l4_links = l4_links or []
        self.saved_relation_snapshots = []
        self.snapshot_details = {}

    def get_connection(self):
        return _FakeConnection(self)

    def get_latest_trace_batch(self, session_id):
        return self.latest_trace_batch if session_id else None

    def get_latest_conflict_batch(self, session_id):
        return self.latest_conflict_batch if session_id else None

    def get_latest_classification(self, session_id):
        return self.latest_classification if session_id else None

    def save_requirement_graph_snapshot(self, **kwargs):
        snapshot = dict(kwargs)
        snapshot["snapshot_id"] = f"snap-{len(self.saved_relation_snapshots) + 1}"
        snapshot["edge_count"] = len(snapshot.get("edges") or [])
        snapshot["created_at"] = snapshot.get("created_at") or "2026-04-20T06:00:00+00:00"
        snapshot["invalidated_at"] = snapshot.get("invalidated_at")
        snapshot["is_active"] = snapshot.get("is_active", True)
        self.saved_relation_snapshots.append(snapshot)
        self.snapshot_details[snapshot["snapshot_id"]] = {
            "snapshot_id": snapshot["snapshot_id"],
            "project_id": snapshot.get("project_id"),
            "session_id": snapshot.get("session_id"),
            "relation_mode": snapshot.get("relation_mode"),
            "created_at": snapshot["created_at"],
            "invalidated_at": snapshot["invalidated_at"],
            "is_active": snapshot["is_active"],
            "edge_count": snapshot["edge_count"],
            "edges": [
                {
                    "source_node_id": edge["source"],
                    "target_node_id": edge["target"],
                    "source_req_id": str(edge["source"]).removeprefix("req:"),
                    "target_req_id": str(edge["target"]).removeprefix("req:"),
                    "relation_type": edge["type"],
                    "source_kind": (edge.get("properties") or {}).get("source_kind"),
                    "source_detail": (edge.get("properties") or {}).get("source_detail"),
                    "weight": edge.get("weight"),
                    "confidence": (edge.get("properties") or {}).get("confidence"),
                    "reason": (edge.get("properties") or {}).get("reason"),
                    "evidence": (edge.get("properties") or {}).get("evidence") or [],
                    "model": (edge.get("properties") or {}).get("model"),
                    "review_action": (edge.get("properties") or {}).get("review_action"),
                    "review_package_id": (edge.get("properties") or {}).get("review_package_id"),
                    "properties": dict(edge.get("properties") or {}),
                    "created_at": snapshot["created_at"],
                }
                for edge in snapshot.get("edges") or []
            ],
        }
        return {
            "snapshot_id": snapshot["snapshot_id"],
            "relation_mode": snapshot.get("relation_mode"),
            "edge_count": snapshot["edge_count"],
        }

    def get_latest_requirement_graph_snapshot(self, *, project_id=None, session_id=None, relation_mode=None):
        matches = [
            snapshot for snapshot in self.snapshot_details.values()
            if (not project_id or snapshot.get("project_id") == project_id)
            and (not session_id or snapshot.get("session_id") == session_id)
            and (not relation_mode or snapshot.get("relation_mode") == relation_mode)
            and snapshot.get("is_active", False)
        ]
        if not matches:
            return None
        matches.sort(key=lambda item: (item.get("created_at") or "", item.get("snapshot_id") or ""))
        return matches[-1]

    def list_requirement_graph_snapshots(self, *, project_id=None, session_id=None, relation_mode=None, limit=20):
        matches = [
            {
                "snapshot_id": snapshot.get("snapshot_id"),
                "project_id": snapshot.get("project_id"),
                "session_id": snapshot.get("session_id"),
                "relation_mode": snapshot.get("relation_mode"),
                "created_at": snapshot.get("created_at"),
                "invalidated_at": snapshot.get("invalidated_at"),
                "is_active": snapshot.get("is_active", False),
                "edge_count": snapshot.get("edge_count", 0),
            }
            for snapshot in self.snapshot_details.values()
            if (not project_id or snapshot.get("project_id") == project_id)
            and (not session_id or snapshot.get("session_id") == session_id)
            and (not relation_mode or snapshot.get("relation_mode") == relation_mode)
        ]
        matches.sort(key=lambda item: (item.get("created_at") or "", item.get("snapshot_id") or ""), reverse=True)
        return matches[:limit]

    def get_requirement_graph_snapshot_by_id(self, snapshot_id):
        return self.snapshot_details.get(snapshot_id)


def _make_requirement(
    req_id,
    *,
    title,
    description="",
    source_level=None,
    requirement_type="business",
    tags=None,
    parent_id=None,
    source_req_id=None,
    custom_fields=None,
):
    return {
        "req_id": req_id,
        "project_id": "P-1",
        "requirement_type": requirement_type,
        "status": "open",
        "title": title,
        "description": description,
        "priority": 3,
        "assignee": "u-owner",
        "tags": tags or [],
        "parent_id": parent_id,
        "source_req_id": source_req_id,
        "source_level": source_level,
        "custom_fields": custom_fields or {},
        "created_by": "u-1",
        "updated_by": "u-1",
        "created_at": "2026-04-19T00:00:00Z",
        "updated_at": "2026-04-19T00:00:00Z",
    }


def _make_l123(req_id, *, text, level="L2"):
    return {
        "req_id": req_id,
        "session_id": "S-1",
        "level": level,
        "text": text,
        "fingerprint": f"fp-{req_id}",
        "anchor_span_id": None,
        "r": {},
        "created_at": "2026-04-19T00:00:00Z",
    }


def _make_l4(req_id, *, text, source_top_id="TOP-1", component="core"):
    return {
        "req_id": req_id,
        "session_id": "S-1",
        "source_top_id": source_top_id,
        "source_top_text": "",
        "text": text,
        "component": component,
        "acceptance_criteria": ["验收"],
        "test_method": "unit",
        "interfaces": ["api"],
        "data_contracts": [],
        "error_handling": [],
        "nfr": [],
        "open_questions": [],
        "evidence_ids": [],
        "confidence": 0.9,
        "source": "test",
        "meta": {},
        "created_at": "2026-04-19T00:00:00Z",
    }


def _make_l4_link(top_req_id, req_id):
    return {
        "top_req_id": top_req_id,
        "req_id": req_id,
        "session_id": "S-1",
        "created_at": "2026-04-19T00:00:00Z",
    }


def _add_requirement_node(builder, req):
    normalized_level = req.get("source_level") or "UNKNOWN_LEVEL"
    builder.add_node(
        _req_node_id(req["req_id"]),
        "requirement",
        req["title"],
        normalized_level,
        {
            "req_id": req["req_id"],
            "title": req["title"],
            "description": req["description"],
            "source_level": normalized_level,
            "priority": req.get("priority", 3),
            "tags": req.get("tags") or [],
            "status": "open",
        },
    )


def test_req_node_id_keeps_existing_prefix():
    assert _req_node_id("REQ-1") == "req:REQ-1"
    assert _req_node_id("req:REQ-1") == "req:REQ-1"


def test_as_list_accepts_json_arrays_and_plain_text():
    assert _as_list('["安全", "性能"]') == ["安全", "性能"]
    assert _as_list("安全") == ["安全"]
    assert _as_list(None) == []


def test_build_graph_uses_source_level_and_level_stats():
    requirements = [
        _make_requirement("R-1", title="方向需求", source_level="L1"),
        _make_requirement("R-2", title="业务需求", source_level="L2"),
        _make_requirement("R-3", title="方案需求", source_level="L3"),
        _make_requirement("R-4", title="实现需求", source_level="L4"),
        _make_requirement("R-5", title="未知需求", source_level=None),
    ]

    graph = RequirementGraphService(_FakeDB(requirements), ai_client=None).build_graph(
        project_id="P-1",
        session_id="S-1",
        infer_relations=False,
    )

    nodes = {node["id"]: node for node in graph["nodes"]}
    assert nodes["req:R-1"]["properties"]["source_level"] == "L1"
    assert nodes["req:R-4"]["properties"]["source_level"] == "L4"
    assert nodes["req:R-5"]["properties"]["source_level"] == "UNKNOWN_LEVEL"
    assert graph["stats"]["level_counts"]["L1"] == 1
    assert graph["stats"]["level_counts"]["L4"] == 1
    assert graph["stats"]["level_counts"]["UNKNOWN_LEVEL"] == 1


def test_source_level_missing_with_low_level_type_falls_back_to_l4():
    requirements = [
        _make_requirement(
            "R-1",
            title="底层实现",
            source_level=None,
            requirement_type="low_level",
        )
    ]

    graph = RequirementGraphService(_FakeDB(requirements), ai_client=None).build_graph(
        project_id="P-1",
        session_id="S-1",
        infer_relations=False,
    )

    node = graph["nodes"][0]
    assert node["properties"]["source_level"] == "L4"
    assert graph["stats"]["level_counts"]["L4"] == 1


def test_parent_id_and_source_req_id_emit_refines_edges():
    requirements = [
        _make_requirement("ROOT", title="根需求", source_level="L1"),
        _make_requirement("MID", title="中层需求", source_level="L2", parent_id="ROOT"),
        _make_requirement("LEAF", title="叶子需求", source_level="L3", source_req_id="MID"),
    ]

    graph = RequirementGraphService(_FakeDB(requirements), ai_client=None).build_graph(
        project_id="P-1",
        session_id="S-1",
        infer_relations=False,
    )

    edge_keys = {(edge["source"], edge["target"], edge["type"]) for edge in graph["edges"]}
    assert ("req:ROOT", "req:MID", "REFINES") in edge_keys
    assert ("req:MID", "req:LEAF", "REFINES") in edge_keys


def test_build_graph_uses_existing_analysis_results_as_authoritative_sources():
    requirements = [
        _make_requirement("ROOT", title="根需求", description="统一身份认证", source_level="L1"),
        _make_requirement("MID", title="登录流程", description="系统需要登录流程", source_level="L2", parent_id="ROOT"),
        _make_requirement("LEAF", title="登录校验", description="登录时校验凭证", source_level="L3", source_req_id="SRC-LEAF"),
        _make_requirement("OTHER", title="游客访问", description="允许游客访问部分页面", source_level="L3"),
        _make_requirement("LOW-A", title="登录接口校验", description="登录接口校验凭证", source_level="L4"),
        _make_requirement("LOW-B", title="登录错误提示", description="登录失败返回错误提示", source_level="L4"),
    ]
    db = _FakeDB(
        requirements,
        latest_trace_batch={
            "record_id": 101,
            "data": {
                "relations": [
                    {
                        "high_req_id": "ROOT",
                        "low_req_id": "MID",
                        "relation_type": "refine",
                        "confidence": 0.91,
                    },
                    {
                        "source_id": "SRC-LEAF",
                        "target_id": "ROOT",
                        "relation_type": "depends_on",
                        "confidence": 0.86,
                    },
                ]
            },
        },
        latest_conflict_batch={
            "batch_id": "conf-batch-1",
            "items": [
                {
                    "requirement_a": "登录流程",
                    "requirement_b": "游客访问",
                    "is_conflict": True,
                    "result_json": {"reason": "认证与匿名访问冲突"},
                }
            ],
        },
        latest_classification={
            "id": 55,
            "requirements": ["登录流程", "登录校验", "游客访问", "登录接口校验", "登录错误提示"],
            "predictions": [
                {"label": "安全", "requirement": "登录流程"},
                {"label": "安全", "requirement": "登录校验"},
                {"label": "体验", "requirement": "游客访问"},
                {"label": "实现", "requirement": "登录接口校验"},
                {"label": "实现", "requirement": "登录错误提示"},
            ],
            "label_distribution": {"安全": 2, "体验": 1, "实现": 2},
            "total": 5,
        },
    )

    graph = RequirementGraphService(db, ai_client=None).build_graph(
        project_id="P-1",
        session_id="S-1",
        infer_relations=False,
    )

    nodes = {node["id"]: node for node in graph["nodes"]}
    edges = {(edge["source"], edge["target"], edge["type"]): edge for edge in graph["edges"]}

    assert nodes["req:MID"]["properties"]["category"] == "安全"
    assert nodes["req:LEAF"]["properties"]["category"] == "安全"
    assert graph["stats"]["classification_label_distribution"] == {"安全": 2, "体验": 1, "实现": 2}
    assert graph["stats"]["analysis_edge_count"] >= 3
    assert graph["stats"]["supplemental_edge_count"] == 0

    assert ("req:ROOT", "req:MID", "REFINES") in edges
    assert "trace_analysis" in edges[("req:ROOT", "req:MID", "REFINES")]["properties"]["source_kinds"]
    assert ("req:LEAF", "req:ROOT", "DEPENDS_ON") in edges
    assert edges[("req:LEAF", "req:ROOT", "DEPENDS_ON")]["properties"]["source_kind"] == "trace_analysis"
    assert ("req:MID", "req:OTHER", "CONFLICTS_WITH") in edges or ("req:OTHER", "req:MID", "CONFLICTS_WITH") in edges
    assert edges.get(("req:LEAF", "req:MID", "SIMILAR_TO")) is None
    assert edges.get(("req:MID", "req:LEAF", "SIMILAR_TO")) is None
    similar_edge = edges.get(("req:LOW-A", "req:LOW-B", "SIMILAR_TO")) or edges.get(("req:LOW-B", "req:LOW-A", "SIMILAR_TO"))
    assert similar_edge is not None
    assert similar_edge["properties"]["source_kind"] == "classification_analysis"


def test_build_graph_infer_false_skips_authoritative_rule_duplication():
    requirements = [
        _make_requirement(
            "A",
            title="支付编排",
            description="订单服务依赖支付模块接口返回结果后再继续处理",
            source_level="L3",
            tags=["order", "payment"],
            custom_fields={"module": "order"},
        ),
        _make_requirement(
            "B",
            title="支付模块",
            description="提供支付模块接口",
            source_level="L4",
            tags=["payment"],
            custom_fields={"module": "payment"},
        ),
    ]

    graph = RequirementGraphService(_FakeDB(requirements), ai_client=None).build_graph(
        project_id="P-1",
        session_id="S-1",
        infer_relations=False,
    )

    edge_keys = {(edge["source"], edge["target"], edge["type"]) for edge in graph["edges"]}
    assert ("req:A", "req:B", "DEPENDS_ON") not in edge_keys
    assert graph["stats"]["supplemental_edge_count"] == 0


def test_build_graph_infer_true_only_adds_extra_relations():
    class FakeAI:
        async def chat_completion_with_tools_async(self, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_relation_mutations",
                            "arguments": {
                                "mutations": [
                                    {
                                        "candidate_id": "pair:req:A|req:B",
                                        "action": "add",
                                        "target_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "IMPACTS",
                                        },
                                        "replacement_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "IMPACTS",
                                        },
                                        "confidence": 0.83,
                                        "reason": "认证策略会影响游客访问路径",
                                        "evidence": ["shared_term:访问"],
                                    }
                                ]
                            },
                        },
                    }
                ]
            }

    requirements = [
        _make_requirement(
            "A",
            title="认证策略",
            description="认证策略影响游客访问流程，并要求回归校验",
            source_level="L3",
            tags=["访问", "认证"],
            custom_fields={"validation_rules": ["回归校验"]},
        ),
        _make_requirement(
            "B",
            title="游客访问",
            description="游客访问部分页面时需要被策略约束",
            source_level="L3",
            tags=["访问"],
        ),
    ]

    graph = RequirementGraphService(_FakeDB(requirements), ai_client=FakeAI()).build_graph(
        project_id="P-1",
        session_id="S-1",
        infer_relations=True,
        inference_limit=12,
    )

    edge_keys = {(edge["source"], edge["target"], edge["type"]): edge for edge in graph["edges"]}
    assert ("req:A", "req:B", "IMPACTS") in edge_keys
    assert edge_keys[("req:A", "req:B", "IMPACTS")]["properties"]["source_kind"] == "llm"
    assert graph["stats"]["supplemental_edge_count"] >= 1
    assert ("req:A", "req:B", "DEPENDS_ON") not in edge_keys
    assert ("req:A", "req:B", "CONFLICTS_WITH") not in edge_keys


def test_dependency_rule_produces_depends_on():
    service = RequirementGraphService(_FakeDB(), ai_client=None)
    builder = _GraphBuilder(limit=10)
    source = _make_requirement(
        "A",
        title="支付编排",
        description="订单服务依赖支付模块接口返回结果后再继续处理",
        source_level="L3",
        tags=["order", "payment"],
        custom_fields={"module": "order"},
    )
    target = _make_requirement(
        "B",
        title="支付模块",
        description="提供支付模块接口",
        source_level="L4",
        tags=["payment"],
        custom_fields={"module": "payment"},
    )
    for req in (source, target):
        _add_requirement_node(builder, req)

    features = {
        _req_node_id(source["req_id"]): service._build_requirement_feature(source, "L3"),
        _req_node_id(target["req_id"]): service._build_requirement_feature(target, "L4"),
    }
    candidate_pairs, _ = service._collect_candidate_pairs(features)
    stats = service._apply_rule_edges(builder, features, candidate_pairs)

    assert stats["edge_counts"]["DEPENDS_ON"] >= 1
    assert ("req:A", "req:B", "DEPENDS_ON") in builder.edges


def test_dependency_tool_audit_can_reject_dense_false_positive():
    class FakeAI:
        async def chat_completion_with_tools_async(self, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_dependency_decisions",
                            "arguments": {
                                "decisions": [
                                    {
                                        "candidate_id": "dep:A->B",
                                        "action": "reject",
                                        "confidence": 0.91,
                                        "reason": "两者只是同一主题下的并列功能，没有明确前置依赖",
                                        "evidence": ["same_topic_only"],
                                        "dependency_kind": "other",
                                    }
                                ]
                            },
                        },
                    }
                ]
            }

    service = RequirementGraphService(_FakeDB(), ai_client=FakeAI())
    builder = _GraphBuilder(limit=10)
    source = _make_requirement(
        "A",
        title="任务面板",
        description="任务面板模块应展示任务统计与摘要",
        source_level="L4",
        tags=["task", "dashboard"],
        custom_fields={"module": "task_panel"},
    )
    target = _make_requirement(
        "B",
        title="任务列表",
        description="任务列表模块应支持任务查询与筛选",
        source_level="L4",
        tags=["task", "dashboard"],
        custom_fields={"module": "task_list"},
    )
    for req in (source, target):
        _add_requirement_node(builder, req)

    features = {
        _req_node_id(source["req_id"]): service._build_requirement_feature(source, "L4"),
        _req_node_id(target["req_id"]): service._build_requirement_feature(target, "L4"),
    }
    candidate_pairs = [{
        "source": "req:A",
        "target": "req:B",
        "score": 12,
        "signals": ["shared_tag:task", "shared_term:任务"],
    }]
    stats = service._apply_rule_edges(builder, features, candidate_pairs)

    assert stats["dependency_audit"]["reviewed_count"] == 0 or stats["edge_counts"].get("DEPENDS_ON", 0) == 0
    assert ("req:A", "req:B", "DEPENDS_ON") not in builder.edges


def test_dependency_tool_audit_can_reverse_direction():
    class FakeAI:
        async def chat_completion_with_tools_async(self, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_dependency_decisions",
                            "arguments": {
                                "decisions": [
                                    {
                                        "candidate_id": "dep:A->B",
                                        "action": "reverse",
                                        "confidence": 0.88,
                                        "reason": "配置加载器先提供配置数据，热加载校验器依赖它工作",
                                        "evidence": ["配置数据先被加载", "校验器消费配置内容"],
                                        "dependency_kind": "data",
                                    }
                                ]
                            },
                        },
                    }
                ]
            }

    service = RequirementGraphService(_FakeDB(), ai_client=FakeAI())
    builder = _GraphBuilder(limit=10)
    source = _make_requirement(
        "A",
        title="热加载校验器",
        description="热加载校验器依赖 loader 模块提供的 /configs 配置内容完成校验",
        source_level="L4",
        tags=["config"],
        custom_fields={"module": "validator"},
    )
    target = _make_requirement(
        "B",
        title="配置加载器",
        description="配置加载器提供 loader 模块能力，并暴露 /configs 接口输出配置内容",
        source_level="L4",
        tags=["config"],
        custom_fields={"module": "loader"},
    )
    for req in (source, target):
        _add_requirement_node(builder, req)

    features = {
        _req_node_id(source["req_id"]): service._build_requirement_feature(source, "L4"),
        _req_node_id(target["req_id"]): service._build_requirement_feature(target, "L4"),
    }
    candidate_pairs = [{
        "source": "req:A",
        "target": "req:B",
        "score": 14,
        "signals": ["mentioned_module:loader", "shared_interface:config"],
    }]
    stats = service._apply_rule_edges(builder, features, candidate_pairs)

    assert stats["edge_counts"]["DEPENDS_ON"] >= 1
    assert ("req:B", "req:A", "DEPENDS_ON") in builder.edges
    assert ("req:A", "req:B", "DEPENDS_ON") not in builder.edges


def test_dependency_tool_audit_falls_back_on_service_unavailable():
    class FakeAI:
        async def chat_completion_with_tools_async(self, **kwargs):
            raise aiohttp.ClientResponseError(
                request_info=None,
                history=(),
                status=503,
                message="Service Unavailable",
                headers=None,
            )

    service = RequirementGraphService(_FakeDB(), ai_client=FakeAI())
    builder = _GraphBuilder(limit=10)
    source = _make_requirement(
        "A",
        title="订单编排",
        description="订单编排模块依赖 payment-gateway 接口返回支付结果后才能继续创建履约任务",
        source_level="L4",
        tags=["order", "payment"],
        custom_fields={"module": "order-orchestrator"},
    )
    target = _make_requirement(
        "B",
        title="支付网关",
        description="payment-gateway 模块提供支付结果查询接口并返回支付状态",
        source_level="L4",
        tags=["payment"],
        custom_fields={"module": "payment-gateway"},
    )
    for req in (source, target):
        _add_requirement_node(builder, req)

    features = {
        _req_node_id(source["req_id"]): service._build_requirement_feature(source, "L4"),
        _req_node_id(target["req_id"]): service._build_requirement_feature(target, "L4"),
    }
    candidate_pairs = [{
        "source": "req:A",
        "target": "req:B",
        "score": 15,
        "signals": ["mentioned_module:payment-gateway", "shared_interface:payment-status"],
    }]
    stats = service._apply_rule_edges(builder, features, candidate_pairs)

    assert stats["dependency_audit"]["fallback_used"] is True
    assert stats["edge_counts"]["DEPENDS_ON"] >= 1
    assert ("req:A", "req:B", "DEPENDS_ON") in builder.edges


def test_dependency_audit_uses_json_when_tool_calls_are_not_supported():
    class FakeAI:
        def __init__(self):
            self.json_calls = 0

        def supports_tool_calls(self, model=None):
            return False

        def chat_completion(self, **kwargs):
            self.json_calls += 1
            return {
                "content": json.dumps(
                    {
                        "decisions": [
                            {
                                "candidate_id": "dep:A->B",
                                "action": "confirm",
                                "confidence": 0.89,
                                "reason": "订单编排明确消费支付网关返回的支付状态。",
                                "evidence": ["shared_interface:payment-status"],
                                "dependency_kind": "data",
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }

    fake_ai = FakeAI()
    service = RequirementGraphService(_FakeDB(), ai_client=fake_ai)
    builder = _GraphBuilder(limit=10)
    stats = service._apply_dependency_candidates(
        builder,
        [
            {
                "candidate_id": "dep:A->B",
                "source": "req:A",
                "target": "req:B",
                "score": 15,
                "rule_confidence": 0.89,
                "detail": "rule_dependency_signal_match",
                "reason": "订单编排消费支付网关返回的支付状态",
                "evidence": ["shared_interface:payment-status"],
                "signals": ["mentioned_module:payment-gateway", "shared_interface:payment-status"],
                "source_requirement": {"id": "req:A", "title": "订单编排"},
                "target_requirement": {"id": "req:B", "title": "支付网关"},
            }
        ],
        model="local-json-model",
        review_limit=12,
    )

    assert fake_ai.json_calls == 1
    assert stats["fallback_used"] is False
    assert ("req:A", "req:B", "DEPENDS_ON") in builder.edges


def test_conflict_rule_produces_conflicts_with():
    service = RequirementGraphService(_FakeDB(), ai_client=None)
    builder = _GraphBuilder(limit=10)
    left = _make_requirement(
        "A",
        title="安全审计",
        description="必须开启加密审计并进行复杂校验",
        source_level="L3",
        custom_fields={"module": "gateway"},
    )
    right = _make_requirement(
        "B",
        title="开放访问",
        description="要求明文开放访问以减少接入成本，和审计目标冲突",
        source_level="L3",
        custom_fields={"module": "gateway"},
    )
    for req in (left, right):
        _add_requirement_node(builder, req)

    features = {
        _req_node_id(left["req_id"]): service._build_requirement_feature(left, "L3"),
        _req_node_id(right["req_id"]): service._build_requirement_feature(right, "L3"),
    }
    candidate_pairs, _ = service._collect_candidate_pairs(features)
    stats = service._apply_rule_edges(builder, features, candidate_pairs)

    assert stats["edge_counts"]["CONFLICTS_WITH"] >= 1
    assert ("req:A", "req:B", "CONFLICTS_WITH") in builder.edges or ("req:B", "req:A", "CONFLICTS_WITH") in builder.edges


def test_validation_rule_produces_validates_with():
    service = RequirementGraphService(_FakeDB(), ai_client=None)
    builder = _GraphBuilder(limit=10)
    left = _make_requirement(
        "A",
        title="审计日志验证",
        description="验收标准要求回放审计日志并验证签名",
        source_level="L4",
        custom_fields={"acceptance_criteria": ["回放审计日志", "验证签名"]},
    )
    right = _make_requirement(
        "B",
        title="审计结果校验",
        description="测试需要回放审计日志并验证签名完整性",
        source_level="L4",
        custom_fields={"test_method": "回放审计日志并验证签名"},
    )
    for req in (left, right):
        _add_requirement_node(builder, req)

    features = {
        _req_node_id(left["req_id"]): service._build_requirement_feature(left, "L4"),
        _req_node_id(right["req_id"]): service._build_requirement_feature(right, "L4"),
    }
    candidate_pairs, _ = service._collect_candidate_pairs(features)
    stats = service._apply_rule_edges(builder, features, candidate_pairs)

    assert stats["edge_counts"]["VALIDATES_WITH"] >= 1
    assert ("req:A", "req:B", "VALIDATES_WITH") in builder.edges or ("req:B", "req:A", "VALIDATES_WITH") in builder.edges


def test_similar_to_rejects_modal_template_overlap_even_if_sentences_look_close():
    service = RequirementGraphService(_FakeDB(), ai_client=None)
    builder = _GraphBuilder(limit=10)
    left = _make_requirement(
        "A",
        title="Shell 会话超时控制",
        description="The system shall timeout inactive shell sessions after 15 minutes.",
        source_level="L4",
        tags=["security"],
    )
    right = _make_requirement(
        "B",
        title="Shell 历史命令导出",
        description="The system shall export shell command history to audit storage.",
        source_level="L4",
        tags=["security"],
    )
    for req in (left, right):
        _add_requirement_node(builder, req)

    features = {
        _req_node_id(left["req_id"]): service._build_requirement_feature(left, "L4"),
        _req_node_id(right["req_id"]): service._build_requirement_feature(right, "L4"),
    }
    features["req:A"]["embedding"] = [0.9, 0.1, 0.1]
    features["req:B"]["embedding"] = [0.9, 0.1, 0.1]
    candidate_pairs, _ = service._collect_candidate_pairs(features)
    stats = service._apply_rule_edges(builder, features, candidate_pairs)

    assert stats["edge_counts"].get("SIMILAR_TO", 0) == 0
    assert ("req:A", "req:B", "SIMILAR_TO") not in builder.edges
    assert ("req:B", "req:A", "SIMILAR_TO") not in builder.edges


def test_similar_to_accepts_semantic_match_with_module_anchor():
    service = RequirementGraphService(_FakeDB(), ai_client=None)
    builder = _GraphBuilder(limit=10)
    left = _make_requirement(
        "A",
        title="权限审批流配置",
        description="权限中心支持审批节点、审批人路由和审批记录查询。",
        source_level="L4",
        tags=["permission", "approval"],
        custom_fields={"module": "permission-workflow"},
    )
    right = _make_requirement(
        "B",
        title="权限审批策略编排",
        description="权限工作流提供审批节点编排、审批路由和审批轨迹检索。",
        source_level="L4",
        tags=["permission", "workflow"],
        custom_fields={"module": "permission-workflow"},
    )
    for req in (left, right):
        _add_requirement_node(builder, req)

    features = {
        _req_node_id(left["req_id"]): service._build_requirement_feature(left, "L4"),
        _req_node_id(right["req_id"]): service._build_requirement_feature(right, "L4"),
    }
    features["req:A"]["embedding"] = [0.8, 0.6, 0.0]
    features["req:B"]["embedding"] = [0.79, 0.61, 0.0]
    candidate_pairs, _ = service._collect_candidate_pairs(features)
    stats = service._apply_rule_edges(builder, features, candidate_pairs)

    assert stats["edge_counts"]["SIMILAR_TO"] >= 1
    assert ("req:A", "req:B", "SIMILAR_TO") in builder.edges or ("req:B", "req:A", "SIMILAR_TO") in builder.edges


def test_similar_to_does_not_override_stronger_relation():
    service = RequirementGraphService(_FakeDB(), ai_client=None)
    builder = _GraphBuilder(limit=10)
    left = _make_requirement(
        "A",
        title="订单服务",
        description="订单服务依赖支付模块接口",
        source_level="L3",
        tags=["payment", "order"],
        custom_fields={"module": "order"},
    )
    right = _make_requirement(
        "B",
        title="支付服务",
        description="支付模块接口负责支付执行",
        source_level="L4",
        tags=["payment"],
        custom_fields={"module": "payment"},
    )
    for req in (left, right):
        _add_requirement_node(builder, req)

    features = {
        _req_node_id(left["req_id"]): service._build_requirement_feature(left, "L3"),
        _req_node_id(right["req_id"]): service._build_requirement_feature(right, "L4"),
    }
    candidate_pairs, _ = service._collect_candidate_pairs(features)
    service._apply_rule_edges(builder, features, candidate_pairs)
    service._prune_weaker_similar_edges(builder)

    assert ("req:A", "req:B", "DEPENDS_ON") in builder.edges
    assert ("req:A", "req:B", "SIMILAR_TO") not in builder.edges
    assert ("req:B", "req:A", "SIMILAR_TO") not in builder.edges


def test_candidate_recall_limits_pair_scale():
    service = RequirementGraphService(_FakeDB(), ai_client=None)
    features = {}
    for index in range(14):
        req = _make_requirement(
            f"R-{index}",
            title=f"支付需求{index}",
            description=f"支付模块需求 {index}",
            source_level="L4",
            tags=["payment", f"batch-{index % 2}"],
            custom_fields={"module": "payment"},
        )
        features[_req_node_id(req["req_id"])] = service._build_requirement_feature(req, "L4")

    pairs, stats = service._collect_candidate_pairs(features, per_requirement_limit=5)

    assert max(stats["per_requirement_counts"].values()) <= 5
    assert len(pairs) < 91


def test_build_graph_local_relation_mode_surfaces_local_vector_edges(monkeypatch):
    requirements = [
        _make_requirement(
            "A",
            title="订单侧支付编排",
            description="订单服务需要调用 payment 接口完成扣款",
            source_level="L3",
            custom_fields={"module": "payment"},
        ),
        _make_requirement(
            "B",
            title="支付核心服务",
            description="支付服务提供扣款与退款能力",
            source_level="L4",
            custom_fields={"module": "payment"},
        ),
    ]
    service = RequirementGraphService(_FakeDB(requirements), ai_client=None)

    monkeypatch.setattr(
        service,
        "_collect_candidate_pairs",
        lambda _features: (
            [
                {
                    "source": "req:A",
                    "target": "req:B",
                    "score": 12,
                    "signals": ["semantic_match:0.913", "shared_module:payment"],
                }
            ],
            {
                "pair_count": 1,
                "per_requirement_limit": 10,
                "per_requirement_counts": {"req:A": 1, "req:B": 1},
                "requirement_count": 2,
                "max_term_document_frequency": 1,
            },
        ),
    )

    graph = service.build_graph(
        project_id="P-1",
        session_id="S-1",
        relation_mode="local",
        inference_limit=24,
    )

    local_edges = [
        edge for edge in graph["edges"] if (edge.get("properties") or {}).get("source_kind") == "local_vector"
    ]
    assert local_edges
    local_edge = local_edges[0]
    assert local_edge["properties"]["source_kind"] == "local_vector"
    assert str(local_edge["properties"]["source_detail"]).startswith("local_vector.")
    assert local_edge["properties"]["model"]
    assert graph["stats"]["local_vector"]["enabled"] is True
    assert graph["stats"]["local_vector"]["added_count"] >= 1
    assert graph["stats"]["supplemental_edge_count"] >= 1
    assert graph["meta"]["relation_mode"] == "local"


def test_build_graph_local_relation_mode_persists_requirement_relation_snapshot(monkeypatch):
    requirements = [
        _make_requirement(
            "A",
            title="订单侧支付编排",
            description="订单服务需要调用 payment 接口完成扣款",
            source_level="L3",
            custom_fields={"module": "payment"},
        ),
        _make_requirement(
            "B",
            title="支付核心服务",
            description="支付服务提供扣款与退款能力",
            source_level="L4",
            custom_fields={"module": "payment"},
        ),
    ]
    db = _FakeDB(requirements)
    service = RequirementGraphService(db, ai_client=None)

    monkeypatch.setattr(
        service,
        "_collect_candidate_pairs",
        lambda _features: (
            [
                {
                    "source": "req:A",
                    "target": "req:B",
                    "score": 12,
                    "signals": ["semantic_match:0.913", "shared_module:payment"],
                }
            ],
            {
                "pair_count": 1,
                "per_requirement_limit": 10,
                "per_requirement_counts": {"req:A": 1, "req:B": 1},
                "requirement_count": 2,
                "max_term_document_frequency": 1,
            },
        ),
    )

    graph = service.build_graph(
        project_id="P-1",
        session_id="S-1",
        relation_mode="local",
        inference_limit=24,
    )

    assert db.saved_relation_snapshots
    saved_snapshot = db.saved_relation_snapshots[0]
    assert saved_snapshot["project_id"] == "P-1"
    assert saved_snapshot["session_id"] == "S-1"
    assert saved_snapshot["relation_mode"] == "local"
    assert any(
        (edge.get("properties") or {}).get("source_kind") == "local_vector"
        for edge in saved_snapshot["edges"]
    )
    assert graph["meta"]["relation_snapshot"]["snapshot_id"] == "snap-1"


def test_get_snapshot_graph_rehydrates_saved_requirement_edges():
    requirements = [
        _make_requirement("A", title="订单侧支付编排", source_level="L3"),
        _make_requirement("B", title="支付核心服务", source_level="L4"),
    ]
    db = _FakeDB(requirements)
    db.snapshot_details["snap-history-1"] = {
        "snapshot_id": "snap-history-1",
        "project_id": "P-1",
        "session_id": "S-1",
        "relation_mode": "llm",
        "created_at": "2026-04-20T06:00:00+00:00",
        "invalidated_at": "2026-04-20T06:05:00+00:00",
        "is_active": False,
        "edge_count": 1,
        "edges": [
            {
                "source_node_id": "req:A",
                "target_node_id": "req:B",
                "source_req_id": "A",
                "target_req_id": "B",
                "relation_type": "DEPENDS_ON",
                "source_kind": "llm",
                "source_detail": "llm_tool_review",
                "weight": 0.91,
                "confidence": 0.91,
                "reason": "reviewed",
                "evidence": ["shared_module:payment"],
                "model": "deepseek-v4-pro",
                "review_action": "add",
                "review_package_id": "pkg-1",
                "properties": {
                    "source_kind": "llm",
                    "source_detail": "llm_tool_review",
                    "confidence": 0.91,
                    "reason": "reviewed",
                    "evidence": ["shared_module:payment"],
                    "model": "deepseek-v4-pro",
                    "review_action": "add",
                    "review_package_id": "pkg-1",
                },
                "created_at": "2026-04-20T06:00:00+00:00",
            }
        ],
    }
    service = RequirementGraphService(db, ai_client=None)

    graph = service.get_snapshot_graph("snap-history-1", limit=900)

    edge = graph["edges"][0]
    assert edge["source"] == "req:A"
    assert edge["target"] == "req:B"
    assert edge["type"] == "DEPENDS_ON"
    assert edge["properties"]["source_kind"] == "llm"
    assert graph["stats"]["supplemental_edge_count"] == 1
    assert graph["meta"]["loaded_from_snapshot"] is True
    assert graph["meta"]["relation_snapshot"]["snapshot_id"] == "snap-history-1"
    assert graph["meta"]["relation_snapshot"]["is_active"] is False


def test_list_snapshot_history_returns_filtered_snapshots_in_desc_order():
    requirements = [_make_requirement("A", title="订单侧支付编排", source_level="L3")]
    db = _FakeDB(requirements)
    db.snapshot_details["snap-1"] = {
        "snapshot_id": "snap-1",
        "project_id": "P-1",
        "session_id": "S-1",
        "relation_mode": "local",
        "created_at": "2026-04-20T06:00:00+00:00",
        "invalidated_at": "2026-04-20T06:10:00+00:00",
        "is_active": False,
        "edge_count": 2,
        "edges": [],
    }
    db.snapshot_details["snap-2"] = {
        "snapshot_id": "snap-2",
        "project_id": "P-1",
        "session_id": "S-1",
        "relation_mode": "llm",
        "created_at": "2026-04-20T06:12:00+00:00",
        "invalidated_at": None,
        "is_active": True,
        "edge_count": 3,
        "edges": [],
    }
    service = RequirementGraphService(db, ai_client=None)

    history = service.list_snapshot_history(project_id="P-1", session_id="S-1", limit=10)

    assert [item["snapshot_id"] for item in history] == ["snap-2", "snap-1"]
    assert history[0]["relation_mode"] == "llm"
    assert history[0]["is_active"] is True
    assert history[1]["invalidated_at"] == "2026-04-20T06:10:00+00:00"


def test_build_graph_local_relation_mode_generates_semantic_relation_candidates(monkeypatch):
    requirements = [
        _make_requirement(
            "A",
            title="支付能力扩展编排",
            description="订单流程需要调用支付模块接口，并扩展退款校验。变更时会联动支付能力。",
            source_level="L3",
            custom_fields={"module": "支付模块"},
        ),
        _make_requirement(
            "B",
            title="支付核心服务",
            description="支付模块接口负责扣款、退款与退款校验能力。",
            source_level="L4",
            custom_fields={"module": "支付模块"},
        ),
    ]
    service = RequirementGraphService(_FakeDB(requirements), ai_client=None)

    monkeypatch.setattr(
        service,
        "_collect_candidate_pairs",
        lambda _features: (
            [
                {
                    "source": "req:A",
                    "target": "req:B",
                    "score": 14,
                    "signals": [
                        "semantic_match:0.884",
                        "shared_module:支付模块",
                        "shared_validation:退款校验",
                    ],
                }
            ],
            {
                "pair_count": 1,
                "per_requirement_limit": 10,
                "per_requirement_counts": {"req:A": 1, "req:B": 1},
                "requirement_count": 2,
                "max_term_document_frequency": 1,
            },
        ),
    )

    graph = service.build_graph(
        project_id="P-1",
        session_id="S-1",
        relation_mode="local",
        inference_limit=24,
    )

    edge_keys = {(edge["source"], edge["target"], edge["type"]): edge for edge in graph["edges"]}
    assert ("req:A", "req:B", "DEPENDS_ON") in edge_keys
    assert edge_keys[("req:A", "req:B", "DEPENDS_ON")]["properties"]["source_kind"] == "local_vector"
    assert ("req:A", "req:B", "EXTENDS") in edge_keys
    assert ("req:A", "req:B", "IMPACTS") in edge_keys
    assert graph["stats"]["local_vector"]["edge_counts"]["DEPENDS_ON"] >= 1
    assert graph["stats"]["local_vector"]["edge_counts"]["EXTENDS"] >= 1
    assert graph["stats"]["local_vector"]["reviewed_pair_count"] == 1


def test_build_graph_llm_relation_mode_reviews_local_vector_edges(monkeypatch):
    class FakeAI:
        def __init__(self):
            self.seen_existing_relations = []

        async def chat_completion_with_tools_async(self, **kwargs):
            payload = kwargs["messages"][-1]["content"]
            json_payload = json.loads(payload[payload.index("{") :])
            candidate = json_payload["candidates"][0]
            self.seen_existing_relations.append(candidate["existing_relations"])
            return {"tool_calls": []}

    requirements = [
        _make_requirement(
            "A",
            title="支付能力扩展编排",
            description="订单流程需要调用支付模块接口，并扩展退款校验。变更时会联动支付能力。",
            source_level="L3",
            custom_fields={"module": "支付模块"},
        ),
        _make_requirement(
            "B",
            title="支付核心服务",
            description="支付模块接口负责扣款、退款与退款校验能力。",
            source_level="L4",
            custom_fields={"module": "支付模块"},
        ),
    ]
    fake_ai = FakeAI()
    service = RequirementGraphService(_FakeDB(requirements), ai_client=fake_ai)

    monkeypatch.setattr(
        service,
        "_collect_candidate_pairs",
        lambda _features: (
            [
                {
                    "source": "req:A",
                    "target": "req:B",
                    "score": 14,
                    "signals": [
                        "semantic_match:0.884",
                        "shared_module:支付模块",
                        "shared_validation:退款校验",
                    ],
                }
            ],
            {
                "pair_count": 1,
                "per_requirement_limit": 10,
                "per_requirement_counts": {"req:A": 1, "req:B": 1},
                "requirement_count": 2,
                "max_term_document_frequency": 1,
            },
        ),
    )

    graph = service.build_graph(
        project_id="P-1",
        session_id="S-1",
        relation_mode="llm",
        inference_limit=24,
    )

    assert fake_ai.seen_existing_relations
    existing_relations = fake_ai.seen_existing_relations[0]
    assert any(
        relation["type"] == "DEPENDS_ON" and relation["source_kind"] == "local_vector"
        for relation in existing_relations
    )
    assert graph["stats"]["local_vector"]["added_count"] >= 1
    assert graph["stats"]["relation_review"]["reviewed_pair_count"] == 1
    assert graph["meta"]["relation_mode"] == "llm"


def test_build_graph_llm_relation_mode_persists_reviewed_requirement_relation_snapshot():
    class FakeAI:
        async def chat_completion_with_tools_async(self, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_relation_mutations",
                            "arguments": {
                                "mutations": [
                                    {
                                        "candidate_id": "pair:req:A|req:B",
                                        "action": "update",
                                        "target_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "DEPENDS_ON",
                                        },
                                        "replacement_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "IMPACTS",
                                        },
                                        "confidence": 0.93,
                                        "reason": "支付能力变更会联动订单侧能力",
                                        "evidence": ["shared_module:payment"],
                                    }
                                ]
                            },
                        },
                    }
                ]
            }

    requirements = [
        _make_requirement(
            "A",
            title="订单侧支付编排",
            description="订单服务需要调用 payment 接口完成扣款，支付能力调整会影响订单流程",
            source_level="L3",
            custom_fields={"module": "payment"},
        ),
        _make_requirement(
            "B",
            title="支付核心服务",
            description="支付服务提供扣款与退款能力",
            source_level="L4",
            custom_fields={"module": "payment"},
        ),
    ]
    review_edges = [
        {
            "source": "req:A",
            "target": "req:B",
            "type": "DEPENDS_ON",
            "weight": 0.81,
            "properties": {
                "source_kind": "local_vector",
                "source_detail": "local_vector.semantic_dependency",
                "confidence": 0.81,
                "reason": "candidate",
                "evidence": ["shared_module:payment"],
                "model": "local-model",
            },
        }
    ]
    db = _FakeDB(requirements)
    service = RequirementGraphService(db, ai_client=FakeAI())

    graph = service.build_graph(
        project_id="P-1",
        session_id="S-1",
        relation_mode="llm",
        inference_limit=24,
        review_edges=review_edges,
    )

    assert db.saved_relation_snapshots
    saved_snapshot = db.saved_relation_snapshots[0]
    assert saved_snapshot["relation_mode"] == "llm"
    assert any(
        edge["type"] == "IMPACTS" and (edge.get("properties") or {}).get("source_kind") == "llm"
        for edge in saved_snapshot["edges"]
    )
    assert graph["meta"]["relation_snapshot"]["edge_count"] == len(saved_snapshot["edges"])


def test_build_graph_llm_relation_mode_prefers_supplied_local_review_edges(monkeypatch):
    class FakeAI:
        def __init__(self):
            self.packages = []

        async def chat_completion_with_tools_async(self, **kwargs):
            payload = kwargs["messages"][-1]["content"]
            json_payload = json.loads(payload[payload.index("{") :])
            self.packages.append(json_payload)
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_relation_mutations",
                            "arguments": {
                                "mutations": [
                                    {
                                        "candidate_id": "pair:req:A|req:B",
                                        "action": "update",
                                        "target_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "DEPENDS_ON",
                                        },
                                        "replacement_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "IMPACTS",
                                        },
                                        "confidence": 0.91,
                                        "reason": "reviewed",
                                        "evidence": ["shared_module:支付模块"],
                                    }
                                ]
                            },
                        },
                    }
                ]
            }

    requirements = [
        _make_requirement(
            "A",
            title="支付能力扩展编排",
            description="订单流程需要调用支付模块接口。",
            source_level="L3",
            custom_fields={"module": "支付模块"},
        ),
        _make_requirement(
            "B",
            title="支付核心服务",
            description="支付模块接口负责扣款与退款能力。",
            source_level="L4",
            custom_fields={"module": "支付模块"},
        ),
    ]
    fake_ai = FakeAI()
    service = RequirementGraphService(_FakeDB(requirements), ai_client=fake_ai)

    def _unexpected_collect(_features):
        raise AssertionError("should not recollect candidate pairs when review_edges are supplied")

    monkeypatch.setattr(service, "_collect_candidate_pairs", _unexpected_collect)

    graph = service.build_graph(
        project_id="P-1",
        session_id="S-1",
        relation_mode="llm",
        inference_limit=24,
        review_edges=[
            {
                "source": "req:A",
                "target": "req:B",
                "type": "DEPENDS_ON",
                "weight": 0.81,
                "properties": {
                    "source_kind": "local_vector",
                    "source_detail": "local_vector.semantic_dependency",
                    "confidence": 0.81,
                    "reason": "candidate",
                    "evidence": ["shared_module:支付模块"],
                    "model": "local-model",
                },
            }
        ],
    )

    assert fake_ai.packages
    candidate = fake_ai.packages[0]["candidates"][0]
    assert candidate["existing_relations"] == [
        {
            "source": "req:A",
            "target": "req:B",
            "type": "DEPENDS_ON",
            "source_kind": "local_vector",
            "source_detail": "local_vector.semantic_dependency",
        }
    ]
    edge_keys = {(edge["source"], edge["target"], edge["type"]): edge for edge in graph["edges"]}
    assert ("req:A", "req:B", "DEPENDS_ON") not in edge_keys
    assert edge_keys[("req:A", "req:B", "IMPACTS")]["properties"]["source_kind"] == "llm"
    assert graph["stats"]["review_seed_edge_count"] == 1
    assert graph["stats"]["local_vector"]["seeded_from_frontend"] is True
    assert graph["stats"]["relation_review"]["updated_count"] == 1
    assert graph["stats"]["relation_review"]["reviewed_pair_count"] == 1


def test_resolve_semantic_embedding_source_downloads_into_data_model_directory(monkeypatch):
    model_dir = Path.cwd() / "data" / "model" / f"test_requirement_graph_embedding_download_{uuid.uuid4().hex}"
    shutil.rmtree(model_dir, ignore_errors=True)
    monkeypatch.setattr(graph_helpers, "_REQUIREMENT_GRAPH_EMBEDDING_DIR", model_dir)
    monkeypatch.setattr(
        graph_helpers,
        "_SEMANTIC_EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )

    captured = {}

    def fake_snapshot_download(*, repo_id, local_dir, **kwargs):
        captured["repo_id"] = repo_id
        captured["local_dir"] = local_dir
        local_path = Path(local_dir)
        local_path.mkdir(parents=True, exist_ok=True)
        (local_path / "modules.json").write_text("{}", encoding="utf-8")
        return str(local_path)

    huggingface_hub = importlib.import_module("huggingface_hub")
    monkeypatch.setattr(huggingface_hub, "snapshot_download", fake_snapshot_download)

    resolved = graph_helpers._resolve_semantic_embedding_source()

    assert captured["repo_id"] == "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    assert Path(captured["local_dir"]) == model_dir
    assert Path(resolved) == model_dir

    shutil.rmtree(model_dir, ignore_errors=True)


def test_resolve_semantic_embedding_source_prefers_existing_data_model_directory(monkeypatch):
    model_dir = Path.cwd() / "data" / "model" / f"test_requirement_graph_embedding_existing_{uuid.uuid4().hex}"
    shutil.rmtree(model_dir, ignore_errors=True)
    model_dir.mkdir(parents=True, exist_ok=True)
    (model_dir / "modules.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(graph_helpers, "_REQUIREMENT_GRAPH_EMBEDDING_DIR", model_dir)
    monkeypatch.setattr(
        graph_helpers,
        "_SEMANTIC_EMBEDDING_MODEL",
        "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
    )

    resolved = graph_helpers._resolve_semantic_embedding_source()

    assert Path(resolved) == model_dir

    shutil.rmtree(model_dir, ignore_errors=True)


def test_relation_review_add_action_applies_llm_review_edge():
    class FakeAI:
        async def chat_completion_with_tools_async(self, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_relation_mutations",
                            "arguments": {
                                "mutations": [
                                    {
                                        "candidate_id": "pair:req:A|req:B",
                                        "action": "add",
                                        "target_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "DEPENDS_ON",
                                        },
                                        "replacement_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "DEPENDS_ON",
                                        },
                                        "confidence": 0.84,
                                        "reason": "订单服务调用支付模块",
                                        "evidence": ["shared_module:payment", "shared_interface:/payments"],
                                    }
                                ]
                            },
                        },
                    }
                ]
            }

    service = RequirementGraphService(_FakeDB(), ai_client=FakeAI())
    builder = _GraphBuilder(limit=10)
    left = _make_requirement("A", title="订单服务", description="订单服务依赖支付模块接口", source_level="L3", custom_fields={"module": "order"})
    right = _make_requirement("B", title="支付服务", description="支付模块提供 /payments 接口", source_level="L4", custom_fields={"module": "payment"})
    for req, level in ((left, "L3"), (right, "L4")):
        _add_requirement_node(builder, req)
    features = {
        "req:A": service._build_requirement_feature(left, "L3"),
        "req:B": service._build_requirement_feature(right, "L4"),
    }
    candidate_pairs = [{"source": "req:A", "target": "req:B", "score": 10, "signals": ["shared_module:payment"]}]

    stats = service._apply_llm_relation_review(
        builder,
        project_id="P-1",
        session_id="S-1",
        enabled=True,
        model="fake-model",
        inference_limit=12,
        requirement_features=features,
        candidate_pairs=candidate_pairs,
    )

    edge = builder.edges[("req:A", "req:B", "DEPENDS_ON")]
    assert stats["added_count"] == 1
    assert stats["package_count"] == 1
    assert stats["reviewed_pair_count"] == 1
    assert edge["properties"]["source_kind"] == "llm"
    assert edge["properties"]["source_detail"] == "llm_tool_review"
    assert edge["properties"]["review_action"] == "add"
    assert edge["properties"]["review_package_id"] == "pkg-1"
    assert edge["properties"]["reason"] == "订单服务调用支付模块"
    assert edge["properties"]["evidence"] == ["shared_module:payment", "shared_interface:/payments"]


def test_relation_review_update_action_replaces_edge_direction():
    class FakeAI:
        async def chat_completion_with_tools_async(self, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_relation_mutations",
                            "arguments": {
                                "mutations": [
                                    {
                                        "candidate_id": "pair:req:A|req:B",
                                        "action": "update",
                                        "target_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "DEPENDS_ON",
                                        },
                                        "replacement_edge": {
                                            "source": "req:B",
                                            "target": "req:A",
                                            "type": "DEPENDS_ON",
                                        },
                                        "confidence": 0.88,
                                        "reason": "真实方向是配置加载器先提供输入，校验器依赖它",
                                        "evidence": ["配置加载器输出配置内容", "校验器消费配置内容"],
                                    }
                                ]
                            },
                        },
                    }
                ]
            }

    service = RequirementGraphService(_FakeDB(), ai_client=FakeAI())
    builder = _GraphBuilder(limit=10)
    left = _make_requirement("A", title="热加载校验器", description="校验器检查配置内容并在热加载时执行校验", source_level="L4", custom_fields={"module": "validator"})
    right = _make_requirement("B", title="配置加载器", description="配置加载器输出配置内容并提供 /configs 接口", source_level="L4", custom_fields={"module": "loader"})
    for req, level in ((left, "L3"), (right, "L4")):
        _add_requirement_node(builder, req)
    features = {
        "req:A": service._build_requirement_feature(left, "L3"),
        "req:B": service._build_requirement_feature(right, "L4"),
    }
    builder.add_edge(
        "req:A",
        "req:B",
        "DEPENDS_ON",
        label="依赖",
        weight=0.78,
        properties={
            "source_kind": "rule",
            "source_detail": "rule_dependency_signal_match",
            "reason": "规则误判方向",
            "evidence": ["mentioned_module:loader"],
        },
    )
    candidate_pairs = [{"source": "req:A", "target": "req:B", "score": 12, "signals": ["mentioned_module:loader"]}]

    stats = service._apply_llm_relation_review(
        builder,
        project_id="P-1",
        session_id="S-1",
        enabled=True,
        model="fake-model",
        inference_limit=12,
        requirement_features=features,
        candidate_pairs=candidate_pairs,
    )

    assert stats["updated_count"] == 1
    assert ("req:A", "req:B", "DEPENDS_ON") not in builder.edges
    edge = builder.edges[("req:B", "req:A", "DEPENDS_ON")]
    assert edge["properties"]["source_kind"] == "llm"
    assert edge["properties"]["review_action"] == "update"
    assert edge["properties"]["review_package_id"] == "pkg-1"


def test_relation_review_delete_action_removes_non_structural_edge():
    class FakeAI:
        async def chat_completion_with_tools_async(self, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_relation_mutations",
                            "arguments": {
                                "mutations": [
                                    {
                                        "candidate_id": "pair:req:A|req:B",
                                        "action": "delete",
                                        "target_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "CONFLICTS_WITH",
                                        },
                                        "confidence": 0.91,
                                        "reason": "两者只是同主题，不构成真实冲突",
                                        "evidence": ["same_topic_only"],
                                    }
                                ]
                            },
                        },
                    }
                ]
            }

    service = RequirementGraphService(_FakeDB(), ai_client=FakeAI())
    builder = _GraphBuilder(limit=10)
    left = _make_requirement("A", title="任务面板", description="展示任务摘要", source_level="L4")
    right = _make_requirement("B", title="任务列表", description="支持任务查询", source_level="L4")
    for req, level in ((left, "L4"), (right, "L4")):
        _add_requirement_node(builder, req)
    builder.add_edge(
        "req:A",
        "req:B",
        "CONFLICTS_WITH",
        label="冲突",
        weight=0.76,
        properties={
            "source_kind": "rule",
            "source_detail": "rule_conflict_signal_match",
            "reason": "规则误判冲突",
            "evidence": ["explicit_conflict_marker"],
        },
    )
    features = {
        "req:A": service._build_requirement_feature(left, "L4"),
        "req:B": service._build_requirement_feature(right, "L4"),
    }
    candidate_pairs = [{"source": "req:A", "target": "req:B", "score": 11, "signals": ["shared_term:任务"]}]

    stats = service._apply_llm_relation_review(
        builder,
        project_id="P-1",
        session_id="S-1",
        enabled=True,
        model="fake-model",
        inference_limit=12,
        requirement_features=features,
        candidate_pairs=candidate_pairs,
    )

    assert stats["deleted_count"] == 1
    assert ("req:A", "req:B", "CONFLICTS_WITH") not in builder.edges


def test_relation_review_ignores_out_of_scope_and_invalid_mutations():
    class FakeAI:
        async def chat_completion_with_tools_async(self, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_relation_mutations",
                            "arguments": {
                                "mutations": [
                                    {
                                        "candidate_id": "pair:req:OUT|req:SIDE",
                                        "action": "add",
                                        "target_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "DEPENDS_ON",
                                        },
                                        "replacement_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "DEPENDS_ON",
                                        },
                                        "confidence": 0.9,
                                        "reason": "越界 candidate",
                                        "evidence": ["invalid"],
                                    },
                                    {
                                        "candidate_id": "pair:req:A|req:B",
                                        "action": "add",
                                        "target_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "DEPENDS_ON",
                                        },
                                        "replacement_edge": {
                                            "source": "req:A",
                                            "target": "req:C",
                                            "type": "DEPENDS_ON",
                                        },
                                        "confidence": 0.9,
                                        "reason": "跨 pair 引用",
                                        "evidence": ["invalid"],
                                    },
                                    {
                                        "candidate_id": "pair:req:A|req:B",
                                        "action": "add",
                                        "target_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "DEPENDS_ON",
                                        },
                                        "replacement_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "SIMILAR_TO",
                                        },
                                        "confidence": 0.9,
                                        "reason": "非法类型",
                                        "evidence": ["invalid"],
                                    },
                                ]
                            },
                        },
                    }
                ]
            }

    service = RequirementGraphService(_FakeDB(), ai_client=FakeAI())
    builder = _GraphBuilder(limit=10)
    requirements = [
        _make_requirement("A", title="A", description="A", source_level="L4"),
        _make_requirement("B", title="B", description="B", source_level="L4"),
        _make_requirement("C", title="C", description="C", source_level="L4"),
    ]
    for req in requirements:
        _add_requirement_node(builder, req)
    features = {
        _req_node_id(req["req_id"]): service._build_requirement_feature(req, "L4")
        for req in requirements
    }
    candidate_pairs = [{"source": "req:A", "target": "req:B", "score": 9, "signals": ["shared_term:a"]}]

    stats = service._apply_llm_relation_review(
        builder,
        project_id="P-1",
        session_id="S-1",
        enabled=True,
        model="fake-model",
        inference_limit=12,
        requirement_features=features,
        candidate_pairs=candidate_pairs,
    )

    assert stats["added_count"] == 0
    assert stats["updated_count"] == 0
    assert stats["deleted_count"] == 0
    assert builder.edges == {}


def test_relation_review_does_not_delete_structural_refines_edge():
    class FakeAI:
        async def chat_completion_with_tools_async(self, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_relation_mutations",
                            "arguments": {
                                "mutations": [
                                    {
                                        "candidate_id": "pair:req:A|req:B",
                                        "action": "delete",
                                        "target_edge": {
                                            "source": "req:A",
                                            "target": "req:B",
                                            "type": "REFINES",
                                        },
                                        "confidence": 0.95,
                                        "reason": "不应保留",
                                        "evidence": ["invalid_delete"],
                                    }
                                ]
                            },
                        },
                    }
                ]
            }

    service = RequirementGraphService(_FakeDB(), ai_client=FakeAI())
    builder = _GraphBuilder(limit=10)
    left = _make_requirement("A", title="父需求", description="父", source_level="L1")
    right = _make_requirement("B", title="子需求", description="子", source_level="L2")
    for req, level in ((left, "L1"), (right, "L2")):
        _add_requirement_node(builder, req)
    builder.add_edge(
        "req:A",
        "req:B",
        "REFINES",
        label="细化",
        weight=1.0,
        properties={
            "source_kind": "structural",
            "source_detail": "manage_requirements.parent_id",
            "reason": "结构边",
        },
    )
    features = {
        "req:A": service._build_requirement_feature(left, "L1"),
        "req:B": service._build_requirement_feature(right, "L2"),
    }
    candidate_pairs = [{"source": "req:A", "target": "req:B", "score": 8, "signals": ["structural"]}]

    stats = service._apply_llm_relation_review(
        builder,
        project_id="P-1",
        session_id="S-1",
        enabled=True,
        model="fake-model",
        inference_limit=12,
        requirement_features=features,
        candidate_pairs=candidate_pairs,
    )

    assert stats["deleted_count"] == 0
    assert ("req:A", "req:B", "REFINES") in builder.edges


def test_relation_review_splits_48_pairs_into_eight_fixed_size_packages():
    class FakeAI:
        def __init__(self):
            self.package_sizes = []

        async def chat_completion_with_tools_async(self, **kwargs):
            payload = kwargs["messages"][-1]["content"]
            self.package_sizes.append(payload.count('"candidate_id"'))
            return {"tool_calls": []}

    fake_ai = FakeAI()
    service = RequirementGraphService(_FakeDB(), ai_client=fake_ai)
    builder = _GraphBuilder(limit=200)
    features = {}
    for index in range(49):
        req = _make_requirement(
            f"R-{index}",
            title=f"需求{index}",
            description=f"描述{index}",
            source_level="L4",
        )
        node_id = _req_node_id(req["req_id"])
        _add_requirement_node(builder, req)
        features[node_id] = service._build_requirement_feature(req, "L4")
    candidate_pairs = [
        {
            "source": _req_node_id(f"R-{index}"),
            "target": _req_node_id(f"R-{index + 1}"),
            "score": 10 + index,
            "signals": [f"signal:{index}"],
        }
        for index in range(48)
    ]

    stats = service._apply_llm_relation_review(
        builder,
        project_id="P-1",
        session_id="S-1",
        enabled=True,
        model="fake-model",
        inference_limit=48,
        requirement_features=features,
        candidate_pairs=candidate_pairs,
    )

    assert stats["package_count"] == 8
    assert stats["reviewed_pair_count"] == 48
    assert stats["requested_concurrency"] == 3
    assert stats["applied_concurrency"] == 3
    assert fake_ai.package_sizes == [6, 6, 6, 6, 6, 6, 6, 6]


def test_relation_review_uses_fixed_package_size_independent_of_concurrency():
    class FakeAI:
        def __init__(self):
            self.package_sizes = []

        async def chat_completion_with_tools_async(self, **kwargs):
            payload = kwargs["messages"][-1]["content"]
            self.package_sizes.append(payload.count('"candidate_id"'))
            return {"tool_calls": []}

    fake_ai = FakeAI()
    service = RequirementGraphService(_FakeDB(), ai_client=fake_ai)
    builder = _GraphBuilder(limit=200)
    features = {}
    for index in range(17):
        req = _make_requirement(
            f"Q-{index}",
            title=f"需求{index}",
            description=f"描述{index}",
            source_level="L4",
        )
        node_id = _req_node_id(req["req_id"])
        _add_requirement_node(builder, req)
        features[node_id] = service._build_requirement_feature(req, "L4")
    candidate_pairs = [
        {
            "source": _req_node_id(f"Q-{index}"),
            "target": _req_node_id(f"Q-{index + 1}"),
            "score": 10 + index,
            "signals": [f"signal:{index}"],
        }
        for index in range(16)
    ]

    stats = service._apply_llm_relation_review(
        builder,
        project_id="P-1",
        session_id="S-1",
        enabled=True,
        model="fake-model",
        inference_limit=16,
        review_concurrency=4,
        requirement_features=features,
        candidate_pairs=candidate_pairs,
    )

    assert stats["package_count"] == 3
    assert stats["requested_concurrency"] == 4
    assert stats["applied_concurrency"] == 3
    assert stats["reviewed_pair_count"] == 16
    assert fake_ai.package_sizes == [6, 6, 4]


def test_relation_review_falls_back_per_failed_package_and_keeps_other_results():
    class FakeAI:
        def __init__(self):
            self.tool_calls = 0
            self.json_calls = 0

        async def chat_completion_with_tools_async(self, **kwargs):
            self.tool_calls += 1
            if self.tool_calls == 1:
                raise aiohttp.ClientResponseError(
                    request_info=None,
                    history=(),
                    status=503,
                    message="Service Unavailable",
                    headers=None,
                )
            payload = kwargs["messages"][-1]["content"]
            candidate_id = json.loads(payload.split("\n", 1)[1])["candidates"][0]["candidate_id"]
            _, pair_payload = candidate_id.split(":", 1)
            _, target = pair_payload.split("|", 1)
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_relation_mutations",
                            "arguments": {
                                "mutations": [
                                    {
                                        "candidate_id": candidate_id,
                                        "action": "add",
                                        "target_edge": {
                                            "source": "req:A",
                                            "target": target,
                                            "type": "DEPENDS_ON",
                                        },
                                        "replacement_edge": {
                                            "source": "req:A",
                                            "target": target,
                                            "type": "DEPENDS_ON",
                                        },
                                        "confidence": 0.81,
                                        "reason": f"A depends on {target}",
                                        "evidence": [f"tool:{target}"],
                                    }
                                ]
                            },
                        },
                    }
                ]
            }

        def chat_completion(self, **kwargs):
            self.json_calls += 1
            return {"content": '{"edges":[]}'}

    fake_ai = FakeAI()
    service = RequirementGraphService(_FakeDB(), ai_client=fake_ai)
    builder = _GraphBuilder(limit=20)
    requirements = [
        _make_requirement("A", title="A", description="A", source_level="L4"),
        _make_requirement("B", title="B", description="B", source_level="L4"),
        _make_requirement("C", title="C", description="C", source_level="L4"),
        _make_requirement("D", title="D", description="D", source_level="L4"),
        _make_requirement("E", title="E", description="E", source_level="L4"),
        _make_requirement("F", title="F", description="F", source_level="L4"),
        _make_requirement("G", title="G", description="G", source_level="L4"),
        _make_requirement("H", title="H", description="H", source_level="L4"),
    ]
    features = {}
    for req in requirements:
        node_id = _req_node_id(req["req_id"])
        _add_requirement_node(builder, req)
        features[node_id] = service._build_requirement_feature(req, "L4")
    candidate_pairs = [
        {"source": "req:A", "target": f"req:{target}", "score": 12 - index, "signals": [f"s{index}"]}
        for index, target in enumerate(["B", "C", "D", "E", "F", "G", "H"], start=1)
    ]

    stats = service._apply_llm_relation_review(
        builder,
        project_id="P-1",
        session_id="S-1",
        enabled=True,
        model="fake-model",
        inference_limit=7,
        requirement_features=features,
        candidate_pairs=candidate_pairs,
    )

    assert stats["package_count"] == 2
    assert stats["fallback_used"] is True
    assert fake_ai.json_calls == 1
    assert ("req:A", "req:H", "DEPENDS_ON") in builder.edges


def test_relation_review_uses_json_when_tool_calls_are_not_supported():
    class FakeAI:
        def __init__(self):
            self.json_calls = 0

        def supports_tool_calls(self, model=None):
            return False

        def chat_completion(self, **kwargs):
            self.json_calls += 1
            return {
                "content": json.dumps(
                    {
                        "mutations": [
                            {
                                "candidate_id": "pair:req:A|req:B",
                                "action": "update",
                                "target_edge": {
                                    "source": "req:A",
                                    "target": "req:B",
                                    "type": "DEPENDS_ON",
                                },
                                "replacement_edge": {
                                    "source": "req:B",
                                    "target": "req:A",
                                    "type": "DEPENDS_ON",
                                },
                                "confidence": 0.84,
                                "reason": "真正依赖方向是配置加载器向校验器提供输入。",
                                "evidence": ["shared_interface:configs"],
                            }
                        ]
                    },
                    ensure_ascii=False,
                )
            }

    fake_ai = FakeAI()
    service = RequirementGraphService(_FakeDB(), ai_client=fake_ai)
    builder = _GraphBuilder(limit=10)
    left = _make_requirement("A", title="热加载校验器", description="校验器消费配置内容执行校验", source_level="L4", custom_fields={"module": "validator"})
    right = _make_requirement("B", title="配置加载器", description="加载器输出配置内容并暴露 /configs 接口", source_level="L4", custom_fields={"module": "loader"})
    for req in (left, right):
        _add_requirement_node(builder, req)
    builder.add_edge(
        "req:A",
        "req:B",
        "DEPENDS_ON",
        label="依赖",
        weight=0.78,
        properties={
            "source_kind": "rule",
            "source_detail": "rule_dependency_signal_match",
            "reason": "规则误判方向",
            "evidence": ["mentioned_module:loader"],
        },
    )
    features = {
        "req:A": service._build_requirement_feature(left, "L4"),
        "req:B": service._build_requirement_feature(right, "L4"),
    }
    candidate_pairs = [{"source": "req:A", "target": "req:B", "score": 12, "signals": ["mentioned_module:loader"]}]

    stats = service._apply_llm_relation_review(
        builder,
        project_id="P-1",
        session_id="S-1",
        enabled=True,
        model="local-json-model",
        inference_limit=12,
        requirement_features=features,
        candidate_pairs=candidate_pairs,
    )

    assert fake_ai.json_calls == 1
    assert stats["fallback_used"] is False
    assert stats["updated_count"] == 1
    assert ("req:A", "req:B", "DEPENDS_ON") not in builder.edges
    assert ("req:B", "req:A", "DEPENDS_ON") in builder.edges


async def test_stream_graph_events_emit_candidates_decisions_and_final_snapshot():
    class FakeAI:
        async def chat_completion_with_tools_async(self, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_relation_mutations",
                            "arguments": {"mutations": []},
                        },
                    }
                ]
            }

    requirements = [
        _make_requirement(
            "A",
            title="支付流程",
            description="支付流程依赖订单模块接口返回状态后继续处理",
            source_level="L4",
            tags=["payment", "order", "订单模块"],
            custom_fields={"module": "payment"},
        ),
        _make_requirement(
            "B",
            title="订单支付",
            description="订单模块提供订单模块接口和支付状态",
            source_level="L4",
            tags=["payment", "order", "订单模块"],
            custom_fields={"module": "order"},
        ),
    ]
    db = _FakeDB(requirements)
    service = RequirementGraphService(db, ai_client=FakeAI())

    events = []
    async for event, payload in service.stream_graph_events(
        project_id="P-1",
        session_id="S-1",
        limit=900,
        inference_limit=48,
        package_size=6,
        review_concurrency=3,
        model="deepseek-v4-pro",
    ):
        events.append((event, payload))

    event_names = [event for event, _payload in events]
    assert event_names.index("base_graph") < event_names.index("candidate_edges")
    assert "relation_decision" in event_names
    assert event_names[-1] == "done"

    candidate_payload = next(payload for event, payload in events if event == "candidate_edges")
    assert candidate_payload["edges"]
    decision_payloads = [payload for event, payload in events if event == "relation_decision"]
    assert any(payload["action"] == "reject" for payload in decision_payloads)

    snapshot_statuses = [item.get("snapshot_status") for item in db.saved_relation_snapshots]
    assert "running" in snapshot_statuses
    assert snapshot_statuses[-1] == "final"
    final_snapshot = db.saved_relation_snapshots[-1]
    assert all(
        (edge.get("properties") or {}).get("review_action") != "reject"
        for edge in final_snapshot.get("edges") or []
    )


async def test_discover_relation_stream_groups_by_top_requirement_and_saves_final_snapshot():
    class FakeAI:
        def __init__(self):
            self.packages = []

        def supports_tool_calls(self, model=None):
            return True

        async def chat_completion_with_tools_async(self, **kwargs):
            prompt = kwargs["messages"][-1]["content"]
            payload = json.loads(prompt.split("输入包：\n", 1)[1])
            self.packages.append(payload)
            low_ids = [item["id"] for item in payload["l4_requirements"]]
            relations = []
            if len(low_ids) >= 2:
                relations.append(
                    {
                        "source": low_ids[0],
                        "target": low_ids[1],
                        "type": "DEPENDS_ON",
                        "confidence": 0.86,
                        "reason": "第一个底层需求依赖第二个底层需求提供的接口",
                        "evidence": ["接口依赖"],
                    }
                )
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_discovered_requirement_relations",
                            "arguments": {"relations": relations},
                        },
                    }
                ]
            }

    db = _FakeDB(
        [],
        l123_requirements=[
            _make_l123("TOP-1", text="支付能力", level="L2"),
            _make_l123("TOP-2", text="审计能力", level="L3"),
        ],
        l4_requirements=[
            _make_l4("LOW-1", text="调用订单接口"),
            _make_l4("LOW-2", text="订单接口返回支付状态"),
            _make_l4("LOW-3", text="记录审计日志", source_top_id="TOP-2"),
        ],
        l4_links=[
            _make_l4_link("TOP-1", "LOW-1"),
            _make_l4_link("TOP-1", "LOW-2"),
            _make_l4_link("TOP-2", "LOW-3"),
        ],
    )
    fake_ai = FakeAI()
    service = RequirementGraphService(db, ai_client=fake_ai)
    service._apply_local_vector_edges = lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("local vectors used"))

    events = []
    async for event, payload in service.stream_discover_relation_events(
        project_id="P-1",
        session_id="S-1",
        limit=900,
        review_concurrency=2,
        model="deepseek-v4-pro",
    ):
        events.append((event, payload))

    event_names = [event for event, _payload in events]
    assert event_names[0] == "base_graph"
    assert event_names.index("base_graph") < event_names.index("relation_decision")
    assert event_names[-1] == "done"
    assert len(fake_ai.packages) == 2
    assert {package["top_requirement"]["id"] for package in fake_ai.packages} == {"req:TOP-1", "req:TOP-2"}

    base_graph = events[0][1]["graph"]
    base_edge_keys = {(edge["source"], edge["target"], edge["type"]) for edge in base_graph["edges"]}
    assert ("req:TOP-1", "req:LOW-1", "REFINES") in base_edge_keys

    decisions = [payload for event, payload in events if event == "relation_decision"]
    assert decisions
    assert all(payload["action"] == "add" for payload in decisions)
    assert decisions[0]["edge"]["properties"]["source_detail"] == "llm_discovery_tool"

    final_snapshot = db.saved_relation_snapshots[-1]
    assert final_snapshot["snapshot_status"] == "final"
    assert final_snapshot["relation_mode"] == "llm"
    saved_edges = final_snapshot["edges"]
    assert any(edge["type"] == "REFINES" for edge in saved_edges)
    assert any((edge.get("properties") or {}).get("source_kind") == "llm" for edge in saved_edges)
    assert not any((edge.get("properties") or {}).get("source_kind") == "local_vector" for edge in saved_edges)


async def test_discover_relation_stream_filters_invalid_tool_relations():
    class FakeAI:
        def supports_tool_calls(self, model=None):
            return True

        async def chat_completion_with_tools_async(self, **kwargs):
            return {
                "tool_calls": [
                    {
                        "type": "function",
                        "function": {
                            "name": "submit_discovered_requirement_relations",
                            "arguments": {
                                "relations": [
                                    {
                                        "source": "req:TOP-1",
                                        "target": "req:LOW-1",
                                        "type": "REFINES",
                                        "confidence": 0.9,
                                        "reason": "禁止结构边",
                                        "evidence": ["bad"],
                                    },
                                    {
                                        "source": "req:LOW-1",
                                        "target": "req:OUTSIDE",
                                        "type": "DEPENDS_ON",
                                        "confidence": 0.9,
                                        "reason": "包外节点",
                                        "evidence": ["bad"],
                                    },
                                    {
                                        "source": "req:LOW-1",
                                        "target": "req:LOW-1",
                                        "type": "DEPENDS_ON",
                                        "confidence": 0.9,
                                        "reason": "自环",
                                        "evidence": ["bad"],
                                    },
                                    {
                                        "source": "req:LOW-1",
                                        "target": "req:LOW-2",
                                        "type": "BLOCKS",
                                        "confidence": 0.9,
                                        "reason": "非法类型",
                                        "evidence": ["bad"],
                                    },
                                ]
                            },
                        },
                    }
                ]
            }

    db = _FakeDB(
        [],
        l123_requirements=[_make_l123("TOP-1", text="支付能力", level="L2")],
        l4_requirements=[
            _make_l4("LOW-1", text="调用订单接口"),
            _make_l4("LOW-2", text="订单接口返回支付状态"),
        ],
        l4_links=[
            _make_l4_link("TOP-1", "LOW-1"),
            _make_l4_link("TOP-1", "LOW-2"),
        ],
    )
    service = RequirementGraphService(db, ai_client=FakeAI())

    events = []
    async for event, payload in service.stream_discover_relation_events(
        project_id="P-1",
        session_id="S-1",
    ):
        events.append((event, payload))

    assert [payload for event, payload in events if event == "relation_decision"] == []
    final_snapshot = db.saved_relation_snapshots[-1]
    assert all(
        (edge.get("properties") or {}).get("source_kind") != "llm"
        for edge in final_snapshot.get("edges") or []
    )


async def test_discover_relation_stream_skips_oversized_top_package():
    class FakeAI:
        def supports_tool_calls(self, model=None):
            return True

        async def chat_completion_with_tools_async(self, **kwargs):
            raise AssertionError("oversized packages should not call DeepSeek")

    lows = [_make_l4(f"LOW-{index}", text=f"需求 {index}") for index in range(81)]
    links = [_make_l4_link("TOP-1", low["req_id"]) for low in lows]
    db = _FakeDB(
        [],
        l123_requirements=[_make_l123("TOP-1", text="支付能力", level="L2")],
        l4_requirements=lows,
        l4_links=links,
    )
    service = RequirementGraphService(db, ai_client=FakeAI())

    events = []
    async for event, payload in service.stream_discover_relation_events(
        project_id="P-1",
        session_id="S-1",
    ):
        events.append((event, payload))

    skipped = [payload for event, payload in events if event == "package_skipped"]
    assert skipped
    assert skipped[0]["reason"] == "too_many_l4"
    assert events[-1][0] == "done"
    assert db.saved_relation_snapshots[-1]["snapshot_status"] == "final"
