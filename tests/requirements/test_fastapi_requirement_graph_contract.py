"""FastAPI requirement graph route contract tests."""

from __future__ import annotations

import pytest

from backend_business.api.routers import requirement_graph


class _StubRequirementGraphService:
    def __init__(self) -> None:
        self.calls = []
        self.latest_calls = []
        self.latest_any_mode_calls = []
        self.history_calls = []
        self.snapshot_calls = []
        self.delete_calls = []

    def build_graph(self, **kwargs):
        self.calls.append(kwargs)
        return {
            "nodes": [{"id": "req:A", "kind": "requirement", "label": "A", "group": "L4", "properties": {}}],
            "edges": [
                {
                    "id": "DEPENDS_ON:req:A->req:B",
                    "source": "req:A",
                    "target": "req:B",
                    "type": "DEPENDS_ON",
                    "label": "依赖",
                    "weight": 0.88,
                    "properties": {
                        "source_kind": "llm",
                        "source_detail": "llm_tool_review",
                        "review_action": "update",
                        "review_package_id": "pkg-2",
                        "model": "deepseek-v4-pro",
                        "reason": "reviewed",
                        "evidence": ["a", "b"],
                        "confidence": 0.88,
                    },
                }
            ],
            "stats": {
                "node_count": 1,
                "edge_count": 1,
                "inferred_edge_count": 1,
                "relation_review": {
                    "package_count": 3,
                    "reviewed_pair_count": 24,
                    "added_count": 1,
                    "updated_count": 2,
                    "deleted_count": 1,
                    "fallback_used": False,
                    "model": "deepseek-v4-pro",
                },
            },
            "legend": {"edge_types": ["DEPENDS_ON"]},
        }

    def get_latest_snapshot_graph(self, **kwargs):
        self.latest_calls.append(kwargs)
        return {
            "nodes": [],
            "edges": [],
            "stats": {},
            "meta": {
                "loaded_from_snapshot": True,
                "relation_snapshot": {
                    "snapshot_id": "snap-latest",
                    "relation_mode": kwargs.get("relation_mode") or "llm",
                },
            },
        }

    def get_latest_snapshot_graph_any_mode(self, **kwargs):
        self.latest_any_mode_calls.append(kwargs)
        return {
            "nodes": [],
            "edges": [],
            "stats": {},
            "meta": {
                "loaded_from_snapshot": True,
                "relation_snapshot": {
                    "snapshot_id": "snap-any-mode",
                    "relation_mode": "llm",
                },
            },
        }

    def list_snapshot_history(self, **kwargs):
        self.history_calls.append(kwargs)
        return [
            {
                "snapshot_id": "snap-latest",
                "project_id": kwargs.get("project_id"),
                "session_id": kwargs.get("session_id"),
                "relation_mode": kwargs.get("relation_mode") or "llm",
                "edge_count": 4,
                "created_at": "2026-04-20T06:00:00+00:00",
                "invalidated_at": None,
                "is_active": True,
            }
        ]

    def get_snapshot_graph(self, snapshot_id, **kwargs):
        self.snapshot_calls.append({"snapshot_id": snapshot_id, **kwargs})
        return {
            "nodes": [],
            "edges": [],
            "stats": {},
            "meta": {
                "loaded_from_snapshot": True,
                "relation_snapshot": {
                    "snapshot_id": snapshot_id,
                    "relation_mode": "local",
                },
            },
        }

    def delete_relation_snapshots(self, **kwargs):
        self.delete_calls.append(kwargs)
        return {
            "deleted_count": 7,
            "project_id": kwargs.get("project_id"),
            "session_id": kwargs.get("session_id"),
            "relation_mode": kwargs.get("relation_mode"),
        }

    async def stream_graph_events(self, **kwargs):
        self.calls.append({"stream": True, **kwargs})
        yield "base_graph", {"graph": {"nodes": [], "edges": [], "stats": {}}}
        yield "candidate_edges", {"edges": []}
        yield "review_progress", {
            "completed_pairs": 0,
            "total_pairs": 0,
            "completed_packages": 0,
            "total_packages": 0,
        }
        yield "snapshot_saved", {
            "snapshot_status": "final",
            "snapshot": {"snapshot_id": "snap-stream"},
        }
        yield "done", {"snapshot": {"snapshot_id": "snap-stream"}}

    async def stream_discover_relation_events(self, **kwargs):
        self.calls.append({"discover_stream": True, **kwargs})
        yield "base_graph", {"graph": {"nodes": [], "edges": [], "stats": {}}}
        yield "discover_progress", {
            "completed_packages": 0,
            "total_packages": 1,
            "added_edges": 0,
            "skipped_packages": 0,
            "review_concurrency": kwargs.get("review_concurrency"),
        }
        yield "relation_decision", {
            "action": "add",
            "edge": {
                "source": "req:A",
                "target": "req:B",
                "type": "DEPENDS_ON",
                "properties": {"source_kind": "llm"},
            },
            "reason": "discovered",
            "confidence": 0.82,
            "package_id": "top-1",
        }
        yield "snapshot_saved", {
            "snapshot_status": "final",
            "snapshot": {"snapshot_id": "snap-discover"},
        }
        yield "done", {"snapshot": {"snapshot_id": "snap-discover"}}


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub_service = _StubRequirementGraphService()
    monkeypatch.setattr(
        requirement_graph,
        "_require_graph_service",
        lambda **_kwargs: stub_service,
    )
    app = build_test_app(requirement_graph.router)
    async with async_client(app) as client:
        yield client, stub_service


async def test_get_requirement_graph_infer_contract_exposes_relation_review_stats(fastapi_client):
    client, stub_service = fastapi_client

    response = await client.get(
        "/api/v2/requirement-graph",
        params={"project_id": "P-1", "infer": "true"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    stats = body["data"]["stats"]
    assert stats["relation_review"]["package_count"] == 3
    assert stats["relation_review"]["updated_count"] == 2
    edge_props = body["data"]["edges"][0]["properties"]
    assert edge_props["source_detail"] == "llm_tool_review"
    assert edge_props["review_action"] == "update"
    assert edge_props["review_package_id"] == "pkg-2"
    assert stub_service.calls[0]["infer_relations"] is True


async def test_get_requirement_graph_local_mode_passes_relation_mode_through(fastapi_client):
    client, stub_service = fastapi_client

    response = await client.get(
        "/api/v2/requirement-graph",
        params={"project_id": "P-1", "relation_mode": "local"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert stub_service.calls[0]["relation_mode"] == "local"
    assert stub_service.calls[0]["infer_relations"] is False


async def test_post_requirement_graph_infer_contract_exposes_relation_review_stats(fastapi_client):
    client, stub_service = fastapi_client

    response = await client.post(
        "/api/v2/requirement-graph/infer",
        json={"project_id": "P-2", "session_id": "S-9", "limit": 80, "inference_limit": 24},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["stats"]["relation_review"]["reviewed_pair_count"] == 24
    assert stub_service.calls[0]["project_id"] == "P-2"
    assert stub_service.calls[0]["session_id"] == "S-9"
    assert stub_service.calls[0]["infer_relations"] is True


async def test_post_requirement_graph_infer_contract_passes_review_edges_through(fastapi_client):
    client, stub_service = fastapi_client
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

    response = await client.post(
        "/api/v2/requirement-graph/infer",
        json={"project_id": "P-2", "review_edges": review_edges},
    )

    assert response.status_code == 200
    assert stub_service.calls[0]["review_edges"] == review_edges


async def test_post_requirement_graph_infer_contract_passes_review_concurrency_through(fastapi_client):
    client, stub_service = fastapi_client

    response = await client.post(
        "/api/v2/requirement-graph/infer",
        json={"project_id": "P-2", "review_concurrency": 4},
    )

    assert response.status_code == 200
    assert stub_service.calls[0]["review_concurrency"] == 4


async def test_get_requirement_graph_latest_contract_returns_snapshot_graph(fastapi_client):
    client, stub_service = fastapi_client

    response = await client.get(
        "/api/v2/requirement-graph/latest",
        params={"project_id": "P-1", "relation_mode": "llm", "limit": 900},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["meta"]["relation_snapshot"]["snapshot_id"] == "snap-latest"
    assert body["data"]["meta"]["loaded_from_snapshot"] is True
    assert stub_service.latest_calls[0] == {
        "project_id": "P-1",
        "session_id": None,
        "relation_mode": "llm",
        "limit": 900,
    }


async def test_get_requirement_graph_latest_contract_uses_any_mode_when_relation_mode_missing(fastapi_client):
    client, stub_service = fastapi_client

    response = await client.get(
        "/api/v2/requirement-graph/latest",
        params={"project_id": "P-1", "limit": 900},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["meta"]["relation_snapshot"]["snapshot_id"] == "snap-any-mode"
    assert stub_service.latest_any_mode_calls[0] == {
        "project_id": "P-1",
        "session_id": None,
        "limit": 900,
    }


async def test_get_requirement_graph_history_contract_returns_snapshot_list(fastapi_client):
    client, stub_service = fastapi_client

    response = await client.get(
        "/api/v2/requirement-graph/history",
        params={"project_id": "P-1", "session_id": "S-1", "relation_mode": "local", "limit": 12},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["items"][0]["snapshot_id"] == "snap-latest"
    assert body["data"]["items"][0]["edge_count"] == 4
    assert stub_service.history_calls[0] == {
        "project_id": "P-1",
        "session_id": "S-1",
        "relation_mode": "local",
        "limit": 12,
    }


async def test_get_requirement_graph_snapshot_contract_returns_requested_snapshot(fastapi_client):
    client, stub_service = fastapi_client

    response = await client.get(
        "/api/v2/requirement-graph/snapshots/snap-2",
        params={"limit": 700},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["meta"]["relation_snapshot"]["snapshot_id"] == "snap-2"
    assert stub_service.snapshot_calls[0] == {"snapshot_id": "snap-2", "limit": 700}


async def test_delete_requirement_graph_relations_contract(fastapi_client):
    client, stub_service = fastapi_client

    response = await client.request(
        "DELETE",
        "/api/v2/requirement-graph/relations",
        json={"project_id": "P-1", "session_id": "S-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["deleted_count"] == 7
    assert stub_service.delete_calls[0] == {
        "project_id": "P-1",
        "session_id": "S-1",
        "relation_mode": None,
    }


async def test_post_requirement_graph_stream_contract_returns_sse(fastapi_client):
    client, stub_service = fastapi_client

    response = await client.post(
        "/api/v2/requirement-graph/stream",
        json={"project_id": "P-2", "inference_limit": 48},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert "event: base_graph" in text
    assert "event: candidate_edges" in text
    assert "event: snapshot_saved" in text
    assert "event: done" in text
    assert stub_service.calls[0]["stream"] is True
    assert stub_service.calls[0]["package_size"] == 6
    assert stub_service.calls[0]["review_concurrency"] == 3
    assert stub_service.calls[0]["model"] == "deepseek-v4-pro"


async def test_post_requirement_graph_discover_stream_contract_returns_sse(fastapi_client):
    client, stub_service = fastapi_client

    response = await client.post(
        "/api/v2/requirement-graph/discover/stream",
        json={"project_id": "P-2", "package_size": 12, "review_concurrency": 4},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert "event: base_graph" in text
    assert "event: discover_progress" in text
    assert "event: relation_decision" in text
    assert "event: snapshot_saved" in text
    assert "event: done" in text
    assert stub_service.calls[0]["discover_stream"] is True
    assert "package_size" not in stub_service.calls[0]
    assert stub_service.calls[0]["limit"] == 900
    assert stub_service.calls[0]["review_concurrency"] == 4
    assert stub_service.calls[0]["model"] == "deepseek-v4-pro"
