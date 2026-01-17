from flask import Blueprint, request, jsonify

from backend_business.services.ai_proxy import ai_proxy
from backend_business.config import settings
from backend_business.services.doors_store import DoorsStore

# 创建一个 Blueprint (蓝图)，用于组织冲突检测相关的路由
conflict_bp = Blueprint('conflict', __name__)

def _maybe_store_conflict(payload: dict, result: dict) -> dict | None:
    if not settings.DOORS_DB_URL:
        return None
    project_name = (payload.get("project_name") or settings.DOORS_PROJECT_NAME or "default").strip()
    created_by = (payload.get("created_by") or "").strip() or None

    store = DoorsStore(settings.DOORS_DB_URL)
    project_id = store.ensure_project(project_name)
    ws_id = store.create_workspace(project_id, scope_query={"stage": "conflict"}, created_by=created_by)
    run_id = store.create_analysis_run(workspace_id=ws_id, stage="conflict", config={}, status="success")

    req_a = (payload.get("requirement_a") or "").strip()
    req_b = (payload.get("requirement_b") or "").strip()

    a_obj = store.upsert_requirement(
        project_id=project_id,
        object_type="system",
        text_body=req_a,
        status="Proposed",
        source_kind="manual",
        created_by=created_by,
        quality_metrics={"source": "conflict_input", "run_id": run_id},
    )
    b_obj = store.upsert_requirement(
        project_id=project_id,
        object_type="system",
        text_body=req_b,
        status="Proposed",
        source_kind="manual",
        created_by=created_by,
        quality_metrics={"source": "conflict_input", "run_id": run_id},
    )

    finding_id = store.insert_conflict_finding(
        run_id=run_id,
        object_a_id=a_obj.object_id,
        object_b_id=b_obj.object_id,
        explanation=str(result.get("raw_response") or ""),
        conflict_type="logical",
        severity="high" if result.get("is_conflict") else "none",
        status="open",
    )
    return {"project_id": project_id, "workspace_id": ws_id, "analysis_run_id": run_id, "conflict_finding_id": finding_id}


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
        doors = _maybe_store_conflict(payload, result)
        # 统一响应结构，record_id 为 None（冲突检测暂不持久化）
        return jsonify({"success": True, "data": result, "record_id": None, "doors": doors})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
