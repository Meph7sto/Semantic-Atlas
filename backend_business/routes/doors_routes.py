from __future__ import annotations

from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from backend_business.config import settings
from backend_business.services.doors_store import DoorsStore


doors_bp = Blueprint("doors", __name__)


def _get_store() -> DoorsStore:
    if not settings.DOORS_DB_URL:
        raise RuntimeError("DOORS_DB_URL 未配置，无法启用 MySQL 对象库")
    return DoorsStore(settings.DOORS_DB_URL)


@doors_bp.get("/health")
def health():
    """
    简单健康检查：验证 DOORS_DB_URL 是否可用。
    """
    try:
        store = _get_store()
        # 轻量触发连接
        pid = store.ensure_project(settings.DOORS_PROJECT_NAME)
        return jsonify({"success": True, "data": {"status": "ok", "project_id": pid}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@doors_bp.post("/import-acquisition")
def import_acquisition():
    """
    将“需求获取(抽取)”结果落入 DOORS 风格库：
    - requirement_object + requirement_revision
    - module/module_object（按 L1/L2/L3 组织）
    - artifact/transcript_segment/evidence_link（把 evidence 字段当作 quote 证据）

    请求体示例：
    {
      "project_name": "demo",
      "artifact": {"type":"text","uri":null,"metadata":{"source":"manual"}},
      "result": {
        "business_requirements":[{"statement":"...","rationale":"...","evidence":"...","confidence":0.8}],
        "stakeholder_requirements":[...],
        "system_requirements":[...]
      },
      "created_by": "alice"
    }
    """
    payload = request.get_json(silent=True) or {}
    project_name = (payload.get("project_name") or settings.DOORS_PROJECT_NAME or "default").strip()
    created_by = (payload.get("created_by") or "").strip() or None
    artifact = payload.get("artifact") or {}
    result = payload.get("result") or payload  # 兼容直接传推理返回

    try:
        store = _get_store()
        project_id = store.ensure_project(project_name)
        artifact_id = store.create_artifact(
            project_id=project_id,
            artifact_type=(artifact.get("type") or "text"),
            uri=artifact.get("uri"),
            metadata=artifact.get("metadata") or {},
        )

        # 模块（视图）
        m_business = store.ensure_module(project_id, "L1 业务需求", "需求获取：业务/使命需求")
        m_stakeholder = store.ensure_module(project_id, "L2 利益相关者需求", "需求获取：利益相关者需求")
        m_system = store.ensure_module(project_id, "L3 系统需求", "需求获取：系统需求")

        def _as_list(key: str) -> List[Dict[str, Any]]:
            xs = result.get(key) or []
            return xs if isinstance(xs, list) else []

        inserted: List[Dict[str, Any]] = []
        pos = 0

        for item in _as_list("business_requirements"):
            pos += 1
            statement = (item.get("statement") or "").strip()
            if not statement:
                continue
            obj = store.upsert_requirement(
                project_id=project_id,
                object_type="business",
                text_body=statement,
                rationale=(item.get("rationale") or None),
                status="Proposed",
                source_kind="extracted",
                created_by=created_by,
                quality_metrics={"confidence": item.get("confidence")},
                artifact_id_for_evidence=artifact_id,
                evidence_quotes=[(str(item.get("evidence") or ""), float(item.get("confidence") or 0.0))],
            )
            store.add_object_to_module(m_business, obj.object_id, position=pos, outline_level=1)
            inserted.append({"object_id": obj.object_id, "revision_id": obj.revision_id, "module": "L1 业务需求"})

        pos = 0
        for item in _as_list("stakeholder_requirements"):
            pos += 1
            statement = (item.get("statement") or "").strip()
            if not statement:
                continue
            obj = store.upsert_requirement(
                project_id=project_id,
                object_type="stakeholder",
                text_body=statement,
                rationale=(item.get("rationale") or None),
                status="Proposed",
                source_kind="extracted",
                created_by=created_by,
                quality_metrics={"confidence": item.get("confidence")},
                artifact_id_for_evidence=artifact_id,
                evidence_quotes=[(str(item.get("evidence") or ""), float(item.get("confidence") or 0.0))],
            )
            store.add_object_to_module(m_stakeholder, obj.object_id, position=pos, outline_level=1)
            inserted.append({"object_id": obj.object_id, "revision_id": obj.revision_id, "module": "L2 利益相关者需求"})

        pos = 0
        for item in _as_list("system_requirements"):
            pos += 1
            statement = (item.get("statement") or "").strip()
            if not statement:
                continue
            obj = store.upsert_requirement(
                project_id=project_id,
                object_type="system",
                text_body=statement,
                rationale=(item.get("rationale") or None),
                status="Proposed",
                source_kind="extracted",
                created_by=created_by,
                quality_metrics={"confidence": item.get("confidence")},
                artifact_id_for_evidence=artifact_id,
                evidence_quotes=[(str(item.get("evidence") or ""), float(item.get("confidence") or 0.0))],
            )
            store.add_object_to_module(m_system, obj.object_id, position=pos, outline_level=1)
            inserted.append({"object_id": obj.object_id, "revision_id": obj.revision_id, "module": "L3 系统需求"})

        return jsonify(
            {
                "success": True,
                "data": {
                    "project_id": project_id,
                    "artifact_id": artifact_id,
                    "imported": inserted,
                    "count": len(inserted),
                },
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@doors_bp.get("/links")
def list_links():
    """
    列出待验收的 link_revision（默认 proposed）。
    GET /api/doors/links?project_name=default&status=proposed&limit=50
    """
    project_name = (request.args.get("project_name") or settings.DOORS_PROJECT_NAME or "default").strip()
    status = (request.args.get("status") or "proposed").strip()
    limit = int(request.args.get("limit") or 50)
    try:
        store = _get_store()
        project_id = store.ensure_project(project_name)
        items = store.list_link_revisions(project_id=project_id, status=status, limit=limit)
        return jsonify({"success": True, "data": {"project_id": project_id, "items": items}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@doors_bp.post("/links/<link_id>/validate")
def validate_link(link_id: str):
    """
    验收/驳回一条 link（通过创建新的 link_revision 实现审计可追溯）。
    POST /api/doors/links/{link_id}/validate
    {
      "validation_status": "accepted|rejected|needs_review",
      "validation_by": "alice",
      "comment": "reason..."
    }
    """
    payload = request.get_json(silent=True) or {}
    validation_status = (payload.get("validation_status") or "").strip()
    validation_by = (payload.get("validation_by") or "").strip() or None
    comment = payload.get("comment")
    try:
        store = _get_store()
        out = store.validate_link_revision(
            link_id=link_id,
            validation_status=validation_status,
            validation_by=validation_by,
            comment=comment,
        )
        return jsonify({"success": True, "data": out})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


