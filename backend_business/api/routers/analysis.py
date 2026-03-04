"""
需求分析路由
对应 Flask blueprint: analysis_bp (url_prefix="/api")
"""

import json
import os
from typing import Any, Dict, Generator, List
from uuid import uuid4

from fastapi import APIRouter, Query
from fastapi.responses import PlainTextResponse
from psycopg2.extras import RealDictCursor

from backend_business.api.http.errors import ErrorResponse
from backend_business.api.http.sse import sse_response_raw
from backend_business.api.routers.schemas.analysis_schemas import (
    BuildContextRequest,
    IngestTranscriptRequest,
)
from backend_business.services.context_builder import context_builder
from backend_business.services.db_service import db_service
from backend_business.services.transcript_parser import parse_transcript_to_spans


router = APIRouter(prefix="/api", tags=["analysis"])


def _require_db_service():
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)
    return db_service


def _sse_data(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.post("/analysis/ingest_transcript")
def ingest_transcript(req: IngestTranscriptRequest):
    service = _require_db_service()

    session_id = req.session_id or str(uuid4())
    options = req.options.model_dump()
    max_spans_returned = options.pop("max_spans_returned", 200)

    spans, warnings, stats = parse_transcript_to_spans(
        req.transcript_text,
        session_id,
        options,
    )
    upsert_result = service.upsert_spans(spans)
    conflict_warnings = [
        f"span_id conflict: {conflict['span_id']}"
        for conflict in upsert_result.get("conflicts", [])
    ]
    all_warnings = warnings + conflict_warnings

    return {
        "success": True,
        "data": {
            "session_id": session_id,
            "span_total": len(spans),
            "warnings": all_warnings,
            "spans_preview": spans[:max_spans_returned],
            "stats": stats,
        },
    }


@router.post("/analysis/ingest_transcript/stream")
def ingest_transcript_stream(req: IngestTranscriptRequest):
    service = _require_db_service()

    session_id = req.session_id or str(uuid4())
    options = req.options.model_dump()
    max_spans_returned = options.pop("max_spans_returned", 200)

    def generate() -> Generator[str, None, None]:
        received_chars = len(req.transcript_text)
        received_lines = len(req.transcript_text.splitlines())
        yield _sse_data(
            {
                "event": "init",
                "session_id": session_id,
                "received_chars": received_chars,
                "received_lines": received_lines,
            }
        )

        spans, warnings, stats = parse_transcript_to_spans(
            req.transcript_text,
            session_id,
            options,
        )
        yield _sse_data(
            {
                "event": "parsed",
                "session_id": session_id,
                "span_total": len(spans),
                "warnings": warnings,
                "stats": stats,
            }
        )

        upsert_result = service.upsert_spans(spans)
        yield _sse_data(
            {
                "event": "db_upserted",
                "session_id": session_id,
                "upserted_count": upsert_result.get("upserted_count", 0),
            }
        )

        conflict_warnings = [
            f"span_id conflict: {conflict['span_id']}"
            for conflict in upsert_result.get("conflicts", [])
        ]
        all_warnings = warnings + conflict_warnings
        yield _sse_data(
            {
                "event": "final",
                "data": {
                    "session_id": session_id,
                    "span_total": len(spans),
                    "warnings": all_warnings,
                    "spans_preview": spans[:max_spans_returned],
                    "stats": stats,
                },
            }
        )

    return sse_response_raw(generate())


@router.get("/analysis/sample_transcript")
def get_sample_transcript():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", "..", ".."))
    sample_path = os.path.join(project_root, "tests", "sample_transcript.txt")
    if not os.path.exists(sample_path):
        raise ErrorResponse("sample transcript not found", 404)
    with open(sample_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    return PlainTextResponse(content, media_type="text/plain; charset=utf-8")


@router.post("/analysis/build_context")
def build_context(req: BuildContextRequest):
    try:
        result = context_builder.build_context(
            req.session_id,
            req.options.model_dump(exclude_none=True),
        )
        return {"success": True, "data": result}
    except ValueError as exc:
        raise ErrorResponse(str(exc), 400)
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/analysis/build_context/stream")
def build_context_stream(req: BuildContextRequest):
    options = req.options.model_dump(exclude_none=True)

    def generate() -> Generator[str, None, None]:
        try:
            for event in context_builder.build_context_stream(req.session_id, options):
                event_data = {"event": event.event, **event.data}
                yield _sse_data(event_data)
        except Exception as exc:
            yield _sse_data({"event": "error", "message": str(exc)})

    return sse_response_raw(generate())


@router.get("/analysis/context_runs")
def list_context_runs(session_id: str = Query(default="")):
    service = _require_db_service()
    session_id = session_id.strip()

    with service._connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if session_id:
                cur.execute(
                    """
                    SELECT context_run_id, session_id, options_snapshot, status, stats, created_at::text
                    FROM context_runs
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    """,
                    (session_id,),
                )
            else:
                cur.execute(
                    """
                    SELECT context_run_id, session_id, options_snapshot, status, stats, created_at::text
                    FROM context_runs
                    ORDER BY created_at DESC
                    LIMIT 50
                    """
                )
            rows = [dict(row) for row in cur.fetchall()]

    return {"success": True, "data": rows}


@router.get("/analysis/bundles/{context_run_id}")
def get_bundles(context_run_id: str):
    service = _require_db_service()

    with service._connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT bundle_id, context_run_id, session_id, order_index, status, context_summary, meta, created_at::text
                FROM bundles
                WHERE context_run_id = %s
                ORDER BY order_index
                """,
                (context_run_id,),
            )
            bundles = [dict(row) for row in cur.fetchall()]
            if not bundles:
                raise ErrorResponse("No bundles found", 404)

            bundle_ids = [bundle["bundle_id"] for bundle in bundles]
            cur.execute(
                """
                SELECT bi.bundle_id, bi.span_id, bi.span_ref, bi.order_index, s.text, s.speaker, s.start_ms, s.end_ms
                FROM bundle_items bi
                JOIN spans s ON bi.span_id = s.span_id
                WHERE bi.bundle_id = ANY(%s)
                ORDER BY bi.bundle_id, bi.order_index
                """,
                (bundle_ids,),
            )
            items = [dict(row) for row in cur.fetchall()]

    items_by_bundle: Dict[str, List[Dict[str, Any]]] = {}
    for item in items:
        bundle_id = item["bundle_id"]
        if bundle_id not in items_by_bundle:
            items_by_bundle[bundle_id] = []
        items_by_bundle[bundle_id].append(item)

    result = []
    for bundle in bundles:
        bundle_data = dict(bundle)
        bundle_data["items"] = items_by_bundle.get(bundle["bundle_id"], [])
        bundle_text_lines = []
        for item in bundle_data["items"]:
            time_info = (
                f"{item['start_ms']}-{item['end_ms']}"
                if item["start_ms"] is not None
                else "?"
            )
            speaker = item["speaker"] or "unknown"
            bundle_text_lines.append(
                f"[{item['span_ref']}] [{time_info}] [{speaker}]: {item['text']}"
            )
        bundle_data["bundle_text"] = "\n".join(bundle_text_lines)
        result.append(bundle_data)

    return {"success": True, "data": result}


@router.get("/analysis/span_links/{context_run_id}")
def get_span_links(context_run_id: str):
    service = _require_db_service()

    with service._connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, context_run_id, source_span_id, target_span_id, relation_type, strength, note, created_at::text
                FROM span_links
                WHERE context_run_id = %s
                ORDER BY strength DESC
                """,
                (context_run_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]

    return {"success": True, "data": rows}


@router.get("/analysis/spans/{session_id}")
def get_spans_by_session(session_id: str):
    service = _require_db_service()

    session_id = (session_id or "").strip()
    if not session_id:
        raise ErrorResponse("session_id 不能为空", 400)

    with service._connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT span_id, session_id, start_ms, end_ms, speaker, text, created_at::text
                FROM spans
                WHERE session_id = %s
                ORDER BY COALESCE(start_ms, 0), created_at
                """,
                (session_id,),
            )
            rows = [dict(row) for row in cur.fetchall()]

    spans = []
    for idx, row in enumerate(rows, start=1):
        span = dict(row)
        span["order_index"] = idx
        span["span_ref"] = f"S{idx}"
        spans.append(span)

    return {"success": True, "data": spans}
