"""
需求分析路由
对应历史蓝图: analysis_bp (url_prefix="/api/v2")
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
    BatchTraceRelationRequest,
    BuildContextRequest,
    IngestTranscriptRequest,
    TraceByMappingRequest,
    TraceRelationRequest,
    TriggerAnalysisRequest,
)
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.context_builder import context_builder
from backend_business.services.db_service import db_service
from backend_business.services.transcript_parser import parse_transcript_to_spans


router = APIRouter(prefix="/api/v2", tags=["analysis"])


def _require_db_service():
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)
    return db_service


def _sse_data(payload: Dict[str, Any]) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@router.get("/health")
def health():
    data: Dict[str, Any] = {"status": "ok"}
    try:
        data["inference"] = ai_proxy.health()
    except Exception as exc:
        data["inference"] = {"status": "error", "detail": str(exc)}
    return {"success": True, "data": data}


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
    candidate_paths = [
        os.path.join(project_root, "tests", "sample_transcript.txt"),
        os.path.join(project_root, "tests", "fixtures", "sample_transcript.txt"),
    ]
    sample_path = next((path for path in candidate_paths if os.path.exists(path)), None)
    if not sample_path:
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


@router.post("/trace-relation")
def trace_relation(req: TraceRelationRequest):
    try:
        result = ai_proxy.trace_relation(
            req.high_level_requirement,
            req.low_level_requirement,
            max_new_tokens=req.max_new_tokens,
        )
        record_id = None
        if req.save_to_db:
            service = _require_db_service()
            record_id = service.save_relation(
                req.high_level_requirement,
                req.low_level_requirement,
                result,
            )
        return {"success": True, "data": result, "record_id": record_id}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/batch-trace-relation")
def batch_trace_relation(req: BatchTraceRelationRequest):
    highs = [text for text in req.high_level_requirements if text]
    lows = [text for text in req.low_level_requirements if text]
    if not highs or not lows:
        raise ErrorResponse("请提供顶层需求列表和底层需求列表", 400)

    try:
        result = ai_proxy.trace_batch(highs, lows, max_new_tokens=req.max_new_tokens)
        record_id = None
        if req.save_to_db:
            service = _require_db_service()
            record_id = service.save_batch(
                highs, lows, result, session_id=req.session_id
            )
        return {"success": True, "data": result, "record_id": record_id}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/trace/latest")
def get_latest_trace_batch(session_id: str = Query(...)):
    normalized_session_id = session_id.strip()
    if not normalized_session_id:
        raise ErrorResponse("缺少 session_id", 400)

    service = _require_db_service()
    data = service.get_latest_trace_batch(normalized_session_id)
    return {"success": True, "data": data}


@router.post("/trace-by-mapping")
def trace_by_mapping(req: TraceByMappingRequest):
    service = _require_db_service()

    try:
        pairs = service.get_requirement_pairs_for_trace(req.session_id)

        if not pairs:
            empty_result = {
                "summary": "未找到需求映射关系，未执行追溯分析",
                "statistics": {
                    "total_combinations": 0,
                    "relations_found": 0,
                    "relation_rate": 0.0,
                },
                "high_level_requirements": [],
                "low_level_requirements": [],
                "relations": [],
                "trace_network": {
                    "nodes": [],
                    "links": [],
                },
                "relation_types_count": None,
            }
            return {
                "success": True,
                "data": empty_result,
                "record_id": None,
                "pairs_analyzed": 0,
                "total_possible_pairs": 0,
            }

        high_texts: List[str] = []
        low_texts: List[str] = []
        high_index_map: Dict[str, int] = {}
        low_index_map: Dict[str, int] = {}

        for pair in pairs:
            high_text = pair["high_req_text"]
            low_text = pair["low_req_text"]
            if high_text not in high_index_map:
                high_index_map[high_text] = len(high_texts)
                high_texts.append(high_text)
            if low_text not in low_index_map:
                low_index_map[low_text] = len(low_texts)
                low_texts.append(low_text)

        pair_indices: List[tuple[int, int]] = []
        seen_pairs: set[tuple[int, int]] = set()
        for pair in pairs:
            idx_pair = (
                high_index_map[pair["high_req_text"]],
                low_index_map[pair["low_req_text"]],
            )
            if idx_pair in seen_pairs:
                continue
            seen_pairs.add(idx_pair)
            pair_indices.append(idx_pair)

        result = ai_proxy.trace_batch_selective(
            high_texts,
            low_texts,
            pair_indices,
            max_new_tokens=req.max_new_tokens,
        )

        pair_id_map: Dict[tuple[int, int], tuple[Any, Any]] = {}
        for pair in pairs:
            idx_pair = (
                high_index_map[pair["high_req_text"]],
                low_index_map[pair["low_req_text"]],
            )
            pair_id_map[idx_pair] = (pair["high_req_id"], pair["low_req_id"])

        for relation in result.get("relations", []):
            hi = relation.get("high_level_index")
            li = relation.get("low_level_index")
            if hi is None or li is None:
                continue
            pair_key = (hi, li)
            if pair_key in pair_id_map:
                relation["high_req_id"], relation["low_req_id"] = pair_id_map[pair_key]

        record_id = None
        if req.save_to_db:
            record_id = service.save_batch(
                high_texts,
                low_texts,
                result,
                session_id=req.session_id,
            )

        return {
            "success": True,
            "data": result,
            "record_id": record_id,
            "pairs_analyzed": len(pair_indices),
            "total_possible_pairs": len(high_texts) * len(low_texts),
        }
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/requirements")
def list_requirements(
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=10, ge=1),
):
    service = _require_db_service()
    data = service.list_requirements(page=page, per_page=per_page)
    return {"success": True, "data": data}


@router.get("/requirements/{requirement_id}")
def get_requirement_detail(requirement_id: int):
    service = _require_db_service()
    detail = service.get_requirement_detail(requirement_id)
    if not detail:
        raise ErrorResponse("资源未找到", 404)
    return {"success": True, "data": detail}


@router.delete("/requirements/{requirement_id}")
def delete_requirement(requirement_id: int):
    service = _require_db_service()
    deleted = service.delete_requirement(requirement_id)
    if not deleted:
        raise ErrorResponse("资源未找到", 404)
    return {"success": True, "message": "删除成功"}


@router.get("/statistics")
def statistics():
    service = _require_db_service()
    data = service.statistics()
    return {"success": True, "data": data}


@router.post("/trigger_analysis")
def trigger_analysis(req: TriggerAnalysisRequest):
    high = req.high_level_requirement or req.requirement_a or ""
    low = req.low_level_requirement or req.requirement_b or ""
    if not high or not low:
        raise ErrorResponse(
            "请提供 high_level_requirement 与 low_level_requirement", 400
        )

    try:
        result = ai_proxy.trace_relation(high, low)
        return {"success": True, "data": result}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)
