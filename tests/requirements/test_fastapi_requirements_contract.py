"""
FastAPI requirements route contract tests.
"""

from collections.abc import Generator
from typing import Any

import httpx
import pytest
import requests
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError


from backend_business.api.http.errors import (
    error_response_handler,
    validation_error_handler,
)
from backend_business.api.routers import requirements


class _StubAIProxy:
    def __init__(self):
        self.extract_calls: list[dict[str, Any]] = []

    def extract_requirements(
        self,
        text: str,
        chunk_size: int = 3600,
        overlap: int = 500,
        clean_model: str = "deepseek-reasoner",
        extract_model: str = "deepseek-reasoner",
    ):
        self.extract_calls.append(
            {
                "text": text,
                "chunk_size": chunk_size,
                "overlap": overlap,
                "clean_model": clean_model,
                "extract_model": extract_model,
            }
        )
        return {"items": [{"text": text}], "count": 1}


class _StubRequirementsService:
    def __init__(self):
        self.clear_calls: list[str] = []
        self.extract_calls: list[dict[str, Any]] = []
        self.stream_calls: list[dict[str, Any]] = []
        self.session_calls: list[dict[str, Any]] = []
        self.detail_calls: list[str] = []
        self.stats_calls: list[str | None] = []
        self.detail_data: dict[str, Any] | None = {"req_id": "r-1", "text": "hello"}
        self.delete_result = True
        self.stats_data = {"total": 10}

    def clear_requirements_for_session(self, session_id: str) -> int:
        self.clear_calls.append(session_id)
        return 2

    def extract_requirements_for_session(self, **kwargs):
        self.extract_calls.append(kwargs)
        return {"session_id": kwargs["session_id"], "total_inserted": 3}

    def extract_requirements_for_session_stream(
        self, **kwargs
    ) -> Generator[dict[str, Any], None, None]:
        self.stream_calls.append(kwargs)
        yield {"event": "progress", "data": {"anchor": 1}}
        yield {"event": "final", "data": {"ok": True}}

    def get_requirements_by_session(self, **kwargs):
        self.session_calls.append(kwargs)
        return {"requirements": [{"req_id": "r-1"}], "total": 1}

    def get_requirement_detail(self, req_id: str):
        self.detail_calls.append(req_id)
        return self.detail_data

    def delete_requirement(self, req_id: str) -> bool:
        return self.delete_result

    def get_statistics(self, session_id: str | None = None):
        self.stats_calls.append(session_id)
        return {**self.stats_data, "session_id": session_id}


class _StubDedupService:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    def detect_duplicates(self, **kwargs):
        self.calls.append(kwargs)
        return {"duplicate_groups": [], "total_duplicates": 0}


class _StubDBService:
    def __init__(self):
        self.list_calls: list[dict[str, Any]] = []
        self.exists_calls: list[str] = []
        self.top_id_calls: list[tuple[str, list[str]]] = []
        self.save_calls: list[dict[str, Any]] = []
        self.existing_top_ids: list[str] = []

    def get_l4_requirements_by_session(
        self,
        session_id: str,
        page: int = 1,
        per_page: int = 100,
        top_req_ids: list[str] | None = None,
    ):
        self.list_calls.append(
            {
                "session_id": session_id,
                "page": page,
                "per_page": per_page,
                "top_req_ids": top_req_ids,
            }
        )
        return {"requirements": [{"req_id": "l4-1"}], "total": 1}

    def has_l4_requirements(self, session_id: str) -> bool:
        self.exists_calls.append(session_id)
        return True

    def get_existing_top_req_ids(
        self, session_id: str, top_req_ids: list[str]
    ) -> list[str]:
        self.top_id_calls.append((session_id, top_req_ids))
        return self.existing_top_ids

    def save_l4_requirements(self, session_id: str, reqs: list[dict[str, Any]]):
        self.save_calls.append({"session_id": session_id, "reqs": reqs})
        return {"inserted": len(reqs), "duplicates": 0, "inserted_ids": ["l4-1"]}


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub_ai = _StubAIProxy()
    stub_requirements = _StubRequirementsService()
    stub_dedup = _StubDedupService()
    stub_db = _StubDBService()

    monkeypatch.setattr(requirements, "ai_proxy", stub_ai)
    monkeypatch.setattr(requirements, "requirements_service", stub_requirements)
    monkeypatch.setattr(requirements, "dedup_service", stub_dedup)
    monkeypatch.setattr(requirements, "db_service", stub_db)

    app = build_test_app(requirements.router)

    async with async_client(app) as client:
        yield client, stub_ai, stub_requirements, stub_dedup, stub_db


async def test_extract_requirements_success_returns_raw_data(fastapi_client):
    client, stub_ai, _, _, _ = fastapi_client

    response = await client.post(
        "/api/v2/requirements/extract",
        json={"text": "  需求文本  ", "chunk_size": 1000, "overlap": 120},
    )

    assert response.status_code == 200
    body = response.json()
    assert body == {"items": [{"text": "需求文本"}], "count": 1}
    assert "success" not in body
    assert stub_ai.extract_calls[0]["text"] == "需求文本"


async def test_extract_requirements_missing_text_returns_422(fastapi_client):
    client, _, _, _, _ = fastapi_client

    response = await client.post("/api/v2/requirements/extract", json={})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item.get("loc") == ["body", "text"] for item in detail)


async def test_extract_l123_strict_bool_validation_returns_422(fastapi_client):
    client, _, _, _, _ = fastapi_client

    response = await client.post(
        "/api/v2/requirements/extract_l123",
        json={"session_id": "s-1", "use_toolcall": "true"},
    )

    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item.get("loc") == ["body", "use_toolcall"] for item in detail)


async def test_extract_l123_success_with_post_dedup(fastapi_client):
    client, _, stub_requirements, stub_dedup, _ = fastapi_client

    response = await client.post(
        "/api/v2/requirements/extract_l123",
        json={
            "session_id": "session-1",
            "post_dedup": True,
            "dedup_with_llm": True,
            "dedup_auto_merge": False,
            "dedup_max_concurrent": 4,
            "enable_parallel_windows": True,
            "max_concurrent_windows": 3,
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["session_id"] == "session-1"
    assert body["cleared_before_extract"] == 2
    assert "deduplication" in body
    assert stub_requirements.extract_calls[0]["enable_parallel"] is True
    assert stub_requirements.extract_calls[0]["max_concurrent"] == 3
    assert stub_dedup.calls[0]["with_llm_decision"] is True


async def test_extract_l123_stream_emits_reset_and_dedup_events(fastapi_client):
    client, _, _, _, _ = fastapi_client

    response = await client.post(
        "/api/v2/requirements/extract_l123/stream",
        json={"session_id": "s-1", "post_dedup": True},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: reset" in response.text
    assert "event: progress" in response.text
    assert "event: dedup_start" in response.text
    assert "event: dedup_final" in response.text


async def test_get_requirements_by_session_invalid_page_returns_422(fastapi_client):
    client, _, _, _, _ = fastapi_client

    response = await client.get("/api/v2/requirements/session/s-1?page=abc")
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item.get("loc") == ["query", "page"] for item in detail)


async def test_get_requirement_detail_not_found_returns_404(fastapi_client):
    client, _, stub_requirements, _, _ = fastapi_client
    stub_requirements.detail_data = None

    response = await client.get("/api/v2/requirements/r-404")
    assert response.status_code == 404
    assert response.json()["detail"] == "Requirement not found"


async def test_get_requirements_stats_uses_stats_route_not_detail(fastapi_client):
    client, _, stub_requirements, _, _ = fastapi_client

    response = await client.get("/api/v2/requirements/stats", params={"session_id": " s-1 "})

    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 10
    assert body["session_id"] == "s-1"
    assert stub_requirements.stats_calls == ["s-1"]
    assert stub_requirements.detail_calls == []


async def test_l4_exists_and_list_success(fastapi_client):
    client, _, _, _, stub_db = fastapi_client

    exists_response = await client.get("/api/v2/requirements/l4/session-1/exists")
    assert exists_response.status_code == 200
    assert exists_response.json() == {"exists": True}
    assert stub_db.exists_calls == ["session-1"]

    list_response = await client.get("/api/v2/requirements/l4/session-1?page=1&per_page=10")
    assert list_response.status_code == 200
    body = list_response.json()
    assert "success" not in body
    assert body["total"] == 1
    assert stub_db.list_calls[0]["per_page"] == 10


async def test_generate_l4_requirements_cache_hit(fastapi_client, monkeypatch):
    client, _, _, _, stub_db = fastapi_client
    stub_db.existing_top_ids = ["t1", "t2"]

    def _unexpected_post(*args, **kwargs):
        raise AssertionError("requests.post should not be called on cache hit")

    monkeypatch.setattr(requirements.requests, "post", _unexpected_post)

    response = await client.post(
        "/api/v2/requirements/l4/generate",
        json={
            "session_id": "s-cache",
            "requirements": [{"id": "t1", "text": "A"}, {"id": "t2", "text": "B"}],
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["from_cache"] is True
    assert body["total"] == 1


async def test_generate_l4_requirements_inference_failure_returns_500(
    fastapi_client, monkeypatch
):
    client, _, _, _, stub_db = fastapi_client
    stub_db.existing_top_ids = []

    def _mock_post(*args, **kwargs):
        raise requests.exceptions.RequestException("upstream timeout")

    monkeypatch.setattr(requirements.requests, "post", _mock_post)

    response = await client.post(
        "/api/v2/requirements/l4/generate",
        json={
            "session_id": "s-1",
            "requirements": [{"id": "t1", "text": "Top req"}],
        },
    )

    assert response.status_code == 500
    assert "推理后端调用失败" in response.json()["detail"]
