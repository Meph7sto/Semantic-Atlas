"""
FastAPI analysis route contract tests.
"""

import asyncio
import json
import os
import sys
from typing import Any, Dict, List, Optional

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.api.http.errors import (
    error_response_handler,
    validation_error_handler,
)
from backend_business.api.routers import analysis


class _FakeCursor:
    def __init__(self, state: Dict[str, Any]):
        self._state = state
        self._rows: List[Dict[str, Any]] = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query: str, params: Optional[tuple] = None):
        normalized = " ".join(query.split())

        if "FROM context_runs" in normalized:
            if params:
                sid = params[0]
                rows = [
                    r for r in self._state["context_runs"] if r["session_id"] == sid
                ]
            else:
                rows = list(self._state["context_runs"])
            self._rows = rows
            return

        if "FROM bundles" in normalized and "ORDER BY order_index" in normalized:
            context_run_id = params[0]
            rows = [
                r
                for r in self._state["bundles"]
                if r["context_run_id"] == context_run_id
            ]
            self._rows = rows
            return

        if "FROM bundle_items bi" in normalized:
            bundle_ids = set(params[0])
            rows = []
            for item in self._state["bundle_items"]:
                if item["bundle_id"] not in bundle_ids:
                    continue
                span = self._state["spans_by_id"][item["span_id"]]
                rows.append(
                    {
                        "bundle_id": item["bundle_id"],
                        "span_id": item["span_id"],
                        "span_ref": item["span_ref"],
                        "order_index": item["order_index"],
                        "text": span["text"],
                        "speaker": span["speaker"],
                        "start_ms": span["start_ms"],
                        "end_ms": span["end_ms"],
                    }
                )
            rows.sort(key=lambda r: (r["bundle_id"], r["order_index"]))
            self._rows = rows
            return

        if "FROM span_links" in normalized:
            context_run_id = params[0]
            rows = [
                r
                for r in self._state["span_links"]
                if r["context_run_id"] == context_run_id
            ]
            rows.sort(key=lambda r: r.get("strength", 0), reverse=True)
            self._rows = rows
            return

        if "FROM spans" in normalized and "WHERE session_id = %s" in normalized:
            sid = params[0]
            rows = [r for r in self._state["spans"] if r["session_id"] == sid]
            rows.sort(key=lambda r: ((r["start_ms"] or 0), r["created_at"]))
            self._rows = rows
            return

        raise AssertionError(f"Unexpected SQL in test stub: {normalized}")

    def fetchall(self):
        return list(self._rows)


class _FakeConnection:
    def __init__(self, state: Dict[str, Any]):
        self._state = state

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self, cursor_factory=None):
        return _FakeCursor(self._state)


class _FakeDBService:
    def __init__(self):
        self.upserted_spans: List[Dict[str, Any]] = []
        self._state: Dict[str, Any] = {
            "context_runs": [
                {
                    "context_run_id": "run-1",
                    "session_id": "s-1",
                    "options_snapshot": {"window_size": 8},
                    "status": "READY",
                    "stats": {"bundle_total": 1},
                    "created_at": "2026-02-25T00:00:00",
                },
                {
                    "context_run_id": "run-2",
                    "session_id": "s-2",
                    "options_snapshot": {"window_size": 9},
                    "status": "READY",
                    "stats": {"bundle_total": 2},
                    "created_at": "2026-02-26T00:00:00",
                },
            ],
            "bundles": [
                {
                    "bundle_id": "b-1",
                    "context_run_id": "run-1",
                    "session_id": "s-1",
                    "order_index": 1,
                    "status": "READY",
                    "context_summary": "summary",
                    "meta": {"is_misc": False},
                    "created_at": "2026-02-25T00:00:00",
                }
            ],
            "bundle_items": [
                {
                    "bundle_id": "b-1",
                    "span_id": "span-1",
                    "span_ref": "S1",
                    "order_index": 1,
                },
                {
                    "bundle_id": "b-1",
                    "span_id": "span-2",
                    "span_ref": "S2",
                    "order_index": 2,
                },
            ],
            "spans": [
                {
                    "span_id": "span-1",
                    "session_id": "s-1",
                    "start_ms": 0,
                    "end_ms": 1000,
                    "speaker": "PM",
                    "text": "text-1",
                    "created_at": "2026-02-25T00:00:00",
                },
                {
                    "span_id": "span-2",
                    "session_id": "s-1",
                    "start_ms": 1000,
                    "end_ms": 2000,
                    "speaker": "TL",
                    "text": "text-2",
                    "created_at": "2026-02-25T00:00:01",
                },
            ],
            "span_links": [
                {
                    "id": 1,
                    "context_run_id": "run-1",
                    "source_span_id": "span-1",
                    "target_span_id": "span-2",
                    "relation_type": "continuation",
                    "strength": 0.8,
                    "note": "n",
                    "created_at": "2026-02-25T00:00:00",
                }
            ],
        }
        self._state["spans_by_id"] = {
            row["span_id"]: row for row in self._state["spans"]
        }

    def upsert_spans(self, spans: List[Dict[str, Any]]) -> Dict[str, Any]:
        self.upserted_spans = spans
        return {"upserted_count": len(spans), "conflicts": []}

    def _connect(self):
        return _FakeConnection(self._state)


class _FakeContextBuilder:
    def build_context(self, session_id: str, options: Dict[str, Any]):
        return {
            "context_run_id": "run-ctx",
            "bundle_total": 1,
            "edge_count": 2,
            "component_count": 1,
            "session_id": session_id,
            "options": options,
        }

    def build_context_stream(self, session_id: str, options: Dict[str, Any]):
        events = [
            ("init", {"session_id": session_id, "context_run_id": "run-ctx"}),
            ("window_start", {"window_index": 1}),
            ("bundling_done", {"bundle_total": 1}),
            ("final", {"context_run_id": "run-ctx", "bundle_total": 1}),
        ]
        for event_name, payload in events:
            yield type("Evt", (), {"event": event_name, "data": payload})()


def _parse_sse_payloads(body: str):
    payloads = []
    for block in body.strip().split("\n\n"):
        if not block:
            continue
        data_lines = [line for line in block.splitlines() if line.startswith("data: ")]
        if not data_lines:
            continue
        content = "".join(line[len("data: ") :] for line in data_lines)
        payloads.append(json.loads(content))
    return payloads


@pytest.fixture
def fastapi_client(monkeypatch):
    fake_db = _FakeDBService()
    fake_builder = _FakeContextBuilder()

    monkeypatch.setattr(analysis, "db_service", fake_db)
    monkeypatch.setattr(analysis, "context_builder", fake_builder)

    def _fake_parse(transcript_text: str, session_id: str, options: Dict[str, Any]):
        spans = [
            {
                "span_id": "span-a",
                "session_id": session_id,
                "start_ms": 0,
                "end_ms": 500,
                "speaker": "PM",
                "text": transcript_text.strip(),
                "meta_json": "{}",
                "asr_confidence": None,
            }
        ]
        return spans, [], {"has_timestamp_ratio": 0.0, "speaker_count": 1}

    monkeypatch.setattr(analysis, "parse_transcript_to_spans", _fake_parse)

    app = FastAPI()
    app.include_router(analysis.router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)

    with TestClient(app, raise_server_exceptions=False) as client:
        yield client, fake_db


def test_ingest_transcript_success_shape(fastapi_client):
    client, _ = fastapi_client
    response = client.post(
        "/api/v2/analysis/ingest_transcript",
        json={"transcript_text": "hello"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "data" in body
    assert body["data"]["span_total"] == 1


def test_ingest_transcript_missing_required_field_returns_422(fastapi_client):
    client, _ = fastapi_client
    response = client.post("/api/v2/analysis/ingest_transcript", json={})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item.get("loc") == ["body", "transcript_text"] for item in detail)


def test_ingest_transcript_invalid_option_type_returns_422(fastapi_client):
    client, _ = fastapi_client
    response = client.post(
        "/api/v2/analysis/ingest_transcript",
        json={
            "transcript_text": "x",
            "options": {"max_spans_returned": "bad-number"},
        },
    )
    assert response.status_code == 422


def test_ingest_stream_emits_expected_event_order(fastapi_client):
    client, _ = fastapi_client
    response = client.post(
        "/api/v2/analysis/ingest_transcript/stream",
        json={"transcript_text": "hello"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    payloads = _parse_sse_payloads(response.text)
    events = [payload["event"] for payload in payloads]
    assert events == ["init", "parsed", "db_upserted", "final"]


def test_build_context_success_shape(fastapi_client):
    client, _ = fastapi_client
    response = client.post(
        "/api/v2/analysis/build_context",
        json={"session_id": "s-1"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["context_run_id"] == "run-ctx"


def test_build_context_missing_session_id_returns_422(fastapi_client):
    client, _ = fastapi_client
    response = client.post("/api/v2/analysis/build_context", json={})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert any(item.get("loc") == ["body", "session_id"] for item in detail)


def test_build_context_stream_emits_final_event(fastapi_client):
    client, _ = fastapi_client
    response = client.post(
        "/api/v2/analysis/build_context/stream",
        json={"session_id": "s-1"},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")

    payloads = _parse_sse_payloads(response.text)
    assert payloads[-1]["event"] == "final"


def test_build_context_stream_parallel_path_no_nested_loop_error(
    fastapi_client, monkeypatch
):
    client, _ = fastapi_client

    class _LoopInsideGeneratorBuilder:
        def build_context_stream(self, session_id: str, options: Dict[str, Any]):
            yield type(
                "Evt", (), {"event": "init", "data": {"session_id": session_id}}
            )()

            async def _fake_parallel_work():
                await asyncio.sleep(0)
                return 2

            loop = asyncio.new_event_loop()
            try:
                asyncio.set_event_loop(loop)
                result = loop.run_until_complete(_fake_parallel_work())
            finally:
                loop.close()
                asyncio.set_event_loop(None)

            yield type(
                "Evt",
                (),
                {
                    "event": "parallel_batch_complete",
                    "data": {"total_windows_processed": result},
                },
            )()
            yield type("Evt", (), {"event": "final", "data": {"ok": True}})()

    monkeypatch.setattr(analysis, "context_builder", _LoopInsideGeneratorBuilder())

    response = client.post(
        "/api/v2/analysis/build_context/stream",
        json={"session_id": "s-1", "options": {"enable_parallel_windows": True}},
    )
    assert response.status_code == 200
    payloads = _parse_sse_payloads(response.text)
    events = [payload["event"] for payload in payloads]
    assert "parallel_batch_complete" in events
    assert events[-1] == "final"


def test_context_runs_success_and_filtering(fastapi_client):
    client, _ = fastapi_client
    all_resp = client.get("/api/v2/analysis/context_runs")
    assert all_resp.status_code == 200
    assert all_resp.json()["success"] is True
    assert len(all_resp.json()["data"]) == 2

    filtered_resp = client.get("/api/v2/analysis/context_runs?session_id=s-1")
    assert filtered_resp.status_code == 200
    assert len(filtered_resp.json()["data"]) == 1


def test_bundles_not_found_returns_404_detail(fastapi_client):
    client, _ = fastapi_client
    response = client.get("/api/v2/analysis/bundles/not-found")
    assert response.status_code == 404
    assert response.json()["detail"] == "No bundles found"


def test_span_links_and_spans_success(fastapi_client):
    client, _ = fastapi_client
    links_response = client.get("/api/v2/analysis/span_links/run-1")
    spans_response = client.get("/api/v2/analysis/spans/s-1")

    assert links_response.status_code == 200
    assert links_response.json()["success"] is True
    assert len(links_response.json()["data"]) == 1

    assert spans_response.status_code == 200
    body = spans_response.json()
    assert body["success"] is True
    assert body["data"][0]["span_ref"] == "S1"
    assert body["data"][1]["span_ref"] == "S2"


def test_sample_transcript_success(fastapi_client):
    client, _ = fastapi_client
    response = client.get("/api/v2/analysis/sample_transcript")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert response.text.strip() != ""
