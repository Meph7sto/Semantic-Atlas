"""
需求相关路由
包含传统需求抽取和基于 EgoBundle 的 L1-L3 需求抽取
"""
import json
from typing import Any, Dict, List, Optional, Tuple

import requests
from flask import Blueprint, Response, jsonify, request, stream_with_context

from backend_business.config import settings
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.doors_store import DoorsStore
from backend_business.services.requirements_extraction_service import RequirementsExtractionService

requirements_bp = Blueprint("requirements", __name__)

# 初始化需求抽取服务
requirements_service = RequirementsExtractionService(dsn=settings.POSTGRES_DSN)


def _maybe_store_acquisition_result(
    payload: Dict[str, Any],
    result: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    将需求获取结果写入 MySQL（若 DOORS_DB_URL 未配置则跳过）。
    这里把：
    - artifact / extraction_run / candidate_requirement(+candidate_evidence) 作为审计底座
    - requirement_object / requirement_revision 作为正式对象库
    - module/module_object 用 L1/L2/L3 模块视图组织
    - evidence_link 通过 quote 绑定到 transcript_segment
    """
    if not settings.DOORS_DB_URL:
        return None

    project_name = (payload.get("project_name") or settings.DOORS_PROJECT_NAME or "default").strip()
    created_by = (payload.get("created_by") or "").strip() or None
    artifact_meta = payload.get("artifact") or {}
    artifact_type = (artifact_meta.get("type") or "text").strip() or "text"
    artifact_uri = artifact_meta.get("uri")
    artifact_metadata = artifact_meta.get("metadata") or {}

    store = DoorsStore(settings.DOORS_DB_URL)
    project_id = store.ensure_project(project_name)
    ws_id = store.create_workspace(project_id, scope_query={"stage": "acquisition"}, created_by=created_by)
    run_id = store.create_analysis_run(
        workspace_id=ws_id,
        stage="acquisition",
        config={
            "clean_model": payload.get("clean_model"),
            "extract_model": payload.get("extract_model"),
            "chunk_size": payload.get("chunk_size"),
            "overlap": payload.get("overlap"),
        },
        status="success",
    )

    artifact_id = store.create_artifact(
        project_id=project_id,
        artifact_type=artifact_type,
        uri=artifact_uri,
        metadata=artifact_metadata,
    )
    extraction_run_id = store.create_extraction_run(
        artifact_id=artifact_id,
        model=str(payload.get("extract_model") or "unknown"),
        prompt_version=None,
        status="success",
        config={"stage": "acquisition"},
    )

    # Modules
    m_business = store.ensure_module(project_id, "L1 业务需求", "需求获取：业务/使命需求")
    m_stakeholder = store.ensure_module(project_id, "L2 利益相关者需求", "需求获取：利益相关者需求")
    m_system = store.ensure_module(project_id, "L3 系统需求", "需求获取：系统需求")

    def _items(key: str) -> List[Dict[str, Any]]:
        xs = result.get(key) or []
        return xs if isinstance(xs, list) else []

    inserted: List[Dict[str, Any]] = []

    def _handle_group(items: List[Dict[str, Any]], obj_type: str, module_id: str) -> None:
        pos = 0
        for it in items:
            statement = (it.get("statement") or "").strip()
            if not statement:
                continue
            pos += 1
            confidence = it.get("confidence")
            evidence = str(it.get("evidence") or "").strip()

            # candidate + candidate_evidence
            cand_id = store.create_candidate_requirement(
                extraction_run_id=extraction_run_id,
                text_body=statement,
                confidence=float(confidence) if confidence is not None else None,
                suggested_type=obj_type,
                metadata={"rationale": it.get("rationale")},
            )
            seg_id = ""
            if evidence:
                # 复用 transcript_segment（quote 作为 segment 文本）
                with store.SessionLocal() as db:
                    seg_id = store._ensure_transcript_segment_by_quote(db, artifact_id, evidence)  # type: ignore[attr-defined]
                    db.commit()
                if seg_id:
                    store.link_candidate_evidence(cand_id, seg_id, score=float(confidence) if confidence is not None else None)

            # requirement object + revision + evidence_link
            imported = store.upsert_requirement(
                project_id=project_id,
                object_type=obj_type,
                text_body=statement,
                rationale=(it.get("rationale") or None),
                status="Proposed",
                source_kind="extracted",
                created_by=created_by,
                quality_metrics={"confidence": confidence, "run_id": run_id},
                artifact_id_for_evidence=artifact_id,
                evidence_quotes=[(evidence, float(confidence) if confidence is not None else None)],
            )
            store.add_object_to_module(module_id, imported.object_id, position=pos, outline_level=1)
            inserted.append(
                {
                    "object_id": imported.object_id,
                    "revision_id": imported.revision_id,
                    "module_id": module_id,
                    "candidate_id": cand_id,
                }
            )

    _handle_group(_items("business_requirements"), "business", m_business)
    _handle_group(_items("stakeholder_requirements"), "stakeholder", m_stakeholder)
    _handle_group(_items("system_requirements"), "system", m_system)

    return {
        "project_id": project_id,
        "workspace_id": ws_id,
        "analysis_run_id": run_id,
        "artifact_id": artifact_id,
        "extraction_run_id": extraction_run_id,
        "count": len(inserted),
        "imported": inserted,
    }


@requirements_bp.post("/requirements/extract")
def extract_requirements():
    """传统需求抽取接口（保持向后兼容）"""
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400
    
    text = data["text"]
    chunk_size = data.get("chunk_size", 3600)
    overlap = data.get("overlap", 500)
    clean_model = data.get("clean_model", "deepseek-chat")
    extract_model = data.get("extract_model", "deepseek-reasoner")
    
    try:
        result = ai_proxy.extract_requirements(
            text, 
            chunk_size, 
            overlap, 
            clean_model=clean_model, 
            extract_model=extract_model
        )
        stored = _maybe_store_acquisition_result(
            {
                **(data or {}),
                "chunk_size": chunk_size,
                "overlap": overlap,
                "clean_model": clean_model,
                "extract_model": extract_model,
            },
            result,
        )
        return jsonify({"success": True, "data": result, "doors": stored})
    except Exception as e:
        # Proxy or backend error
        return jsonify({"success": False, "error": str(e)}), 500


@requirements_bp.post("/requirements/extract/stream")
def extract_requirements_stream():
    """
    代理推理后端的 SSE：
    - 前端可以继续实时显示进度
    - 当收到 event=result 时，自动把结果落入 MySQL
    """
    data = request.get_json(silent=True) or {}
    if "text" not in data:
        return jsonify({"success": False, "error": "Missing 'text' field"}), 400

    base_url = settings.INFERENCE_BASE_URL.rstrip("/")
    url = f"{base_url}/acquisition/extract/stream"

    # NOTE: requests 代理 streaming，Flask 使用 Response(stream_with_context(...))
    upstream = requests.post(url, json=data, stream=True, timeout=900)

    if upstream.status_code != 200:
        return jsonify({"success": False, "error": upstream.text}), upstream.status_code

    def _iter_events():
        buf: List[str] = []
        event_name = "message"

        def _flush_block(block_lines: List[str]) -> Optional[Tuple[str, str]]:
            if not block_lines:
                return None
            event = "message"
            payload = ""
            for line in block_lines:
                if line.startswith("event:"):
                    event = line[len("event:"):].strip() or "message"
                elif line.startswith("data:"):
                    payload += line[len("data:"):].strip()
            return event, payload

        for raw in upstream.iter_lines(decode_unicode=True):
            if raw is None:
                continue
            line = str(raw)
            # SSE block separator
            if line == "":
                parsed = _flush_block(buf)
                buf = []
                if not parsed:
                    yield "\n"
                    continue
                ev, payload = parsed
                # 落库：仅处理 result
                if ev == "result":
                    try:
                        result_obj = json.loads(payload) if payload else {}
                        _maybe_store_acquisition_result(data, result_obj)
                    except Exception:
                        # 落库失败不影响前端显示
                        pass
                # 原样透传
                yield f"event: {ev}\n"
                yield f"data: {payload}\n\n"
                continue
            buf.append(line)

    return Response(stream_with_context(_iter_events()), mimetype="text/event-stream")


@requirements_bp.post("/requirements/extract_l123")
def extract_l123_requirements():
    """
    L1-L3 需求抽取接口
    基于 EgoBundle 和 toolcall 机制
    """
    data = request.get_json()
    if not data or "session_id" not in data:
        return jsonify({"error": "Missing 'session_id' field"}), 400

    session_id = data["session_id"]
    context_run_id = data.get("context_run_id")
    bundle_strategy = data.get("bundle_strategy", "sequence")  # sequence | graph
    anchor_strategy = data.get("anchor_strategy", "informative")  # all | keyword | informative
    r = data.get("r", 2)
    model_name = data.get("model", "deepseek-chat")
    use_toolcall = bool(data.get("use_toolcall", True))
    adaptive_retry_r2 = bool(data.get("adaptive_retry_r2", False))
    max_spans_per_bundle = data.get("max_spans_per_bundle")
    token_limit = data.get("token_limit")
    top_m_2hop = data.get("top_m_2hop")
    keywords = data.get("keywords")

    try:
        result = requirements_service.extract_requirements_for_session(
            session_id=session_id,
            context_run_id=context_run_id,
            bundle_strategy=bundle_strategy,
            anchor_strategy=anchor_strategy,
            r=r,
            model_name=model_name,
            use_toolcall=use_toolcall,
            adaptive_retry_r2=adaptive_retry_r2,
            max_spans_per_bundle=max_spans_per_bundle,
            token_limit=token_limit,
            top_m_2hop=top_m_2hop,
            keywords=keywords,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@requirements_bp.get("/requirements/session/<session_id>")
def get_requirements_by_session(session_id: str):
    """
    查询指定 session 的需求列表
    支持按层级过滤和分页
    """
    level = request.args.get("level")  # L1 | L2 | L3
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 50))

    try:
        result = requirements_service.get_requirements_by_session(
            session_id=session_id,
            level=level,
            page=page,
            per_page=per_page,
        )
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@requirements_bp.get("/requirements/<req_id>")
def get_requirement_detail(req_id: str):
    """获取需求详情"""
    try:
        requirement = requirements_service.get_requirement_detail(req_id)
        if not requirement:
            return jsonify({"error": "Requirement not found"}), 404
        return jsonify(requirement)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@requirements_bp.delete("/requirements/<req_id>")
def delete_requirement(req_id: str):
    """删除需求"""
    try:
        deleted = requirements_service.delete_requirement(req_id)
        if not deleted:
            return jsonify({"error": "Requirement not found"}), 404
        return jsonify({"message": "Requirement deleted successfully"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@requirements_bp.get("/requirements/stats")
def get_requirements_stats():
    """
    获取需求统计信息
    可选参数：session_id（统计指定会话的需求）
    """
    session_id = request.args.get("session_id")

    try:
        stats = requirements_service.get_statistics(session_id)
        return jsonify(stats)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
