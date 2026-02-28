from flask import Blueprint, request, jsonify

from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service

# 创建一个 Blueprint (蓝图)，用于组织冲突检测相关的路由
conflict_bp = Blueprint("conflict", __name__)


@conflict_bp.route("/check", methods=["POST"])
def check_conflict():  # 已迁移到 backend_business/api/routers/conflict.py
    """
    检查冲突接口
    通过 ai_proxy 服务代理请求到推理后端 (Inference Backend)
    响应格式与追溯接口保持一致：{success, data, record_id}
    """
    payload = request.get_json(silent=True) or {}
    requirement_a = (payload.get("requirement_a") or "").strip()
    requirement_b = (payload.get("requirement_b") or "").strip()
    save_to_db = bool(payload.get("save_to_db", False))
    session_id = payload.get("session_id")

    if not requirement_a or not requirement_b:
        return jsonify(
            {"success": False, "error": "请提供 requirement_a 与 requirement_b"}
        ), 400

    try:
        result = ai_proxy.conflict_check(requirement_a, requirement_b)
        record_id = None

        if save_to_db and db_service:
            record_ids = db_service.save_conflict_batch(
                session_id=session_id,
                conflicts=[
                    {
                        "requirement_a": requirement_a,
                        "requirement_b": requirement_b,
                        "is_conflict": result.get("is_conflict", False),
                        "raw_response": result.get("raw_response", ""),
                        "data": result,
                    }
                ],
            )
            if record_ids:
                record_id = record_ids[0]

        return jsonify({"success": True, "data": result, "record_id": record_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@conflict_bp.route("/check/batch", methods=["POST"])
def check_conflict_batch():  # 已迁移到 backend_business/api/routers/conflict.py
    """
    批量检查冲突接口
    """
    payload = request.get_json(silent=True) or {}
    pairs = payload.get(
        "pairs", []
    )  # List[{'requirement_a': str, 'requirement_b': str}]
    save_to_db = bool(payload.get("save_to_db", False))
    session_id = payload.get("session_id")

    if not pairs:
        return jsonify({"success": False, "error": "请提供 pairs 列表"}), 400

    try:
        results = []
        conflicts_to_save = []

        for pair in pairs:
            req_a = pair.get("requirement_a", "").strip()
            req_b = pair.get("requirement_b", "").strip()
            if not req_a or not req_b:
                continue

            result = ai_proxy.conflict_check(req_a, req_b)
            results.append({"requirement_a": req_a, "requirement_b": req_b, **result})

            if save_to_db:
                conflicts_to_save.append(
                    {
                        "requirement_a": req_a,
                        "requirement_b": req_b,
                        "is_conflict": result.get("is_conflict", False),
                        "raw_response": result.get("raw_response", ""),
                        "data": result,
                    }
                )

        record_ids = []
        if save_to_db and db_service and conflicts_to_save:
            record_ids = db_service.save_conflict_batch(
                session_id=session_id, conflicts=conflicts_to_save
            )

        return jsonify(
            {
                "success": True,
                "data": results,
                "record_ids": record_ids,
                "total": len(results),
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@conflict_bp.route("/latest", methods=["GET"])
def get_latest_conflict_batch():  # 已迁移到 backend_business/api/routers/conflict.py
    session_id = request.args.get("session_id")
    if not session_id:
        return jsonify({"success": False, "error": "缺少 session_id"}), 400
    if not db_service:
        return jsonify({"success": False, "error": "数据库服务未初始化"}), 500
    data = db_service.get_latest_conflict_batch(session_id)
    return jsonify({"success": True, "data": data})
