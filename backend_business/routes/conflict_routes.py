from flask import Blueprint, request, jsonify

from backend_business.services.ai_proxy import ai_proxy

# 创建一个 Blueprint (蓝图)，用于组织冲突检测相关的路由
conflict_bp = Blueprint('conflict', __name__)


@conflict_bp.route('/check', methods=['POST'])
def check_conflict():
    """
    检查冲突接口
    通过 ai_proxy 服务代理请求到推理后端 (Inference Backend)
    响应格式与追溯接口保持一致：{success, data, record_id}
    """
    payload = request.get_json(silent=True) or {}
    requirement_a = (payload.get("requirement_a") or "").strip()
    requirement_b = (payload.get("requirement_b") or "").strip()

    if not requirement_a or not requirement_b:
        return jsonify({"success": False, "error": "请提供 requirement_a 与 requirement_b"}), 400

    try:
        result = ai_proxy.conflict_check(requirement_a, requirement_b)
        # 统一响应结构，record_id 为 None（冲突检测暂不持久化）
        return jsonify({"success": True, "data": result, "record_id": None})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
