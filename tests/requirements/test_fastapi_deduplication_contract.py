"""
FastAPI deduplication route contract tests.

These tests enforce FastAPI-native validation semantics.
"""

import pytest

from backend_business.api.routers import deduplication


class _DummyDedupService:
    def __init__(self):
        self.detect_kwargs = None

    def detect_duplicates(self, **kwargs):
        self.detect_kwargs = kwargs
        return {
            "duplicate_groups": [],
            "total_duplicates": 0,
            "total_requirements_scanned": 0,
            "total_merged": None,
        }

    def execute_merge(self, **kwargs):
        return {
            "primary_req_id": kwargs["primary_req_id"],
            "deleted_count": len(kwargs["to_delete_req_ids"]),
            "old_text": "old",
            "new_text": kwargs["merged_text"],
            "reason": kwargs.get("reason", ""),
        }

    def delete_requirements(self, **kwargs):
        return {"deleted_count": len(kwargs["req_ids"])}

    def update_requirement(self, **kwargs):
        return {
            "req_id": kwargs["req_id"],
            "old_text": "old",
            "new_text": kwargs["new_text"],
        }

    def get_similar_pairs(self, **kwargs):
        return {"pairs": [], "total_pairs": 0, "total_requirements_scanned": 0}

    def regenerate_llm_decision(self, **kwargs):
        return {"requirements": [], "similarity": 0.0, "llm_decision": {"should_merge": False}}


def _assert_validation_error(response, field: str):
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert isinstance(detail, list)
    assert any(item.get("loc") == ["body", field] for item in detail)


@pytest.fixture
async def api_client(monkeypatch):
    dummy = _DummyDedupService()
    monkeypatch.setattr(deduplication, "_dedup_service", dummy)

    app = build_test_app(deduplication.router)

    async with async_client(app) as client:
        yield client, dummy


async def test_detect_missing_session_id(api_client):
    client, _ = api_client
    response = await client.post("/api/v2/dedup/detect", json={})
    _assert_validation_error(response, "session_id")


async def test_detect_empty_session_id(api_client):
    client, _ = api_client
    response = await client.post("/api/v2/dedup/detect", json={"session_id": ""})
    _assert_validation_error(response, "session_id")


async def test_detect_invalid_bool_values_rejected(api_client):
    client, _ = api_client
    response = await client.post(
        "/api/v2/dedup/detect",
        json={
            "session_id": "s1",
            "with_llm_decision": "abc",
            "auto_merge": "",
        },
    )
    assert response.status_code == 422


async def test_detect_null_bool_values_rejected(api_client):
    client, _ = api_client
    response = await client.post(
        "/api/v2/dedup/detect",
        json={
            "session_id": "s1",
            "with_llm_decision": None,
            "auto_merge": None,
        },
    )
    assert response.status_code == 422


async def test_detect_valid_payload_calls_service(api_client):
    client, dummy = api_client
    response = await client.post(
        "/api/v2/dedup/detect",
        json={
            "session_id": "s1",
            "with_llm_decision": True,
            "auto_merge": False,
        },
    )
    assert response.status_code == 200
    assert dummy.detect_kwargs["with_llm_decision"] is True
    assert dummy.detect_kwargs["auto_merge"] is False


async def test_merge_missing_primary_req_id(api_client):
    client, _ = api_client
    response = await client.post(
        "/api/v2/dedup/merge",
        json={
            "session_id": "s1",
            "primary_req_id": "",
            "to_delete_req_ids": ["r2"],
            "merged_text": "merged requirement text",
            "merged_level": "L2",
        },
    )
    _assert_validation_error(response, "primary_req_id")


async def test_delete_missing_req_ids(api_client):
    client, _ = api_client
    response = await client.post(
        "/api/v2/dedup/delete",
        json={"session_id": "s1", "req_ids": []},
    )
    _assert_validation_error(response, "req_ids")


async def test_update_missing_new_text(api_client):
    client, _ = api_client
    response = await client.post(
        "/api/v2/dedup/update",
        json={"session_id": "s1", "req_id": "r1", "new_text": ""},
    )
    _assert_validation_error(response, "new_text")


async def test_regenerate_requires_at_least_two_ids(api_client):
    client, _ = api_client
    response = await client.post(
        "/api/v2/dedup/regenerate",
        json={"session_id": "s1", "req_ids": ["r1"]},
    )
    _assert_validation_error(response, "req_ids")

