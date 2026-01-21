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
from backend_business.services.requirements_extraction_service import RequirementsExtractionService

requirements_bp = Blueprint("requirements", __name__)

# 初始化需求抽取服务
requirements_service = RequirementsExtractionService(dsn=settings.POSTGRES_DSN)


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
        return jsonify({"success": True, "data": result})
    except Exception as e:
        # Proxy or backend error
        return jsonify({"success": False, "error": str(e)}), 500


@requirements_bp.post("/requirements/extract/stream")
def extract_requirements_stream():
    """
    代理推理后端的 SSE 流式需求抽取
    """
    data = request.get_json(silent=True) or {}
    if "text" not in data:
        return jsonify({"success": False, "error": "Missing 'text' field"}), 400

    base_url = settings.INFERENCE_BASE_URL.rstrip("/")
    url = f"{base_url}/acquisition/extract/stream"

    upstream = requests.post(url, json=data, stream=True, timeout=900)

    if upstream.status_code != 200:
        return jsonify({"success": False, "error": upstream.text}), upstream.status_code

    def _iter_events():
        buf: List[str] = []

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
            if line == "":
                parsed = _flush_block(buf)
                buf = []
                if not parsed:
                    yield "\n"
                    continue
                ev, payload = parsed
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
