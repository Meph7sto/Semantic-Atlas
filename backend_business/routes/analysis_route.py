import json
import os
from uuid import uuid4

from flask import Blueprint, Response, jsonify, request, stream_with_context
from psycopg2.extras import RealDictCursor

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
def ingest_transcript():  # 已迁移
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
def ingest_transcript_stream():  # 已迁移
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
def get_sample_transcript():  # 已迁移
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
    session_id = payload.get("session_id")
    max_new_tokens = int(payload.get("max_new_tokens", 1600))

    highs = [str(s).strip() for s in highs if str(s).strip()]
    lows = [str(s).strip() for s in lows if str(s).strip()]

    if not highs or not lows:
        return jsonify({"success": False, "error": "请提供顶层需求列表和底层需求列表"}), 400

    try:
        result = ai_proxy.trace_batch(highs, lows, max_new_tokens=max_new_tokens)
        record_id = None
        if save_to_db:
            record_id = db_service.save_batch(highs, lows, result, session_id=session_id)
        return jsonify({"success": True, "data": result, "record_id": record_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analysis_bp.route("/trace/latest", methods=["GET"])
def get_latest_trace_batch():
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"success": False, "error": "缺少 session_id"}), 400
    data = db_service.get_latest_trace_batch(session_id)
    if not data:
        return jsonify({"success": True, "data": None})
    return jsonify({"success": True, "data": data})


@analysis_bp.route("/trace-by-mapping", methods=["POST"])
def trace_by_mapping():
    """
    基于数据库映射关系的追溯分析
    
    只分析验证数据库中已有对应关系的顶层-底层需求对，
    而不是全量笛卡尔积分析，大幅减少分析组合数。
    
    请求体：
    {
        "session_id": "xxx",
        "save_to_db": true,
        "max_new_tokens": 800
    }
    """
    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    save_to_db = bool(payload.get("save_to_db", False))
    max_new_tokens = int(payload.get("max_new_tokens", 800))

    if not session_id:
        return jsonify({"success": False, "error": "缺少 session_id"}), 400

    try:
        # 从数据库获取有映射关系的需求对
        pairs = db_service.get_requirement_pairs_for_trace(session_id)
        
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
            return jsonify({
                "success": True,
                "data": empty_result,
                "record_id": None,
                "pairs_analyzed": 0,
                "total_possible_pairs": 0,
            })

        # 构建追溯分析所需的数据结构
        # 去重：同一个顶层需求可能对应多个底层需求
        high_texts = []
        low_texts = []
        high_id_map = {}  # text -> id
        low_id_map = {}   # text -> id
        
        for pair in pairs:
            ht = pair["high_req_text"]
            lt = pair["low_req_text"]
            if ht not in high_id_map:
                high_id_map[ht] = pair["high_req_id"]
                high_texts.append(ht)
            if lt not in low_id_map:
                low_id_map[lt] = pair["low_req_id"]
                low_texts.append(lt)

        # 只对有映射关系的对进行分析
        # 构建需要分析的 (high_index, low_index) 列表
        pair_indices = []
        for pair in pairs:
            hi = high_texts.index(pair["high_req_text"])
            li = low_texts.index(pair["low_req_text"])
            if (hi, li) not in pair_indices:
                pair_indices.append((hi, li))

        # 调用推理后端进行追溯分析（仅分析指定的对）
        result = ai_proxy.trace_batch_selective(
            high_texts, 
            low_texts, 
            pair_indices,
            max_new_tokens=max_new_tokens
        )

        # 为关系补充顶层/底层需求ID，便于前端正确连线
        pair_id_map = {}
        for pair in pairs:
            hi = high_texts.index(pair["high_req_text"])
            li = low_texts.index(pair["low_req_text"])
            pair_id_map[(hi, li)] = (pair["high_req_id"], pair["low_req_id"])

        for rel in result.get("relations", []):
            hi = rel.get("high_level_index")
            li = rel.get("low_level_index")
            if hi is None or li is None:
                continue
            if (hi, li) in pair_id_map:
                rel["high_req_id"], rel["low_req_id"] = pair_id_map[(hi, li)]
        
        record_id = None
        if save_to_db:
            record_id = db_service.save_batch(high_texts, low_texts, result, session_id=session_id)

        return jsonify({
            "success": True, 
            "data": result, 
            "record_id": record_id,
            "pairs_analyzed": len(pair_indices),
            "total_possible_pairs": len(high_texts) * len(low_texts),
        })

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


# ========================
# Phase 2: Context Building APIs
# ========================

@analysis_bp.route("/analysis/build_context", methods=["POST"])
def build_context():  # 已迁移
    """
    Phase 2: 构建上下文（非流式）
    POST /api/analysis/build_context
    
    Request:
    {
        "session_id": "...",
        "options": {
            "window_size": 8,
            "step_size": 7,
            "tau": 0.6,
            "top_k": 3,
            "max_edges_per_window": 24,
            "token_limit_per_bundle": 4000,
            "mock_llm": false
        }
    }
    """
    from backend_business.services.context_builder import context_builder
    
    payload = request.get_json(silent=True) or {}
    session_id = (payload.get("session_id") or "").strip()
    
    if not session_id:
        return jsonify({"success": False, "error": "session_id 不能为空"}), 400
    
    options = payload.get("options") or {}
    
    try:
        result = context_builder.build_context(session_id, options)
        return jsonify({"success": True, "data": result})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@analysis_bp.route("/analysis/build_context/stream", methods=["POST"])
def build_context_stream():  # 已迁移
    """
    Phase 2: 构建上下文（SSE流式）
    POST /api/analysis/build_context/stream
    
    返回 text/event-stream
    """
    from backend_business.services.context_builder import context_builder
    
    payload = request.get_json(silent=True) or {}
    session_id = (payload.get("session_id") or "").strip()
    
    if not session_id:
        return jsonify({"success": False, "error": "session_id 不能为空"}), 400
    
    options = payload.get("options") or {}
    
    def generate():
        try:
            for event in context_builder.build_context_stream(session_id, options):
                event_data = {
                    "event": event.event,
                    **event.data
                }
                yield f"data: {json.dumps(event_data, ensure_ascii=False)}\n\n"
        except Exception as e:
            error_data = {"event": "error", "message": str(e)}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"
    
    headers = {
        "Content-Type": "text/event-stream",
        "Cache-Control": "no-cache",
        "X-Accel-Buffering": "no",
    }
    return Response(stream_with_context(generate()), headers=headers)


@analysis_bp.route("/analysis/context_runs", methods=["GET"])
def list_context_runs():  # 已迁移
    """
    获取context_runs列表
    GET /api/analysis/context_runs?session_id=xxx
    """
    from backend_business.services.db_service import db_service
    
    session_id = request.args.get("session_id", "").strip()
    
    with db_service._connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            if session_id:
                cur.execute(
                    """
                    SELECT context_run_id, session_id, options_snapshot, status, stats, created_at::text
                    FROM context_runs
                    WHERE session_id = %s
                    ORDER BY created_at DESC
                    """,
                    (session_id,)
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
            rows = cur.fetchall()
    
    return jsonify({"success": True, "data": rows})


@analysis_bp.route("/analysis/bundles/<context_run_id>", methods=["GET"])
def get_bundles(context_run_id: str):  # 已迁移
    """
    获取指定context_run下的bundles和bundle_items
    GET /api/analysis/bundles/<context_run_id>
    """
    from backend_business.services.db_service import db_service
    from psycopg2.extras import RealDictCursor
    
    with db_service._connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            # 获取bundles
            cur.execute(
                """
                SELECT bundle_id, context_run_id, session_id, order_index, status, context_summary, meta, created_at::text
                FROM bundles
                WHERE context_run_id = %s
                ORDER BY order_index
                """,
                (context_run_id,)
            )
            bundles = cur.fetchall()
            
            if not bundles:
                return jsonify({"success": False, "error": "No bundles found"}), 404
            
            # 获取bundle_items
            bundle_ids = [b["bundle_id"] for b in bundles]
            cur.execute(
                """
                SELECT bi.bundle_id, bi.span_id, bi.span_ref, bi.order_index, s.text, s.speaker, s.start_ms, s.end_ms
                FROM bundle_items bi
                JOIN spans s ON bi.span_id = s.span_id
                WHERE bi.bundle_id = ANY(%s)
                ORDER BY bi.bundle_id, bi.order_index
                """,
                (bundle_ids,)
            )
            items = cur.fetchall()
    
    # 组织数据
    items_by_bundle = {}
    for item in items:
        bid = item["bundle_id"]
        if bid not in items_by_bundle:
            items_by_bundle[bid] = []
        items_by_bundle[bid].append(dict(item))
    
    result = []
    for bundle in bundles:
        bundle_data = dict(bundle)
        bundle_data["items"] = items_by_bundle.get(bundle["bundle_id"], [])
        
        # 生成bundle_text（使用短引用）
        bundle_text_lines = []
        for item in bundle_data["items"]:
            time_info = f"{item['start_ms']}-{item['end_ms']}" if item['start_ms'] is not None else "?"
            speaker = item['speaker'] or 'unknown'
            bundle_text_lines.append(f"[{item['span_ref']}] [{time_info}] [{speaker}]: {item['text']}")
        bundle_data["bundle_text"] = "\n".join(bundle_text_lines)
        
        result.append(bundle_data)
    
    return jsonify({"success": True, "data": result})


@analysis_bp.route("/analysis/span_links/<context_run_id>", methods=["GET"])
def get_span_links(context_run_id: str):  # 已迁移
    """
    获取指定context_run下的边列表
    GET /api/analysis/span_links/<context_run_id>
    """
    from backend_business.services.db_service import db_service
    from psycopg2.extras import RealDictCursor
    
    with db_service._connect() as conn:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                """
                SELECT id, context_run_id, source_span_id, target_span_id, relation_type, strength, note, created_at::text
                FROM span_links
                WHERE context_run_id = %s
                ORDER BY strength DESC
                """,
                (context_run_id,)
            )
            rows = cur.fetchall()
    
    return jsonify({"success": True, "data": rows})


@analysis_bp.route("/analysis/spans/<session_id>", methods=["GET"])
def get_spans_by_session(session_id: str):  # 已迁移
    """
    获取指定session下的spans（按时间顺序），带短引用序号
    GET /api/analysis/spans/<session_id>
    """
    from backend_business.services.db_service import db_service
    from psycopg2.extras import RealDictCursor

    session_id = (session_id or "").strip()
    if not session_id:
        return jsonify({"success": False, "error": "session_id 不能为空"}), 400

    with db_service._connect() as conn:
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
            rows = cur.fetchall()

    spans = []
    for idx, row in enumerate(rows, start=1):
        span = dict(row)
        span["order_index"] = idx
        span["span_ref"] = f"S{idx}"
        spans.append(span)

    return jsonify({"success": True, "data": spans})

