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
