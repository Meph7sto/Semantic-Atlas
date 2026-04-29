"""
需求管理路由 - FastAPI 版本
对应历史蓝图: requirements_bp (url_prefix="/api/v2")
"""

import asyncio
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
_DEFAULT_L4_MODEL = "deepseek-v4-pro"


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


def _l4_connect_timeout_seconds() -> float:
    return max(0.1, float(settings.L4_GENERATION_CONNECT_TIMEOUT_SECONDS))


def _l4_single_requirement_timeout_seconds() -> float:
    return max(1.0, float(settings.L4_SINGLE_REQUIREMENT_TIMEOUT_SECONDS))


def _l4_stream_max_concurrent(config: dict[str, Any] | None) -> int:
    raw_value = (config or {}).get("max_concurrent", 4)
    try:
        return max(1, min(8, int(raw_value)))
    except (TypeError, ValueError):
        return 4


def _build_l4_generation_payload(
    requirements_to_generate: list[Any],
    config: dict[str, Any],
    model: str | None,
    use_thinking_mode: bool = True,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "requirements": [item.model_dump() for item in requirements_to_generate],
        "config": config,
        "use_thinking_mode": use_thinking_mode,
    }
    if model:
        payload["model"] = model
    return payload


def _build_l4_timeout_result(top_requirement: Any) -> dict[str, Any]:
    timeout_seconds = _l4_single_requirement_timeout_seconds()
    timeout_display = (
        str(int(timeout_seconds))
        if float(timeout_seconds).is_integer()
        else f"{timeout_seconds:.1f}"
    )
    return {
        "source_top_id": top_requirement.id,
        "l4_requirements": [],
        "open_questions": [
            (
                f"L4 生成超时（单条需求上限 {timeout_display}s），"
                "请缩小输入范围或切换更快模型后重试"
            )
        ],
    }


def _find_l4_generation_result(
    resp_data: dict[str, Any], top_requirement: Any
) -> dict[str, Any]:
    results = resp_data.get("results", [])
    for result in results:
        if result.get("source_top_id") == top_requirement.id:
            return cast(dict[str, Any], result)
    if results:
        return cast(dict[str, Any], results[0])
    return {
        "source_top_id": top_requirement.id,
        "l4_requirements": [],
        "open_questions": ["推理后端未返回生成结果"],
    }


def _collect_l4_requirements_to_save(
    generation_result: dict[str, Any],
    top_requirement: Any,
) -> list[dict[str, Any]]:
    all_l4_requirements: list[dict[str, Any]] = []
    source_top_id = generation_result.get("source_top_id", top_requirement.id)
    source_top_text = top_requirement.text if source_top_id == top_requirement.id else ""

    for l4_req in generation_result.get("l4_requirements", []):
        l4_item = dict(l4_req)
        l4_item["source_top_id"] = source_top_id
        l4_item["source_top_text"] = source_top_text
        l4_item["source_top_ids"] = [source_top_id] if source_top_id else []
        all_l4_requirements.append(l4_item)

    return all_l4_requirements


def _get_saved_l4_requirements_for_top(
    service: Any,
    session_id: str,
    top_req_id: str,
) -> list[dict[str, Any]]:
    saved = service.get_l4_requirements_by_session(
        session_id,
        per_page=500,
        top_req_ids=[top_req_id],
    )
    return cast(list[dict[str, Any]], saved.get("requirements", []))


def _build_stream_item_payload(
    *,
    top_requirement: Any,
    generation_result: dict[str, Any],
    requirements: list[dict[str, Any]],
    from_cache: bool,
    status: str,
    inserted_count: int = 0,
    duplicates_skipped: int = 0,
    timed_out: bool = False,
    failed: bool = False,
    kb_version: str = "",
    model_id: str = "",
    error_message: str = "",
) -> dict[str, Any]:
    return {
        "source_top_id": top_requirement.id,
        "source_top_text": top_requirement.text,
        "from_cache": from_cache,
        "status": status,
        "timed_out": timed_out,
        "failed": failed,
        "requirements": requirements,
        "generation_result": generation_result,
        "inserted_count": inserted_count,
        "duplicates_skipped": duplicates_skipped,
        "kb_version": kb_version,
        "model_id": model_id,
        "error_message": error_message,
    }


def _generate_single_l4_item(
    service: Any,
    session_id: str,
    top_requirement: Any,
    config: dict[str, Any],
    model: str | None,
    use_thinking_mode: bool = True,
) -> dict[str, Any]:
    payload = _build_l4_generation_payload(
        [top_requirement], config, model, use_thinking_mode
    )
    default_model = model or _DEFAULT_L4_MODEL

    try:
        resp = requests.post(
            f"{settings.INFERENCE_BASE_URL}/l4/generate",
            json=payload,
            timeout=(
                _l4_connect_timeout_seconds(),
                _l4_single_requirement_timeout_seconds(),
            ),
        )
        resp.raise_for_status()
        resp_data = cast(dict[str, Any], resp.json())
        generation_result = _find_l4_generation_result(resp_data, top_requirement)

        save_result: dict[str, Any] = {
            "inserted": 0,
            "duplicates": 0,
            "inserted_ids": [],
        }
        l4_requirements_to_save = _collect_l4_requirements_to_save(
            generation_result, top_requirement
        )
        if l4_requirements_to_save:
            save_result = service.save_l4_requirements(
                session_id, l4_requirements_to_save
            )

        requirements = _get_saved_l4_requirements_for_top(
            service, session_id, top_requirement.id
        )
        return _build_stream_item_payload(
            top_requirement=top_requirement,
            generation_result=generation_result,
            requirements=requirements,
            from_cache=False,
            status="completed",
            inserted_count=int(save_result.get("inserted", 0) or 0),
            duplicates_skipped=int(save_result.get("duplicates", 0) or 0),
            kb_version=str(resp_data.get("kb_version", "") or ""),
            model_id=str(resp_data.get("model_id", "") or default_model),
        )
    except (requests.exceptions.Timeout, requests.exceptions.ReadTimeout):
        return _build_stream_item_payload(
            top_requirement=top_requirement,
            generation_result=_build_l4_timeout_result(top_requirement),
            requirements=[],
            from_cache=False,
            status="timeout",
            timed_out=True,
            model_id=default_model,
            error_message="L4 生成超时",
        )
    except requests.exceptions.RequestException as exc:
        generation_result = {
            "source_top_id": top_requirement.id,
            "l4_requirements": [],
            "open_questions": [f"推理后端调用失败: {str(exc)}"],
        }
        return _build_stream_item_payload(
            top_requirement=top_requirement,
            generation_result=generation_result,
            requirements=[],
            from_cache=False,
            status="error",
            failed=True,
            model_id=default_model,
            error_message=str(exc),
        )
    except Exception as exc:
        generation_result = {
            "source_top_id": top_requirement.id,
            "l4_requirements": [],
            "open_questions": [str(exc)],
        }
        return _build_stream_item_payload(
            top_requirement=top_requirement,
            generation_result=generation_result,
            requirements=[],
            from_cache=False,
            status="error",
            failed=True,
            model_id=default_model,
            error_message=str(exc),
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
            use_thinking_mode=req.use_thinking_mode,
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
            use_thinking_mode=req.use_thinking_mode,
            adaptive_retry_r2=req.adaptive_retry_r2,
            max_spans_per_bundle=req.max_spans_per_bundle,
            token_limit=req.token_limit,
            top_m_2hop=req.top_m_2hop,
            keywords=req.keywords,
            enable_parallel=req.enable_parallel_windows,
            max_concurrent=req.max_concurrent_windows,
            history_aware=req.history_aware,
            planner_connect_timeout_seconds=req.planner_connect_timeout_seconds,
            planner_read_timeout_seconds=req.planner_read_timeout_seconds,
            planner_max_retries=req.planner_max_retries,
        )

        if req.post_dedup:
            service = _dedup_service_for_request(req.dedup_threshold, req.model)
            dedup_result = service.detect_duplicates(
                session_id=req.session_id,
                level=None,
                with_llm_decision=req.dedup_with_llm,
                auto_merge=req.dedup_auto_merge,
                pairwise_review=req.pairwise_dedup,
                pairwise_auto_apply=req.pairwise_auto_apply,
                pairwise_max_pairs=req.pairwise_max_pairs,
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
                use_thinking_mode=req.use_thinking_mode,
                adaptive_retry_r2=req.adaptive_retry_r2,
                max_spans_per_bundle=req.max_spans_per_bundle,
                token_limit=req.token_limit,
                top_m_2hop=req.top_m_2hop,
                keywords=req.keywords,
                enable_parallel=req.enable_parallel_windows,
                max_concurrent=req.max_concurrent_windows,
                history_aware=req.history_aware,
                planner_connect_timeout_seconds=req.planner_connect_timeout_seconds,
                planner_read_timeout_seconds=req.planner_read_timeout_seconds,
                planner_max_retries=req.planner_max_retries,
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
                    pairwise_review=req.pairwise_dedup,
                    pairwise_auto_apply=req.pairwise_auto_apply,
                    pairwise_max_pairs=req.pairwise_max_pairs,
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


@router.delete("/requirements/l4/{session_id}")
def clear_l4_requirements(session_id: str):
    """
    清空指定 session 的全部 L4 底层需求
    """
    normalized_session_id = _non_empty_path_param(session_id, "session_id")
    service = _get_db_service()

    try:
        deleted_count = service.clear_l4_requirements_for_session(normalized_session_id)
        return {
            "session_id": normalized_session_id,
            "deleted_count": deleted_count,
        }
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

        generation_results: list[dict[str, Any]] = []
        timed_out_top_ids: list[str] = []
        kb_version = ""
        model_id = req.model or _DEFAULT_L4_MODEL

        for item in requirements_to_generate:
            payload = _build_l4_generation_payload(
                [item], req.config, req.model, req.use_thinking_mode
            )

            try:
                resp = requests.post(
                    f"{settings.INFERENCE_BASE_URL}/l4/generate",
                    json=payload,
                    timeout=(
                        _l4_connect_timeout_seconds(),
                        _l4_single_requirement_timeout_seconds(),
                    ),
                )
                resp.raise_for_status()
                resp_data = cast(dict[str, Any], resp.json())
            except (
                requests.exceptions.Timeout,
                requests.exceptions.ReadTimeout,
            ):
                timed_out_top_ids.append(item.id)
                generation_results.append(_build_l4_timeout_result(item))
                continue

            kb_version = resp_data.get("kb_version") or kb_version
            model_id = resp_data.get("model_id") or model_id
            item_results = resp_data.get("results", [])

            if item_results:
                generation_results.extend(item_results)
            else:
                generation_results.append(
                    {
                        "source_top_id": item.id,
                        "l4_requirements": [],
                        "open_questions": ["推理后端未返回生成结果"],
                    }
                )

        all_l4_requirements: list[dict[str, Any]] = []
        for result in generation_results:
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
            "generation_results": generation_results,
            "kb_version": kb_version,
            "model_id": model_id,
            "missing_top_ids": missing_ids,
            "timed_out_top_ids": timed_out_top_ids,
            "per_requirement_timeout_seconds": _l4_single_requirement_timeout_seconds(),
        }

    except ErrorResponse:
        raise
    except requests.exceptions.RequestException as exc:
        raise ErrorResponse(f"推理后端调用失败: {str(exc)}", 500)
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/requirements/l4/generate/stream")
async def generate_l4_requirements_stream(req: GenerateL4RequirementsRequest):
    """
    并发流式生成 L4 底层需求。
    - 缓存命中的顶层需求立即逐条返回
    - 缺失项并发调用推理后端
    - 每条顶层需求完成后立刻以 SSE item 事件返回
    """
    service = _get_db_service()
    requested_ids = [item.id for item in req.requirements]

    try:
        existing_ids: list[str] = []
        if not req.force_regenerate:
            existing_ids = await asyncio.to_thread(
                service.get_existing_top_req_ids,
                req.session_id,
                requested_ids,
            )
        existing_id_set = set(existing_ids)
        cached_items = (
            [item for item in req.requirements if item.id in existing_id_set]
            if not req.force_regenerate
            else []
        )
        missing_items = (
            list(req.requirements)
            if req.force_regenerate
            else [item for item in req.requirements if item.id not in existing_id_set]
        )
        max_concurrent = _l4_stream_max_concurrent(req.config)
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)

    async def generate():
        total_count = len(req.requirements)
        completed_count = 0
        inserted_total = 0
        duplicates_total = 0
        timed_out_top_ids: list[str] = []
        failed_top_ids: list[str] = []
        last_kb_version = ""
        last_model_id = req.model or _DEFAULT_L4_MODEL

        yield _sse_event(
            "init",
            {
                "session_id": req.session_id,
                "total_count": total_count,
                "cached_count": len(cached_items),
                "missing_count": len(missing_items),
                "max_concurrent": max_concurrent,
                "per_requirement_timeout_seconds": _l4_single_requirement_timeout_seconds(),
            },
        )

        try:
            for item in cached_items:
                requirements = await asyncio.to_thread(
                    _get_saved_l4_requirements_for_top,
                    service,
                    req.session_id,
                    item.id,
                )
                payload = _build_stream_item_payload(
                    top_requirement=item,
                    generation_result={
                        "source_top_id": item.id,
                        "l4_requirements": [],
                        "open_questions": [],
                    },
                    requirements=requirements,
                    from_cache=True,
                    status="cached",
                )
                completed_count += 1
                yield _sse_event(
                    "item",
                    {
                        **payload,
                        "completed_count": completed_count,
                        "total_count": total_count,
                    },
                )

            semaphore = asyncio.Semaphore(max_concurrent)

            async def _run_single(item: Any) -> dict[str, Any]:
                async with semaphore:
                    return await asyncio.to_thread(
                        _generate_single_l4_item,
                        service,
                        req.session_id,
                        item,
                        req.config,
                        req.model,
                        req.use_thinking_mode,
                    )

            tasks = [asyncio.create_task(_run_single(item)) for item in missing_items]
            try:
                for task in asyncio.as_completed(tasks):
                    payload = await task
                    completed_count += 1
                    inserted_total += int(payload.get("inserted_count", 0) or 0)
                    duplicates_total += int(payload.get("duplicates_skipped", 0) or 0)
                    if payload.get("timed_out"):
                        timed_out_top_ids.append(payload["source_top_id"])
                    if payload.get("failed"):
                        failed_top_ids.append(payload["source_top_id"])
                    last_kb_version = payload.get("kb_version") or last_kb_version
                    last_model_id = payload.get("model_id") or last_model_id
                    yield _sse_event(
                        "item",
                        {
                            **payload,
                            "completed_count": completed_count,
                            "total_count": total_count,
                        },
                    )
            finally:
                for task in tasks:
                    if not task.done():
                        task.cancel()

            yield _sse_event(
                "done",
                {
                    "session_id": req.session_id,
                    "completed_count": completed_count,
                    "total_count": total_count,
                    "inserted_count": inserted_total,
                    "duplicates_skipped": duplicates_total,
                    "timed_out_top_ids": timed_out_top_ids,
                    "failed_top_ids": failed_top_ids,
                    "kb_version": last_kb_version,
                    "model_id": last_model_id,
                    "max_concurrent": max_concurrent,
                    "per_requirement_timeout_seconds": _l4_single_requirement_timeout_seconds(),
                },
            )
        except Exception as exc:
            yield _sse_event("error", {"message": str(exc)})

    return sse_response_raw(generate())
