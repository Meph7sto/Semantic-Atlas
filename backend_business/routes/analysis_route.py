from flask import Blueprint, jsonify, request

from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service


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

