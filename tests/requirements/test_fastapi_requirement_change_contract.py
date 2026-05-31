import pytest

from backend_business.api.http.errors import validation_error_handler
from backend_business.api.routers import requirement_change


class _StubAnalysisService:
    def __init__(self):
        self.last_payload = None

    def analyze_requirement_change(self, **kwargs):
        self.last_payload = kwargs
        requirement_id = kwargs["requirement_id"]
        if requirement_id == "missing":
            raise requirement_change.RequirementChangeAnalysisNotFoundError("需求不存在")
        if requirement_id == "wrong-project":
            raise ValueError("需求不属于当前项目")
        if requirement_id == "full":
            return {
                "source_requirement": {
                    "requirement_id": requirement_id,
                    "project_id": kwargs["project_id"],
                    "title": "源需求",
                    "source_level": "L3",
                    "status": "confirmed",
                    "priority": "medium",
                    "tags": ["core", "audit"],
                },
                "before": {
                    "title": "源需求",
                    "description": "原始描述",
                    "tags": ["core", "audit"],
                    "priority": "medium",
                    "status": "confirmed",
                },
                "after": {
                    "title": kwargs["changes"].get("title", "源需求"),
                    "description": kwargs["changes"].get("description", "原始描述"),
                    "tags": kwargs["changes"].get("tags", ["core", "audit"]),
                    "priority": kwargs["changes"].get("priority", "medium"),
                    "status": kwargs["changes"].get("status", "confirmed"),
                },
                "changed_fields": [
                    field
                    for field in ("title", "description", "tags", "priority", "status")
                    if field in kwargs["changes"]
                ],
                "summary": {
                    "analysis_status": "completed",
                    "message": "已生成影响分析",
                    "impacted_count": 2,
                    "direct_count": 1,
                    "high_risk_count": 1,
                    "advisory_count": 1,
                },
                "impacted_requirements": [
                    {
                        "requirement_id": "CHILD",
                        "title": "子需求",
                        "source_level": "L4",
                        "impact_level": "high",
                        "min_distance": 1,
                        "trigger_relations": ["REFINES"],
                        "short_reason": "下游细化需求直接承接变更源语义，建议同步评估。",
                    },
                    {
                        "requirement_id": "DEP2",
                        "title": "二跳依赖方",
                        "source_level": "L3",
                        "impact_level": "medium",
                        "min_distance": 2,
                        "trigger_relations": ["DEPENDS_ON"],
                        "short_reason": "通过依赖链路传播的间接受影响需求，建议检查前置假设是否仍成立。",
                    },
                ],
                "propagation_paths": [
                    {
                        "target_requirement_id": "CHILD",
                        "path": [
                            {
                                "source": requirement_id,
                                "target": "CHILD",
                                "type": "REFINES",
                                "source_kind": "structural",
                                "source_detail": "manage_requirements.parent_id",
                            }
                        ],
                        "reason": "下游细化需求直接承接变更源语义，建议同步评估。",
                    }
                ],
                "advisories": {
                    "similar_candidates": [
                        {
                            "requirement_id": "SIMILAR",
                            "title": "相似需求",
                            "source_level": "L3",
                            "impact_level": "low",
                            "reason": "与变更源标签、模块或关键词相近，建议人工补充关注。",
                        }
                    ]
                },
            }
        if kwargs["changes"].get("title") == "same":
            return {
                "source_requirement": {"requirement_id": requirement_id},
                "before": {"title": "same"},
                "after": {"title": "same"},
                "changed_fields": [],
                "summary": {
                    "analysis_status": "no_effective_change",
                    "message": "无有效变更",
                    "impacted_count": 0,
                    "direct_count": 0,
                    "high_risk_count": 0,
                    "advisory_count": 0,
                },
                "impacted_requirements": [],
                "propagation_paths": [],
                "advisories": {"similar_candidates": []},
            }
        return {
            "source_requirement": {"requirement_id": requirement_id},
            "before": {"title": "old"},
            "after": {"title": kwargs["changes"].get("title", "old")},
            "changed_fields": ["title"] if "title" in kwargs["changes"] else [],
            "summary": {
                "analysis_status": "completed",
                "message": "已生成影响分析",
                "impacted_count": 0,
                "direct_count": 0,
                "high_risk_count": 0,
                "advisory_count": 0,
            },
            "impacted_requirements": [],
            "propagation_paths": [],
            "advisories": {"similar_candidates": []},
        }


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub = _StubAnalysisService()
    monkeypatch.setattr(requirement_change, "_require_change_analysis_service", lambda: stub)
    app = build_test_app(requirement_change.router)

    async with async_client(app) as client:
        yield client, stub


async def test_analyze_requirement_change_rejects_illegal_fields(fastapi_client):
    client, _ = fastapi_client
    response = await client.post(
        "/api/v2/requirement-change/analyze",
        json={
            "project_id": "P-1",
            "requirement_id": "REQ-1",
            "changes": {"owner": "u-1"},
        },
    )

    assert response.status_code == 422


async def test_analyze_requirement_change_returns_404_for_missing_requirement(fastapi_client):
    client, _ = fastapi_client
    response = await client.post(
        "/api/v2/requirement-change/analyze",
        json={
            "project_id": "P-1",
            "requirement_id": "missing",
            "changes": {"title": "new title"},
        },
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "需求不存在"


async def test_analyze_requirement_change_returns_400_for_cross_project_requirement(fastapi_client):
    client, _ = fastapi_client
    response = await client.post(
        "/api/v2/requirement-change/analyze",
        json={
            "project_id": "P-1",
            "requirement_id": "wrong-project",
            "changes": {"title": "new title"},
        },
    )

    assert response.status_code == 400
    assert response.json()["detail"] == "需求不属于当前项目"


async def test_analyze_requirement_change_returns_frontend_drawer_payload(fastapi_client):
    client, stub = fastapi_client
    response = await client.post(
        "/api/v2/requirement-change/analyze",
        json={
            "project_id": "P-1",
            "requirement_id": "full",
            "changes": {
                "title": "新的源需求标题",
                "description": "新的语义描述",
                "tags": ["core", "audit", "changed"],
                "priority": "high",
                "status": "in_progress",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()

    assert stub.last_payload == {
        "project_id": "P-1",
        "requirement_id": "full",
        "changes": {
            "title": "新的源需求标题",
            "description": "新的语义描述",
            "tags": ["core", "audit", "changed"],
            "priority": "high",
            "status": "in_progress",
        },
    }
    assert body["source_requirement"]["requirement_id"] == "full"
    assert body["before"]["title"] == "源需求"
    assert body["after"]["tags"] == ["core", "audit", "changed"]
    assert body["changed_fields"] == [
        "title",
        "description",
        "tags",
        "priority",
        "status",
    ]
    assert body["summary"] == {
        "analysis_status": "completed",
        "message": "已生成影响分析",
        "impacted_count": 2,
        "direct_count": 1,
        "high_risk_count": 1,
        "advisory_count": 1,
    }
    assert body["impacted_requirements"][0] == {
        "requirement_id": "CHILD",
        "title": "子需求",
        "source_level": "L4",
        "impact_level": "high",
        "min_distance": 1,
        "trigger_relations": ["REFINES"],
        "short_reason": "下游细化需求直接承接变更源语义，建议同步评估。",
    }
    assert body["propagation_paths"][0]["path"][0] == {
        "source": "full",
        "target": "CHILD",
        "type": "REFINES",
        "source_kind": "structural",
        "source_detail": "manage_requirements.parent_id",
    }
    assert body["advisories"]["similar_candidates"][0]["requirement_id"] == "SIMILAR"


async def test_analyze_requirement_change_returns_no_effective_change_result(fastapi_client):
    client, stub = fastapi_client
    response = await client.post(
        "/api/v2/requirement-change/analyze",
        json={
            "project_id": "P-1",
            "requirement_id": "REQ-1",
            "changes": {"title": "same"},
        },
    )

    assert response.status_code == 200
    assert response.json()["summary"]["analysis_status"] == "no_effective_change"
    assert stub.last_payload["changes"] == {"title": "same"}


async def test_analyze_requirement_change_omits_unset_fields(fastapi_client):
    client, stub = fastapi_client
    response = await client.post(
        "/api/v2/requirement-change/analyze",
        json={
            "project_id": "P-1",
            "requirement_id": "REQ-1",
            "changes": {"status": "completed"},
        },
    )

    assert response.status_code == 200
    assert stub.last_payload["changes"] == {"status": "completed"}
