"""
需求管理路由 - FastAPI 版本
对应历史蓝图: requirements_bp (url_prefix="/api/v2")
"""

import json
from collections.abc import Generator
from typing import Any, Literal, cast

import requests
from fastapi import APIRouter, Query

from backend_business.api.http.errors import ErrorResponse
from backend_business.api.http.sse import sse_response_raw
from backend_business.api.routers.schemas.requirements_schemas import (
    ExtractL123Request,
    ExtractRequirementsRequest,
    GenerateL4RequirementsRequest,
)
from backend_business.config import settings
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service
from backend_business.services.requirements_deduplication import (
    RequirementsDeduplicationService,
)
from backend_business.services.requirements_extraction import (
    RequirementsExtractionService,
)

router = APIRouter(prefix="/api/v2", tags=["requirements"])

requirements_service = RequirementsExtractionService(dsn=settings.POSTGRES_DSN)
dedup_service = RequirementsDeduplicationService(dsn=settings.POSTGRES_DSN)


def _sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _non_empty_path_param(value: str, field_name: str) -> str:
    text = (value or "").strip()
    if not text:
        raise ErrorResponse(f"{field_name} 不能为空", 400)
    return text


def _get_db_service():
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)
    return db_service


def _dedup_service_for_request(
    threshold: float | None,
    model_name: str,
) -> RequirementsDeduplicationService:
    if threshold is None:
        return dedup_service
    return RequirementsDeduplicationService(
        dsn=settings.POSTGRES_DSN,
        similarity_threshold=float(threshold),
        default_model=model_name,
    )


@router.post("/requirements/extract")
def extract_requirements(req: ExtractRequirementsRequest):
    """
    传统需求抽取接口
    """
    try:
        result = ai_proxy.extract_requirements(
            req.text,
            req.chunk_size,
            req.overlap,
            clean_model=req.clean_model,
            extract_model=req.extract_model,
        )
        return result
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/requirements/extract_l123")
def extract_l123_requirements(req: ExtractL123Request):
    """
    L1-L3 需求抽取接口
    """
    try:
        cleared_before_extract = 0
        if req.reset_before_extract:
            cleared_before_extract = (
                requirements_service.clear_requirements_for_session(req.session_id)
            )

        result = requirements_service.extract_requirements_for_session(
            session_id=req.session_id,
            context_run_id=req.context_run_id,
            bundle_strategy=req.bundle_strategy,
            anchor_strategy=req.anchor_strategy,
            r=req.r,
            model_name=req.model,
            use_toolcall=req.use_toolcall,
            adaptive_retry_r2=req.adaptive_retry_r2,
            max_spans_per_bundle=req.max_spans_per_bundle,
            token_limit=req.token_limit,
            top_m_2hop=req.top_m_2hop,
            keywords=req.keywords,
            enable_parallel=req.enable_parallel_windows,
            max_concurrent=req.max_concurrent_windows,
            history_aware=req.history_aware,
        )

        if req.post_dedup:
            service = _dedup_service_for_request(req.dedup_threshold, req.model)
            dedup_result = service.detect_duplicates(
                session_id=req.session_id,
                level=None,
                with_llm_decision=req.dedup_with_llm,
                auto_merge=req.dedup_auto_merge,
                model_name=req.model,
                max_concurrent=req.dedup_max_concurrent,
            )
            result["deduplication"] = dedup_result

        result["cleared_before_extract"] = cleared_before_extract
        return result
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/requirements/extract_l123/stream")
def extract_l123_requirements_stream(req: ExtractL123Request):
    """
    L1-L3 需求抽取流式接口
    """
    try:
        cleared_before_extract = 0
        if req.reset_before_extract:
            cleared_before_extract = (
                requirements_service.clear_requirements_for_session(req.session_id)
            )
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)

    def generate() -> Generator[str, None, None]:
        yield _sse_event("reset", {"cleared_before_extract": cleared_before_extract})

        try:
            for (
                event_dict
            ) in requirements_service.extract_requirements_for_session_stream(
                session_id=req.session_id,
                context_run_id=req.context_run_id,
                bundle_strategy=req.bundle_strategy,
                anchor_strategy=req.anchor_strategy,
                r=req.r,
                model_name=req.model,
                use_toolcall=req.use_toolcall,
                adaptive_retry_r2=req.adaptive_retry_r2,
                max_spans_per_bundle=req.max_spans_per_bundle,
                token_limit=req.token_limit,
                top_m_2hop=req.top_m_2hop,
                keywords=req.keywords,
                enable_parallel=req.enable_parallel_windows,
                max_concurrent=req.max_concurrent_windows,
                history_aware=req.history_aware,
            ):
                event_name = str(event_dict.get("event", "message"))
                event_data = event_dict.get("data", {})
                yield _sse_event(event_name, event_data)

            if req.post_dedup:
                yield _sse_event("dedup_start", {"session_id": req.session_id})
                service = _dedup_service_for_request(req.dedup_threshold, req.model)
                dedup_result = service.detect_duplicates(
                    session_id=req.session_id,
                    level=None,
                    with_llm_decision=req.dedup_with_llm,
                    auto_merge=req.dedup_auto_merge,
                    model_name=req.model,
                    max_concurrent=req.dedup_max_concurrent,
                )
                yield _sse_event("dedup_final", dedup_result)

        except Exception as exc:
            yield _sse_event("error", {"message": str(exc)})

    return sse_response_raw(generate())


@router.get("/requirements/session/{session_id}")
def get_requirements_by_session(
    session_id: str,
    level: Literal["L1", "L2", "L3"] | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=50, ge=1),
):
    """
    查询指定 session 的需求列表
    """
    normalized_session_id = _non_empty_path_param(session_id, "session_id")

    try:
        result = requirements_service.get_requirements_by_session(
            session_id=normalized_session_id,
            level=level,
            page=page,
            per_page=per_page,
        )
        return result
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/requirements/stats")
def get_requirements_stats(session_id: str | None = Query(default=None)):
    """
    获取需求统计信息
    """
    normalized_session_id = session_id.strip() if session_id else None
    if normalized_session_id == "":
        normalized_session_id = None

    try:
        return requirements_service.get_statistics(normalized_session_id)
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/requirements/{req_id}")
def get_requirement_detail(req_id: str):
    """
    获取需求详情
    """
    normalized_req_id = _non_empty_path_param(req_id, "req_id")

    try:
        requirement = requirements_service.get_requirement_detail(normalized_req_id)
        if not requirement:
            raise ErrorResponse("Requirement not found", 404)
        return requirement
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.delete("/requirements/{req_id}")
def delete_requirement(req_id: str):
    """
    删除需求
    """
    normalized_req_id = _non_empty_path_param(req_id, "req_id")

    try:
        deleted = requirements_service.delete_requirement(normalized_req_id)
        if not deleted:
            raise ErrorResponse("Requirement not found", 404)
        return {"message": "Requirement deleted successfully"}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/requirements/l4/{session_id}")
def get_l4_requirements(
    session_id: str,
    page: int = Query(default=1, ge=1),
    per_page: int = Query(default=100, ge=1),
):
    """
    查询指定 session 的 L4 底层需求
    """
    normalized_session_id = _non_empty_path_param(session_id, "session_id")
    service = _get_db_service()

    try:
        return service.get_l4_requirements_by_session(
            session_id=normalized_session_id,
            page=page,
            per_page=per_page,
        )
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/requirements/l4/{session_id}/exists")
def check_l4_exists(session_id: str):
    """
    检查指定 session 是否有 L4 底层需求缓存
    """
    normalized_session_id = _non_empty_path_param(session_id, "session_id")
    service = _get_db_service()

    try:
        exists = service.has_l4_requirements(normalized_session_id)
        return {"exists": exists}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/requirements/l4/generate")
def generate_l4_requirements(req: GenerateL4RequirementsRequest):
    """
    生成 L4 底层需求
    """
    service = _get_db_service()
    requested_ids = [item.id for item in req.requirements]

    missing_ids: list[str] = []
    requirements_to_generate = req.requirements

    try:
        if not req.force_regenerate:
            existing_ids = service.get_existing_top_req_ids(
                req.session_id, requested_ids
            )
            existing_id_set = set(existing_ids)
            missing_ids = [rid for rid in requested_ids if rid not in existing_id_set]

            if not missing_ids:
                cached = service.get_l4_requirements_by_session(
                    req.session_id,
                    per_page=500,
                    top_req_ids=requested_ids,
                )
                return {
                    "from_cache": True,
                    "requirements": cached.get("requirements", []),
                    "total": cached.get("total", 0),
                    "generation_results": [],
                }

            requirements_to_generate = [
                item for item in req.requirements if item.id in set(missing_ids)
            ]

        if not requirements_to_generate:
            raise ErrorResponse("没有需要生成的需求", 400)

        payload: dict[str, Any] = {
            "requirements": [item.model_dump() for item in requirements_to_generate],
            "config": req.config,
        }
        if req.model:
            payload["model"] = req.model

        resp = requests.post(
            f"{settings.INFERENCE_BASE_URL}/l4/generate",
            json=payload,
            timeout=600,
        )
        resp.raise_for_status()
        resp_data = cast(dict[str, Any], resp.json())

        all_l4_requirements: list[dict[str, Any]] = []
        for result in resp_data.get("results", []):
            source_top_id = result.get("source_top_id", "")
            source_top_text = ""
            for top_req in requirements_to_generate:
                if top_req.id == source_top_id:
                    source_top_text = top_req.text
                    break

            for l4_req in result.get("l4_requirements", []):
                l4_item = dict(l4_req)
                l4_item["source_top_id"] = source_top_id
                l4_item["source_top_text"] = source_top_text
                l4_item["source_top_ids"] = [source_top_id] if source_top_id else []
                all_l4_requirements.append(l4_item)

        save_result: dict[str, Any] = {
            "inserted": 0,
            "duplicates": 0,
            "inserted_ids": [],
        }
        if all_l4_requirements:
            save_result = service.save_l4_requirements(
                req.session_id, all_l4_requirements
            )

        saved = service.get_l4_requirements_by_session(
            req.session_id,
            per_page=500,
            top_req_ids=requested_ids,
        )

        return {
            "from_cache": False,
            "requirements": saved.get("requirements", []),
            "total": saved.get("total", 0),
            "inserted_count": save_result.get("inserted", 0),
            "duplicates_skipped": save_result.get("duplicates", 0),
            "generation_results": resp_data.get("results", []),
            "kb_version": resp_data.get("kb_version", ""),
            "model_id": resp_data.get("model_id", ""),
            "missing_top_ids": missing_ids,
        }

    except ErrorResponse:
        raise
    except requests.exceptions.RequestException as exc:
        raise ErrorResponse(f"推理后端调用失败: {str(exc)}", 500)
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)
