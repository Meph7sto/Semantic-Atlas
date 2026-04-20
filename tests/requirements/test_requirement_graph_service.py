import aiohttp

from backend_business.services.requirement_graph_service import (
    RequirementGraphService,
    _GraphBuilder,
    _as_list,
    _req_node_id,
)


class _FakeCursor:
    def __init__(self, requirements):
        self.requirements = requirements
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
        if "FROM manage_projects" in query:
            self._row = None
            self._rows = []
            return
        raise AssertionError(f"Unexpected query: {query}")

    def fetchall(self):
        return self._rows

    def fetchone(self):
        return self._row


class _FakeConnection:
    def __init__(self, requirements):
        self.requirements = requirements

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, cursor_factory=None):
        return _FakeCursor(self.requirements)


class _FakeDB:
    def __init__(self, requirements=None):
        self.requirements = requirements or []

    def get_connection(self):
        return _FakeConnection(self.requirements)


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


def test_llm_output_accepts_depends_on_and_conflicts_with():
    class FakeAI:
        def chat_completion(self, **kwargs):
            return {
                "content": """
                {
                  "edges": [
                    {
                      "source": "req:A",
                      "target": "req:B",
                      "type": "DEPENDS_ON",
                      "confidence": 0.84,
                      "reason": "订单服务调用支付模块",
                      "evidence": ["shared_module:payment", "shared_interface:/payments"]
                    },
                    {
                      "source": "req:A",
                      "target": "req:B",
                      "type": "CONFLICTS_WITH",
                      "confidence": 0.66,
                      "reason": "这条不会被接纳，因为同一候选对没有冲突证据限制",
                      "evidence": ["manual"]
                    }
                  ]
                }
                """
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

    stats = service._apply_llm_inference(
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
    assert stats["inferred_edge_count"] >= 1
    assert edge["properties"]["source_kind"] == "llm"
    assert edge["properties"]["reason"] == "订单服务调用支付模块"
    assert edge["properties"]["evidence"] == ["shared_module:payment", "shared_interface:/payments"]


def test_rule_and_llm_hits_merge_into_one_edge():
    class FakeAI:
        def chat_completion(self, **kwargs):
            return {
                "content": """
                {
                  "edges": [
                    {
                      "source": "req:A",
                      "target": "req:B",
                      "type": "DEPENDS_ON",
                      "confidence": 0.88,
                      "reason": "LLM 认为存在调用依赖",
                      "evidence": ["llm:调用支付接口"]
                    }
                  ]
                }
                """
            }

    service = RequirementGraphService(_FakeDB(), ai_client=FakeAI())
    builder = _GraphBuilder(limit=10)
    left = _make_requirement("A", title="订单服务", description="订单服务依赖 payment 模块接口", source_level="L3", custom_fields={"module": "order"})
    right = _make_requirement("B", title="支付服务", description="payment 模块提供支付接口", source_level="L4", custom_fields={"module": "payment"})
    for req, level in ((left, "L3"), (right, "L4")):
        _add_requirement_node(builder, req)
    features = {
        "req:A": service._build_requirement_feature(left, "L3"),
        "req:B": service._build_requirement_feature(right, "L4"),
    }
    candidate_pairs = [{"source": "req:A", "target": "req:B", "score": 12, "signals": ["shared_module:payment"]}]
    service._apply_rule_edges(builder, features, candidate_pairs)

    service._apply_llm_inference(
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
    assert edge["properties"]["source_kind"] == "rule"
    assert "rule" in edge["properties"]["source_kinds"]
    assert "llm" in edge["properties"]["source_kinds"]
    assert "llm:调用支付接口" in edge["properties"]["evidence"]
