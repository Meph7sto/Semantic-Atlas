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
from backend_business.services.requirements_extraction import (
    RequirementsExtractionService,
)
from backend_business.services.requirements_deduplication import (
    RequirementsDeduplicationService,
)

requirements_bp = Blueprint("requirements", __name__)

# 初始化需求抽取服务
requirements_service = RequirementsExtractionService(dsn=settings.POSTGRES_DSN)
dedup_service = RequirementsDeduplicationService(dsn=settings.POSTGRES_DSN)


def _parse_bool(value: Any, default: bool = False) -> bool:
    """Parse common bool-like inputs from JSON payloads."""
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            return True
        if lowered in {"0", "false", "no", "n", "off", ""}:
            return False
    return bool(value)


def _parse_optional_bool(value: Any):
    """Parse bool-like input and preserve None when missing."""
    if value is None:
        return None
    return _parse_bool(value, default=False)


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
            extract_model=extract_model,
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
                    event = line[len("event:") :].strip() or "message"
                elif line.startswith("data:"):
                    payload += line[len("data:") :].strip()
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
    anchor_strategy = data.get(
        "anchor_strategy", "informative"
    )  # all | keyword | informative
    r = data.get("r", 2)
    model_name = data.get("model", "deepseek-chat")
    use_toolcall = _parse_bool(data.get("use_toolcall"), default=True)
    adaptive_retry_r2 = _parse_optional_bool(data.get("adaptive_retry_r2"))
    max_spans_per_bundle = data.get("max_spans_per_bundle")
    token_limit = data.get("token_limit")
    top_m_2hop = data.get("top_m_2hop")
    keywords = data.get("keywords")
    history_aware = _parse_bool(data.get("history_aware"), default=False)
    reset_before_extract = _parse_bool(data.get("reset_before_extract"), default=True)

    # Optional: post extraction dedup
    post_dedup = _parse_bool(data.get("post_dedup"), default=False)
    dedup_with_llm = _parse_bool(data.get("dedup_with_llm"), default=False)
    dedup_auto_merge = _parse_bool(data.get("dedup_auto_merge"), default=False)
    dedup_threshold = data.get("dedup_threshold")
    try:
        dedup_max_concurrent = int(data.get("dedup_max_concurrent", 5))
    except (TypeError, ValueError):
        dedup_max_concurrent = 5
    dedup_max_concurrent = max(1, min(10, dedup_max_concurrent))

    # 可选并发参数（与 Phase 2 保持一致的命名）
    enable_parallel = _parse_bool(data.get("enable_parallel_windows"), default=False)
    try:
        max_concurrent = int(data.get("max_concurrent_windows", 5))
    except (TypeError, ValueError):
        max_concurrent = 5
    max_concurrent = max(1, min(10, max_concurrent))

    try:
        cleared_before_extract = 0
        if reset_before_extract:
            cleared_before_extract = (
                requirements_service.clear_requirements_for_session(session_id)
            )

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
            enable_parallel=enable_parallel,
            max_concurrent=max_concurrent,
            history_aware=history_aware,
        )

        if post_dedup:
            # Use per-request threshold if provided
            service = dedup_service
            if dedup_threshold is not None:
                service = RequirementsDeduplicationService(
                    dsn=settings.POSTGRES_DSN,
                    similarity_threshold=float(dedup_threshold),
                    default_model=model_name,
                )

            dedup_result = service.detect_duplicates(
                session_id=session_id,
                level=None,
                with_llm_decision=dedup_with_llm,
                auto_merge=dedup_auto_merge,
                model_name=model_name,
                max_concurrent=dedup_max_concurrent,
            )
            result["deduplication"] = dedup_result
        result["cleared_before_extract"] = cleared_before_extract
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@requirements_bp.post("/requirements/extract_l123/stream")
def extract_l123_requirements_stream():
    """
    L1-L3 需求抽取流式接口
    支持并发处理和实时进度反馈
    """
    data = request.get_json()
    if not data or "session_id" not in data:
        return jsonify({"error": "Missing 'session_id' field"}), 400

    session_id = data["session_id"]
    context_run_id = data.get("context_run_id")
    bundle_strategy = data.get("bundle_strategy", "sequence")
    anchor_strategy = data.get("anchor_strategy", "informative")
    r = data.get("r", 2)
    model_name = data.get("model", "deepseek-chat")
    use_toolcall = _parse_bool(data.get("use_toolcall"), default=True)
    adaptive_retry_r2 = _parse_optional_bool(data.get("adaptive_retry_r2"))
    max_spans_per_bundle = data.get("max_spans_per_bundle")
    token_limit = data.get("token_limit")
    top_m_2hop = data.get("top_m_2hop")
    keywords = data.get("keywords")
    history_aware = _parse_bool(data.get("history_aware"), default=False)
    reset_before_extract = _parse_bool(data.get("reset_before_extract"), default=True)

    # Optional: post extraction dedup
    post_dedup = _parse_bool(data.get("post_dedup"), default=False)
    dedup_with_llm = _parse_bool(data.get("dedup_with_llm"), default=False)
    dedup_auto_merge = _parse_bool(data.get("dedup_auto_merge"), default=False)
    dedup_threshold = data.get("dedup_threshold")
    try:
        dedup_max_concurrent = int(data.get("dedup_max_concurrent", 5))
    except (TypeError, ValueError):
        dedup_max_concurrent = 5
    dedup_max_concurrent = max(1, min(10, dedup_max_concurrent))

    # 并发参数（复用 Phase 2 的参数名）
    enable_parallel = _parse_bool(data.get("enable_parallel_windows"), default=False)
    try:
        max_concurrent = int(data.get("max_concurrent_windows", 5))
    except (TypeError, ValueError):
        max_concurrent = 5
    max_concurrent = max(1, min(10, max_concurrent))

    try:
        cleared_before_extract = 0
        if reset_before_extract:
            cleared_before_extract = (
                requirements_service.clear_requirements_for_session(session_id)
            )
    except Exception as e:
        return jsonify({"error": str(e)}), 500

    def _generate_events():
        try:
            yield f"event: reset\n"
            yield (
                f"data: {json.dumps({'cleared_before_extract': cleared_before_extract})}\n\n"
            )

            for (
                event_dict
            ) in requirements_service.extract_requirements_for_session_stream(
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
                enable_parallel=enable_parallel,
                max_concurrent=max_concurrent,
                history_aware=history_aware,
            ):
                event_name = event_dict.get("event", "message")
                event_data = event_dict.get("data", {})

                yield f"event: {event_name}\n"
                yield f"data: {json.dumps(event_data)}\n\n"

            # Run dedup after stream completes successfully
            if post_dedup:
                yield "event: dedup_start\n"
                yield f"data: {json.dumps({'session_id': session_id})}\n\n"

                service = dedup_service
                if dedup_threshold is not None:
                    service = RequirementsDeduplicationService(
                        dsn=settings.POSTGRES_DSN,
                        similarity_threshold=float(dedup_threshold),
                        default_model=model_name,
                    )

                dedup_result = service.detect_duplicates(
                    session_id=session_id,
                    level=None,
                    with_llm_decision=dedup_with_llm,
                    auto_merge=dedup_auto_merge,
                    model_name=model_name,
                    max_concurrent=dedup_max_concurrent,
                )

                yield "event: dedup_final\n"
                yield f"data: {json.dumps(dedup_result)}\n\n"
        except Exception as e:
            yield f"event: error\n"
            yield f"data: {json.dumps({'message': str(e)})}\n\n"

    return Response(
        stream_with_context(_generate_events()), mimetype="text/event-stream"
    )


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


# ========================
# L4 底层需求相关 API
# ========================

from backend_business.services.db_service import db_service


@requirements_bp.get("/requirements/l4/<session_id>")
def get_l4_requirements(session_id: str):
    """
    查询指定 session 的 L4 底层需求

    如果数据库中有缓存，直接返回；否则返回空列表
    """
    page = int(request.args.get("page", 1))
    per_page = int(request.args.get("per_page", 100))

    try:
        result = db_service.get_l4_requirements_by_session(
            session_id=session_id,
            page=page,
            per_page=per_page,
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@requirements_bp.get("/requirements/l4/<session_id>/exists")
def check_l4_exists(session_id: str):
    """检查指定 session 是否有 L4 底层需求缓存"""
    try:
        exists = db_service.has_l4_requirements(session_id)
        return jsonify({"success": True, "exists": exists})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@requirements_bp.post("/requirements/l4/generate")
def generate_l4_requirements():
    """
    生成 L4 底层需求

    流程：
    1. 检查数据库是否有缓存
    2. 如有缓存，直接返回
    3. 如无缓存，调用推理后端生成，然后保存到数据库

    请求体：
    {
        "session_id": "xxx",
        "requirements": [{"id": "...", "text": "..."}],
        "config": {...},  // 可选
        "model": "deepseek-chat",  // 可选
        "force_regenerate": false  // 可选，是否强制重新生成
    }
    """
    data = request.get_json() or {}
    session_id = data.get("session_id")
    requirements = data.get("requirements", [])
    config = data.get("config", {})
    model = data.get("model")
    force_regenerate = bool(data.get("force_regenerate", False))

    if not session_id:
        return jsonify({"success": False, "error": "Missing 'session_id'"}), 400
    if not requirements:
        return jsonify({"success": False, "error": "Missing 'requirements'"}), 400

    try:
        requested_ids = [r.get("id") for r in requirements if r.get("id")]
        if not requested_ids:
            return jsonify(
                {"success": False, "error": "所有顶层需求必须包含 'id' 字段"}
            ), 400

        # 检查缓存（按本次请求的顶层需求范围）
        if not force_regenerate:
            existing_ids = db_service.get_existing_top_req_ids(
                session_id, requested_ids
            )
            missing_ids = [rid for rid in requested_ids if rid not in set(existing_ids)]

            # 如果所有都有缓存，直接返回
            if not missing_ids:
                cached = db_service.get_l4_requirements_by_session(
                    session_id,
                    per_page=500,
                    top_req_ids=requested_ids,
                )
                return jsonify(
                    {
                        "success": True,
                        "from_cache": True,
                        "requirements": cached.get("requirements", []),
                        "total": cached.get("total", 0),
                    }
                )

            # 只对缺失的顶层需求生成
            requirements = [r for r in requirements if r.get("id") in set(missing_ids)]

        # 调用推理后端生成 L4（只生成缺失的）
        if not requirements:
            return jsonify({"success": False, "error": "没有需要生成的需求"}), 400

        payload = {
            "requirements": requirements,
            "config": config,
        }
        if model:
            payload["model"] = model

        resp = requests.post(
            f"{settings.INFERENCE_BASE_URL}/l4/generate",
            json=payload,
            timeout=600,  # L4 生成可能较慢
        )
        resp.raise_for_status()
        resp_data = resp.json()

        # 解析结果并保存到数据库
        all_l4_reqs = []
        for result in resp_data.get("results", []):
            source_top_id = result.get("source_top_id", "")
            # 找到对应的顶层需求文本
            source_top_text = ""
            for req in requirements:
                if req.get("id") == source_top_id:
                    source_top_text = req.get("text", "")
                    break

            for l4 in result.get("l4_requirements", []):
                l4["source_top_id"] = source_top_id
                l4["source_top_text"] = source_top_text
                l4["source_top_ids"] = [source_top_id] if source_top_id else []
                all_l4_reqs.append(l4)

        # 保存到数据库（带去重）
        save_result = {"inserted": 0, "duplicates": 0, "inserted_ids": []}
        if all_l4_reqs:
            save_result = db_service.save_l4_requirements(session_id, all_l4_reqs)

        # 重新查询以返回完整数据（包含缓存的+新生成的）
        saved = db_service.get_l4_requirements_by_session(
            session_id,
            per_page=500,
            top_req_ids=requested_ids,
        )

        return jsonify(
            {
                "success": True,
                "from_cache": False,
                "requirements": saved.get("requirements", []),
                "total": saved.get("total", 0),
                "inserted_count": save_result.get("inserted", 0),
                "duplicates_skipped": save_result.get("duplicates", 0),
                "kb_version": resp_data.get("kb_version", ""),
                "model_id": resp_data.get("model_id", ""),
                "missing_top_ids": missing_ids if "missing_ids" in locals() else [],
            }
        )

    except requests.exceptions.RequestException as e:
        return jsonify({"success": False, "error": f"推理后端调用失败: {str(e)}"}), 500
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
