from backend_business.services.requirement_change_analysis_service import (
    RequirementChangeAnalysisNotFoundError,
    RequirementChangeAnalysisService,
)


def _make_requirement(req_id="SRC"):
    return {
        "req_id": req_id,
        "project_id": "P-1",
        "title": "源需求",
        "description": "原始描述",
        "tags": ["core", "audit"],
        "priority": "medium",
        "status": "confirmed",
        "source_level": "L3",
        "deleted": False,
    }


def _make_graph():
    nodes = [
        _node("PARENT", "父需求", "L2"),
        _node("SRC", "源需求", "L3"),
        _node("CHILD", "子需求", "L4"),
        _node("GRAND", "孙需求", "L4"),
        _node("DEP1", "直接依赖方", "L3"),
        _node("DEP2", "二跳依赖方", "L3"),
        _node("CONFLICT", "冲突需求", "L3"),
        _node("VALIDATE", "验证需求", "L4"),
        _node("SIMILAR", "相似需求", "L3"),
        _node("MULTI", "多路径命中", "L4"),
    ]
    edges = [
        _edge("PARENT", "SRC", "REFINES", "structural", "manage_requirements.parent_id"),
        _edge("SRC", "CHILD", "REFINES", "structural", "manage_requirements.parent_id"),
        _edge("CHILD", "GRAND", "REFINES", "structural", "manage_requirements.parent_id"),
        _edge("DEP1", "SRC", "DEPENDS_ON", "rule", "rule_dependency_signal_match"),
        _edge("DEP2", "DEP1", "DEPENDS_ON", "rule", "rule_dependency_signal_match"),
        _edge("SRC", "CONFLICT", "CONFLICTS_WITH", "rule", "rule_conflict_signal_match"),
        _edge("SRC", "VALIDATE", "VALIDATES_WITH", "rule", "rule_validation_overlap"),
        _edge("SRC", "SIMILAR", "SIMILAR_TO", "rule", "rule_similarity_recall"),
        _edge("MULTI", "SRC", "DEPENDS_ON", "rule", "rule_dependency_signal_match"),
        _edge("SRC", "MULTI", "VALIDATES_WITH", "rule", "rule_validation_overlap"),
    ]
    return {"nodes": nodes, "edges": edges, "stats": {}}


def _node(req_id, title, level):
    return {
        "id": f"req:{req_id}",
        "kind": "requirement",
        "label": title,
        "group": level,
        "properties": {
            "req_id": req_id,
            "title": title,
            "source_level": level,
        },
    }


def _edge(source, target, edge_type, source_kind, source_detail):
    return {
        "id": f"{edge_type}:{source}->{target}",
        "source": f"req:{source}",
        "target": f"req:{target}",
        "type": edge_type,
        "properties": {
            "source_kind": source_kind,
            "source_detail": source_detail,
        },
    }


class _StubManageService:
    def __init__(self, requirement=None):
        self.requirement = requirement or _make_requirement()

    def get_requirement(self, req_id):
        if self.requirement and self.requirement.get("req_id") == req_id:
            return dict(self.requirement)
        return None


class _StubGraphService:
    def __init__(self, graph=None):
        self.graph = graph or _make_graph()
        self.last_kwargs = None

    def build_graph(self, **kwargs):
        self.last_kwargs = kwargs
        return self.graph


def test_semantic_change_triggers_full_propagation_and_advisories():
    manage_service = _StubManageService()
    graph_service = _StubGraphService()
    service = RequirementChangeAnalysisService(manage_service, graph_service)

    result = service.analyze_requirement_change(
        project_id="P-1",
        requirement_id="SRC",
        changes={"title": "新的源需求标题"},
    )

    impacted = {item["requirement_id"]: item for item in result["impacted_requirements"]}

    assert graph_service.last_kwargs["infer_relations"] is False
    assert result["changed_fields"] == ["title"]
    assert impacted["CHILD"]["impact_level"] == "high"
    assert impacted["GRAND"]["impact_level"] == "medium"
    assert impacted["PARENT"]["impact_level"] == "medium"
    assert impacted["DEP1"]["impact_level"] == "high"
    assert impacted["DEP2"]["impact_level"] == "medium"
    assert impacted["CONFLICT"]["impact_level"] == "high"
    assert impacted["VALIDATE"]["impact_level"] == "medium"
    assert "SIMILAR" not in impacted
    assert result["advisories"]["similar_candidates"][0]["requirement_id"] == "SIMILAR"
    assert result["summary"]["high_risk_count"] == 4
    assert result["summary"]["direct_count"] == 6


def test_frontend_drawer_contract_for_semantic_change_result():
    service = RequirementChangeAnalysisService(_StubManageService(), _StubGraphService())

    result = service.analyze_requirement_change(
        project_id="P-1",
        requirement_id="SRC",
        changes={
            "title": "新的源需求标题",
            "description": "新的语义描述",
            "tags": ["core", "audit", "changed"],
            "priority": "high",
            "status": "in_progress",
        },
    )

    assert result["source_requirement"] == {
        "requirement_id": "SRC",
        "project_id": "P-1",
        "title": "源需求",
        "source_level": "L3",
        "status": "confirmed",
        "priority": "medium",
        "tags": ["core", "audit"],
    }
    assert result["before"] == {
        "title": "源需求",
        "description": "原始描述",
        "tags": ["core", "audit"],
        "priority": "medium",
        "status": "confirmed",
    }
    assert result["after"] == {
        "title": "新的源需求标题",
        "description": "新的语义描述",
        "tags": ["core", "audit", "changed"],
        "priority": "high",
        "status": "in_progress",
    }
    assert result["changed_fields"] == [
        "title",
        "description",
        "tags",
        "priority",
        "status",
    ]
    assert result["summary"] == {
        "analysis_status": "completed",
        "message": "已生成影响分析",
        "impacted_count": 8,
        "direct_count": 6,
        "high_risk_count": 4,
        "advisory_count": 1,
    }

    first_impact = result["impacted_requirements"][0]
    assert set(first_impact) == {
        "requirement_id",
        "title",
        "source_level",
        "impact_level",
        "min_distance",
        "trigger_relations",
        "short_reason",
    }
    assert first_impact["impact_level"] == "high"
    assert isinstance(first_impact["trigger_relations"], list)
    assert first_impact["short_reason"]

    path_by_target = {
        item["target_requirement_id"]: item for item in result["propagation_paths"]
    }
    child_path = path_by_target["CHILD"]
    assert child_path["reason"]
    assert child_path["path"] == [
        {
            "source": "SRC",
            "target": "CHILD",
            "type": "REFINES",
            "source_kind": "structural",
            "source_detail": "manage_requirements.parent_id",
        }
    ]
    assert result["advisories"]["similar_candidates"] == [
        {
            "requirement_id": "SIMILAR",
            "title": "相似需求",
            "source_level": "L3",
            "impact_level": "low",
            "reason": "与变更源标签、模块或关键词相近，建议人工补充关注。",
        }
    ]


def test_management_change_only_produces_one_hop_impacts():
    service = RequirementChangeAnalysisService(_StubManageService(), _StubGraphService())

    result = service.analyze_requirement_change(
        project_id="P-1",
        requirement_id="SRC",
        changes={"priority": "high"},
    )

    impacted_ids = {item["requirement_id"] for item in result["impacted_requirements"]}

    assert result["changed_fields"] == ["priority"]
    assert {"PARENT", "CHILD", "DEP1", "CONFLICT", "VALIDATE", "MULTI"} <= impacted_ids
    assert "GRAND" not in impacted_ids
    assert "DEP2" not in impacted_ids


def test_multi_path_target_keeps_highest_risk_and_aggregated_relations():
    service = RequirementChangeAnalysisService(_StubManageService(), _StubGraphService())

    result = service.analyze_requirement_change(
        project_id="P-1",
        requirement_id="SRC",
        changes={"description": "新的语义描述"},
    )

    impacted = {item["requirement_id"]: item for item in result["impacted_requirements"]}
    multi = impacted["MULTI"]

    assert multi["impact_level"] == "high"
    assert multi["min_distance"] == 1
    assert multi["trigger_relations"] == ["DEPENDS_ON", "VALIDATES_WITH"]


def test_same_value_change_returns_no_effective_change():
    service = RequirementChangeAnalysisService(_StubManageService(), _StubGraphService())

    result = service.analyze_requirement_change(
        project_id="P-1",
        requirement_id="SRC",
        changes={"status": "confirmed"},
    )

    assert result["summary"]["analysis_status"] == "no_effective_change"
    assert result["impacted_requirements"] == []


def test_no_relation_graph_returns_no_impact_but_frontend_shape_is_stable():
    graph = {"nodes": [_node("SRC", "源需求", "L3")], "edges": [], "stats": {}}
    service = RequirementChangeAnalysisService(
        _StubManageService(),
        _StubGraphService(graph=graph),
    )

    result = service.analyze_requirement_change(
        project_id="P-1",
        requirement_id="SRC",
        changes={"description": "新的语义描述"},
    )

    assert result["summary"] == {
        "analysis_status": "no_impact",
        "message": "未发现直接影响范围",
        "impacted_count": 0,
        "direct_count": 0,
        "high_risk_count": 0,
        "advisory_count": 0,
    }
    assert result["changed_fields"] == ["description"]
    assert result["impacted_requirements"] == []
    assert result["propagation_paths"] == []
    assert result["advisories"] == {"similar_candidates": []}


def test_missing_source_node_in_graph_raises_not_found():
    service = RequirementChangeAnalysisService(
        _StubManageService(),
        _StubGraphService(graph={"nodes": [_node("OTHER", "其他需求", "L3")], "edges": []}),
    )

    try:
        service.analyze_requirement_change(
            project_id="P-1",
            requirement_id="SRC",
            changes={"title": "新的源需求标题"},
        )
    except RequirementChangeAnalysisNotFoundError as exc:
        assert str(exc) == "图谱中未找到对应需求"
    else:
        raise AssertionError("expected RequirementChangeAnalysisNotFoundError")


def test_requirement_from_another_project_is_rejected_before_graph_build():
    requirement = _make_requirement()
    requirement["project_id"] = "P-2"
    graph_service = _StubGraphService()
    service = RequirementChangeAnalysisService(
        _StubManageService(requirement=requirement),
        graph_service,
    )

    try:
        service.analyze_requirement_change(
            project_id="P-1",
            requirement_id="SRC",
            changes={"title": "新的源需求标题"},
        )
    except ValueError as exc:
        assert str(exc) == "需求不属于当前项目"
    else:
        raise AssertionError("expected ValueError")

    assert graph_service.last_kwargs is None


def test_missing_requirement_raises_not_found():
    service = RequirementChangeAnalysisService(_StubManageService(requirement=None), _StubGraphService())

    try:
        service.analyze_requirement_change(
            project_id="P-1",
            requirement_id="MISSING",
            changes={"title": "x"},
        )
    except RequirementChangeAnalysisNotFoundError as exc:
        assert str(exc) == "需求不存在"
    else:
        raise AssertionError("expected RequirementChangeAnalysisNotFoundError")
