import json
import os
from uuid import uuid4

from flask import Blueprint, Response, jsonify, request, stream_with_context

from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service
from backend_business.services.transcript_parser import parse_transcript_to_spans


analysis_bp = Blueprint("analysis_api", __name__)


@analysis_bp.route("/health", methods=["GET"])
def health():
    """
    业务后端健康检查 + 推理后端连通性（可用则返回其 health）。
    """
    data = {"status": "ok"}
    try:
        data["inference"] = ai_proxy.health()
    except Exception as e:
        data["inference"] = {"status": "error", "detail": str(e)}
    return jsonify({"success": True, "data": data})


def _build_ingest_options(payload: dict) -> dict:
    options = payload.get("options") or {}
    estimate_missing = options.get("estimate_timestamps_if_missing", True)
    default_span_ms = options.get("default_span_ms", 8000)
    max_spans_returned = options.get("max_spans_returned", 200)
    return {
        "estimate_timestamps_if_missing": bool(estimate_missing),
        "default_span_ms": int(default_span_ms) if str(default_span_ms).isdigit() else 8000,
        "max_spans_returned": int(max_spans_returned) if str(max_spans_returned).isdigit() else 200,
    }


def _sse_event(payload: dict) -> str:
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


@analysis_bp.route("/analysis/ingest_transcript", methods=["POST"])
def ingest_transcript():
    payload = request.get_json(silent=True) or {}
    transcript_text = (payload.get("transcript_text") or "").strip()
    if not transcript_text:
        return jsonify({"success": False, "error": "transcript_text 不能为空"}), 400

    session_id = (payload.get("session_id") or "").strip() or str(uuid4())
    options = _build_ingest_options(payload)
    max_spans_returned = options.pop("max_spans_returned")

    spans, warnings, stats = parse_transcript_to_spans(transcript_text, session_id, options)
    upsert_result = db_service.upsert_spans(spans)
    conflict_warnings = [
        f"span_id conflict: {conflict['span_id']}" for conflict in upsert_result["conflicts"]
    ]
    all_warnings = warnings + conflict_warnings

    return jsonify(
        {
            "success": True,
            "data": {
                "session_id": session_id,
                "span_total": len(spans),
                "warnings": all_warnings,
                "spans_preview": spans[:max_spans_returned],
                "stats": stats,
            },
        }
    )


@analysis_bp.route("/analysis/ingest_transcript/stream", methods=["POST"])
def ingest_transcript_stream():
    payload = request.get_json(silent=True) or {}
    transcript_text = (payload.get("transcript_text") or "").strip()
    if not transcript_text:
        return jsonify({"success": False, "error": "transcript_text 不能为空"}), 400

    session_id = (payload.get("session_id") or "").strip() or str(uuid4())
    options = _build_ingest_options(payload)
    max_spans_returned = options.pop("max_spans_returned")

    def generate():
        received_chars = len(transcript_text)
        received_lines = len(transcript_text.splitlines())
        yield _sse_event(
            {
                "event": "init",
                "session_id": session_id,
                "received_chars": received_chars,
                "received_lines": received_lines,
            }
        )

        spans, warnings, stats = parse_transcript_to_spans(transcript_text, session_id, options)
        yield _sse_event(
            {
                "event": "parsed",
                "session_id": session_id,
                "span_total": len(spans),
                "warnings": warnings,
                "stats": stats,
            }
        )

        upsert_result = db_service.upsert_spans(spans)
        yield _sse_event(
            {
                "event": "db_upserted",
                "session_id": session_id,
                "upserted_count": upsert_result["upserted_count"],
            }
        )

        conflict_warnings = [
            f"span_id conflict: {conflict['span_id']}" for conflict in upsert_result["conflicts"]
        ]
        all_warnings = warnings + conflict_warnings
        yield _sse_event(
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

    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return Response(stream_with_context(generate()), headers=headers)


@analysis_bp.route("/analysis/sample_transcript", methods=["GET"])
def get_sample_transcript():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", ".."))
    sample_path = os.path.join(project_root, "tests", "sample_transcript.txt")
    if not os.path.exists(sample_path):
        return jsonify({"success": False, "error": "sample transcript not found"}), 404
    with open(sample_path, "r", encoding="utf-8") as handle:
        content = handle.read()
    return Response(content, content_type="text/plain; charset=utf-8")


@analysis_bp.route("/trace-relation", methods=["POST"])
def trace_relation():
    """
    单对追溯关系分析（兼容 ai-requirement-tracer 的 API 命名）：
    POST /api/trace-relation
    """
    payload = request.get_json(silent=True) or {}
    high = (payload.get("high_level_requirement") or "").strip()
    low = (payload.get("low_level_requirement") or "").strip()
    save_to_db = bool(payload.get("save_to_db", False))
    max_new_tokens = int(payload.get("max_new_tokens", 800))

    if not high or not low:
        return jsonify({"success": False, "error": "请提供顶层需求和底层需求"}), 400

    try:
        result = ai_proxy.trace_relation(high, low, max_new_tokens=max_new_tokens)
        record_id = None
        if save_to_db:
            record_id = db_service.save_relation(high, low, result)
        return jsonify({"success": True, "data": result, "record_id": record_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analysis_bp.route("/batch-trace-relation", methods=["POST"])
def batch_trace_relation():
    """
    批量追溯关系分析（兼容 ai-requirement-tracer 的 API 命名）：
    POST /api/batch-trace-relation
    """
    payload = request.get_json(silent=True) or {}
    highs = payload.get("high_level_requirements") or []
    lows = payload.get("low_level_requirements") or []
    save_to_db = bool(payload.get("save_to_db", False))
    max_new_tokens = int(payload.get("max_new_tokens", 1600))

    highs = [str(s).strip() for s in highs if str(s).strip()]
    lows = [str(s).strip() for s in lows if str(s).strip()]

    if not highs or not lows:
        return jsonify({"success": False, "error": "请提供顶层需求列表和底层需求列表"}), 400

    try:
        result = ai_proxy.trace_batch(highs, lows, max_new_tokens=max_new_tokens)
        record_id = None
        if save_to_db:
            record_id = db_service.save_batch(highs, lows, result)
        return jsonify({"success": True, "data": result, "record_id": record_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analysis_bp.route("/requirements", methods=["GET"])
def list_requirements():
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    data = db_service.list_requirements(page=page, per_page=per_page)
    return jsonify({"success": True, "data": data})


@analysis_bp.route("/requirements/<int:requirement_id>", methods=["GET"])
def get_requirement_detail(requirement_id: int):
    detail = db_service.get_requirement_detail(requirement_id)
    if not detail:
        return jsonify({"success": False, "error": "资源未找到"}), 404
    return jsonify({"success": True, "data": detail})


@analysis_bp.route("/requirements/<int:requirement_id>", methods=["DELETE"])
def delete_requirement(requirement_id: int):
    ok = db_service.delete_requirement(requirement_id)
    if not ok:
        return jsonify({"success": False, "error": "资源未找到"}), 404
    return jsonify({"success": True, "message": "删除成功"})


@analysis_bp.route("/statistics", methods=["GET"])
def statistics():
    data = db_service.statistics()
    return jsonify({"success": True, "data": data})


@analysis_bp.route("/trigger_analysis", methods=["POST"])
def trigger_analysis():
    """
    兼容占位符：触发分析。
    这里直接复用 /trace-relation 的能力，便于后续扩展成异步任务。
    """
    payload = request.get_json(silent=True) or {}
    high = (payload.get("high_level_requirement") or payload.get("requirement_a") or "").strip()
    low = (payload.get("low_level_requirement") or payload.get("requirement_b") or "").strip()
    if not high or not low:
        return jsonify({"success": False, "error": "请提供 high_level_requirement 与 low_level_requirement"}), 400
    try:
        result = ai_proxy.trace_relation(high, low)
        return jsonify({"success": True, "data": result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

