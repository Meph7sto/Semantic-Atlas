from backend_business.services.requirement_graph_service import (
    RequirementGraphService,
    _GraphBuilder,
    _as_list,
    _req_node_id,
)


def test_req_node_id_keeps_existing_prefix():
    assert _req_node_id("REQ-1") == "req:REQ-1"
    assert _req_node_id("req:REQ-1") == "req:REQ-1"


def test_as_list_accepts_json_arrays_and_plain_text():
    assert _as_list('["安全", "性能"]') == ["安全", "性能"]
    assert _as_list("安全") == ["安全"]
    assert _as_list(None) == []


def test_classification_adds_category_and_similarity_edges():
    class FakeDB:
        def get_latest_classification(self, session_id):
            assert session_id == "S-1"
            return {
                "id": 7,
                "requirements": ["用户必须登录", "管理员必须登录", "系统应加密传输"],
                "predictions": [
                    {"label": "身份认证", "requirement": "用户必须登录"},
                    {"label": "身份认证", "requirement": "管理员必须登录"},
                    {"label": "安全", "requirement": "系统应加密传输"},
                ],
            }

    builder = _GraphBuilder(limit=20)
    service = RequirementGraphService(FakeDB())
    text_index = {}
    for req_id, text in [
        ("REQ-1", "用户必须登录"),
        ("REQ-2", "管理员必须登录"),
        ("REQ-3", "系统应加密传输"),
    ]:
        node_id = _req_node_id(req_id)
        builder.add_node(
            node_id,
            kind="requirement",
            label=text,
            group="L3",
            properties={"req_id": req_id, "content": text},
        )
        text_index["".join(text.lower().split())] = [node_id]

    service._apply_classification(builder, "S-1", text_index)
    graph = builder.to_graph()

    assert builder.nodes["req:REQ-1"]["properties"]["category"] == "身份认证"
    assert builder.nodes["req:REQ-3"]["properties"]["category"] == "安全"
    assert any(edge["type"] == "SIMILAR_TO" for edge in graph["edges"])


def test_graph_stats_use_dynamic_label_distribution_without_hardcoded_labels():
    class FakeDB:
        def get_connection(self):
            raise AssertionError("No database reads needed in this unit test")

        def get_latest_classification(self, session_id):
            assert session_id == "S-1"
            return {
                "id": 8,
                "total": 3,
                "requirements": ["需求A", "需求B", "需求C"],
                "predictions": [
                    {"predicted_label": "定制标签甲", "requirement": "需求A"},
                    {"predicted_label": "定制标签乙", "requirement": "需求B"},
                    {"predicted_label": "定制标签甲", "requirement": "需求C"},
                ],
                "label_distribution": {"定制标签甲": 2, "定制标签乙": 1},
            }

    builder = _GraphBuilder(limit=10)
    text_index = {}
    for req_id, text in [("A", "需求A"), ("B", "需求B"), ("C", "需求C")]:
        node_id = _req_node_id(req_id)
        builder.add_node(node_id, "requirement", text, "L4", {"content": text})
        text_index["".join(text.lower().split())] = [node_id]

    stats = RequirementGraphService(FakeDB())._apply_classification(
        builder,
        "S-1",
        text_index,
    )

    assert stats["label_distribution"] == {"定制标签甲": 2, "定制标签乙": 1}
    assert builder.nodes["req:A"]["properties"]["category"] == "定制标签甲"
    assert builder.nodes["req:B"]["properties"]["category"] == "定制标签乙"


def test_inference_scope_keeps_people_and_validation_evidence():
    builder = _GraphBuilder(limit=10)
    builder.add_node(
        "req:R-1",
        "requirement",
        "支付结果可审计",
        "L4",
        {
            "content": "系统应记录支付审计日志",
            "priority": 4,
            "component": "payment",
            "created_by": "u-creator",
            "updated_by": "u-updater",
            "assignee": "u-owner",
            "validation_rules": {"test_method": "审计回放"},
            "interfaces": ["POST /payments"],
        },
    )
    builder.add_node(
        "stakeholder:u-owner",
        "stakeholder",
        "产品负责人",
        "PO",
        {
            "role": "PO",
            "roles": ["PO"],
            "type": "internal",
            "authority": "decision",
            "department": "产品部",
            "title": "产品负责人",
        },
    )
    builder.add_edge(
        "req:R-1",
        "stakeholder:u-owner",
        "OWNS",
        "负责",
        0.91,
        {"source": "llm_inference", "reason": "负责支付范围"},
    )

    scope = RequirementGraphService(object())._build_inference_scope(builder, inference_limit=12)
    requirement = scope["requirements"][0]
    stakeholder = scope["stakeholders"][0]
    edge = scope["existing_edges"][0]

    assert requirement["people_evidence"] == {
        "created_by": "u-creator",
        "updated_by": "u-updater",
        "assignee": "u-owner",
    }
    assert requirement["validation_evidence"]["validation_rules"] == {"test_method": "审计回放"}
    assert requirement["target_modules"] == ["payment"]
    assert stakeholder["roles"] == ["PO"]
    assert stakeholder["department"] == "产品部"
    assert edge["source_detail"] == "llm_inference"
    assert edge["reason"] == "负责支付范围"


def test_apply_stakeholders_keeps_candidate_nodes_without_authority_mapping():
    class FakeDB:
        def list_project_members(self, project_id, include_roles=False):
            assert project_id == "P-1"
            assert include_roles is True
            return {
                "members": [
                    {
                        "user_id": "u-po",
                        "display_name": "产品负责人",
                        "username": "po",
                        "external_type": "internal",
                        "roles": [{"role_id": "PO"}],
                        "department": "产品部",
                        "title": "负责人",
                    }
                ]
            }

    builder = _GraphBuilder(limit=10)
    RequirementGraphService(FakeDB())._apply_stakeholders(
        builder,
        "P-1",
        [{"created_by": "u-po"}, {"assignee": "u-observer"}],
    )

    assert builder.nodes["stakeholder:u-po"]["properties"]["source"] == "project_members/auth_users"
    assert "authority" not in builder.nodes["stakeholder:u-po"]["properties"]
    assert builder.nodes["stakeholder:u-observer"]["properties"]["source"] == "requirement_people_evidence"


def test_llm_inference_can_add_new_stakeholders_and_merge_existing_candidates():
    class FakeAI:
        def chat_completion(self, **kwargs):
            return {
                "content": """
                {
                  "stakeholders": [
                    {
                      "id": "stakeholder:llm:owner",
                      "label": "产品负责人",
                      "role": "PO",
                      "reason": "负责需求目标"
                    },
                    {
                      "id": "stakeholder:llm:auditor",
                      "label": "审计专员",
                      "role": "AUDITOR",
                      "department": "风控部",
                      "title": "审计负责人",
                      "reason": "负责上线审计"
                    }
                  ],
                  "edges": [
                    {
                      "source": "stakeholder:llm:owner",
                      "target": "req:R-1",
                      "type": "OWNS",
                      "confidence": 0.91,
                      "reason": "负责交付范围"
                    },
                    {
                      "source": "stakeholder:llm:auditor",
                      "target": "req:R-1",
                      "type": "APPROVES",
                      "confidence": 0.82,
                      "reason": "负责审计审批"
                    }
                  ]
                }
                """
            }

    builder = _GraphBuilder(limit=20)
    builder.add_node(
        "req:R-1",
        "requirement",
        "支付结果可审计",
        "L4",
        {"content": "系统应记录支付审计日志", "level": "L4"},
    )
    builder.add_node(
        "stakeholder:u-owner",
        "stakeholder",
        "产品负责人",
        "PO",
        {"role": "PO", "source": "project_members/auth_users"},
    )

    stats = RequirementGraphService(object(), ai_client=FakeAI())._apply_llm_inference(
        builder,
        project_id="P-1",
        session_id="S-1",
        enabled=True,
        model="fake-model",
        inference_limit=12,
    )

    assert stats["inferred_stakeholder_count"] == 1
    assert stats["inferred_edge_count"] == 2
    assert builder.nodes["stakeholder:u-owner"]["properties"]["source"] == "project_members/auth_users"
    assert builder.nodes["stakeholder:u-owner"]["properties"]["inference_reason"] == "负责需求目标"
    new_stakeholder = builder.nodes["stakeholder:llm:auditor"]
    assert new_stakeholder["properties"]["source"] == "llm_inference"
    assert new_stakeholder["properties"]["department"] == "风控部"
    assert ("stakeholder:u-owner", "req:R-1", "OWNS") in builder.edges
    assert ("stakeholder:llm:auditor", "req:R-1", "APPROVES") in builder.edges


def test_inference_scope_prefers_connected_and_evidence_rich_requirements():
    builder = _GraphBuilder(limit=40)
    for index in range(12):
        builder.add_node(
            f"req:R-{index}",
            "requirement",
            f"普通需求{index}",
            "L3",
            {"content": f"普通需求{index}", "level": "L3", "priority": 1},
        )
    builder.add_node(
        "req:R-critical",
        "requirement",
        "关键审计需求",
        "L4",
        {
            "content": "系统应记录并校验关键审计日志",
            "level": "L4",
            "priority": 5,
            "category": "安全",
            "component": "audit",
            "validation_rules": {"test_method": "回放审计日志"},
        },
    )
    builder.add_node(
        "req:R-peer",
        "requirement",
        "关联审计需求",
        "L4",
        {"content": "系统应支持审计检索", "level": "L4", "priority": 4},
    )
    builder.add_edge(
        "req:R-critical",
        "req:R-peer",
        "REFINES",
        "细化",
        0.92,
        {"source": "trace_analysis"},
    )

    scope = RequirementGraphService(object())._build_inference_scope(builder, inference_limit=12)
    requirement_ids = {item["id"] for item in scope["requirements"]}

    assert "req:R-critical" in requirement_ids
    assert "req:R-peer" in requirement_ids


def test_llm_inference_does_not_merge_ambiguous_stakeholder_labels():
    class FakeAI:
        def chat_completion(self, **kwargs):
            return {
                "content": """
                {
                  "stakeholders": [
                    {
                      "id": "stakeholder:llm:zhangwei",
                      "label": "张伟",
                      "role": "PO",
                      "reason": "负责该需求"
                    }
                  ],
                  "edges": [
                    {
                      "source": "stakeholder:llm:zhangwei",
                      "target": "req:R-1",
                      "type": "OWNS",
                      "confidence": 0.88,
                      "reason": "负责需求范围"
                    }
                  ]
                }
                """
            }

    builder = _GraphBuilder(limit=20)
    builder.add_node(
        "req:R-1",
        "requirement",
        "支付结果可审计",
        "L4",
        {"content": "系统应记录支付审计日志", "level": "L4"},
    )
    builder.add_node(
        "stakeholder:u-po-1",
        "stakeholder",
        "张伟",
        "PO",
        {"role": "PO", "department": "产品部", "source": "project_members/auth_users"},
    )
    builder.add_node(
        "stakeholder:u-po-2",
        "stakeholder",
        "张伟",
        "PO",
        {"role": "PO", "department": "交付部", "source": "project_members/auth_users"},
    )

    stats = RequirementGraphService(object(), ai_client=FakeAI())._apply_llm_inference(
        builder,
        project_id="P-1",
        session_id="S-1",
        enabled=True,
        model="fake-model",
        inference_limit=12,
    )

    assert stats["inferred_stakeholder_count"] == 1
    assert "stakeholder:llm:zhangwei" in builder.nodes
    assert ("stakeholder:llm:zhangwei", "req:R-1", "OWNS") in builder.edges
