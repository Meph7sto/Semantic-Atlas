from flask import Blueprint, jsonify, request

from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service
from backend_business.config import settings
from backend_business.services.doors_store import DoorsStore


analysis_bp = Blueprint("analysis_api", __name__)

def _maybe_store_trace_result(
    payload: dict,
    result: dict,
) -> dict | None:
    if not settings.DOORS_DB_URL:
        return None

    project_name = (payload.get("project_name") or settings.DOORS_PROJECT_NAME or "default").strip()
    created_by = (payload.get("created_by") or "").strip() or None

    store = DoorsStore(settings.DOORS_DB_URL)
    project_id = store.ensure_project(project_name)

    ws_id = store.create_workspace(
        project_id=project_id,
        scope_query={
            "stage": "trace",
            "mode": "batch" if isinstance(result.get("relations"), list) else "relation",
        },
        created_by=created_by,
    )
    run_id = store.create_analysis_run(
        workspace_id=ws_id,
        stage="trace",
        config={
            "max_new_tokens": payload.get("max_new_tokens"),
            "save_to_db": payload.get("save_to_db"),
        },
        status="success",
    )

    # Inputs -> requirement objects
    def _upsert_req(text: str, obj_type: str) -> str:
        imported = store.upsert_requirement(
            project_id=project_id,
            object_type=obj_type,
            text_body=text,
            status="Proposed",
            source_kind="manual",
            created_by=created_by,
            quality_metrics={"source": "trace_input", "run_id": run_id},
        )
        return imported.object_id

    # 单对
    if isinstance(result.get("has_relation"), bool):
        high = (payload.get("high_level_requirement") or "").strip()
        low = (payload.get("low_level_requirement") or "").strip()
        high_oid = _upsert_req(high, "system")
        low_oid = _upsert_req(low, "system")
        if bool(result.get("has_relation")):
            link_type = str(result.get("relation_type") or "general")
            confidence = result.get("confidence")
            store.create_or_update_link(
                project_id=project_id,
                src_object_id=high_oid,
                dst_object_id=low_oid,
                link_type=link_type,
                confidence=float(confidence) if confidence is not None else None,
                evidence={"trace_result": result, "analysis_run_id": run_id},
                created_by=created_by,
            )
        return {"project_id": project_id, "workspace_id": ws_id, "analysis_run_id": run_id}

    # 批量：relations 内逐条落 link_revision（仅 has_relation=True）
    highs = payload.get("high_level_requirements") or []
    lows = payload.get("low_level_requirements") or []
    high_ids = [(_upsert_req(str(h).strip(), "system")) for h in highs if str(h).strip()]
    low_ids = [(_upsert_req(str(l).strip(), "system")) for l in lows if str(l).strip()]

    created_links = 0
    for rel in (result.get("relations") or []):
        try:
            if not rel.get("has_relation"):
                continue
            hi = int(rel.get("high_level_index"))
            li = int(rel.get("low_level_index"))
            if hi < 0 or hi >= len(high_ids) or li < 0 or li >= len(low_ids):
                continue
            link_type = str(rel.get("relation_type") or "general")
            conf = rel.get("confidence")
            store.create_or_update_link(
                project_id=project_id,
                src_object_id=high_ids[hi],
                dst_object_id=low_ids[li],
                link_type=link_type,
                confidence=float(conf) if conf is not None else None,
                evidence={"trace_record": rel, "analysis_run_id": run_id},
                created_by=created_by,
            )
            created_links += 1
        except Exception:
            continue

    return {"project_id": project_id, "workspace_id": ws_id, "analysis_run_id": run_id, "links_created": created_links}


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
        doors = _maybe_store_trace_result(payload, result)
        return jsonify({"success": True, "data": result, "record_id": record_id, "doors": doors})
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
        doors = _maybe_store_trace_result(payload, result)
        return jsonify({"success": True, "data": result, "record_id": record_id, "doors": doors})
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

