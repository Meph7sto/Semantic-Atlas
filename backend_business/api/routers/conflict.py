"""
冲突分析路由 - FastAPI 版本
对应 Flask blueprint: conflict_bp (url_prefix="/api/conflict")
"""

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse

from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.conflict_schemas import (
    ConflictCheckBatchRequest,
    ConflictCheckRequest,
)
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service

router = APIRouter(prefix="/api/v2/conflict", tags=["conflict"])


def _normalize_session_id(session_id: str | None) -> str | None:
    if session_id is None:
        return None
    normalized = session_id.strip()
    return normalized or None


@router.post("/check")
def check_conflict(req: ConflictCheckRequest):
    """
    单条冲突检测。

    兼容历史成功响应结构：{"success", "data", "record_id"}。
    错误响应统一由 FastAPI 异常处理器输出 {"detail": "..."}。
    """
    session_id = _normalize_session_id(req.session_id)

    try:
        result = ai_proxy.conflict_check(
            req.requirement_a,
            req.requirement_b,
            use_thinking_mode=req.use_thinking_mode,
        )
        record_id = None

        if req.save_to_db:
            if db_service is None:
                raise ErrorResponse("数据库服务未初始化", 500)

            record_ids = db_service.save_conflict_batch(
                session_id=session_id,
                conflicts=[
                    {
                        "requirement_a": req.requirement_a,
                        "requirement_b": req.requirement_b,
                        "is_conflict": result.get("is_conflict", False),
                        "raw_response": result.get("raw_response", ""),
                        "data": result,
                    }
                ],
            )
            if record_ids:
                record_id = record_ids[0]

        return {"success": True, "data": result, "record_id": record_id}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/stream_check")
def stream_check_conflict(req: ConflictCheckRequest):
    """
    单条冲突检测（流式）。

    由业务后端转发推理后端 NDJSON 流，前端不再直连 inference。
    """
    try:
        stream = ai_proxy.conflict_stream_check(
            req.requirement_a,
            req.requirement_b,
            use_thinking_mode=req.use_thinking_mode,
        )
        return StreamingResponse(stream, media_type="application/x-ndjson")
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/check/batch")
def check_conflict_batch(req: ConflictCheckBatchRequest):
    """
    批量冲突检测。

    输入 pairs 采用严格校验，非法结构由 FastAPI 直接返回 422。
    """
    session_id = _normalize_session_id(req.session_id)

    try:
        results = []
        conflicts_to_save = []

        for pair in req.pairs:
            result = ai_proxy.conflict_check(pair.requirement_a, pair.requirement_b)
            results.append(
                {
                    "requirement_a": pair.requirement_a,
                    "requirement_b": pair.requirement_b,
                    **result,
                }
            )

            if req.save_to_db:
                conflicts_to_save.append(
                    {
                        "requirement_a": pair.requirement_a,
                        "requirement_b": pair.requirement_b,
                        "is_conflict": result.get("is_conflict", False),
                        "raw_response": result.get("raw_response", ""),
                        "data": result,
                    }
                )

        record_ids = []
        if req.save_to_db and conflicts_to_save:
            if db_service is None:
                raise ErrorResponse("数据库服务未初始化", 500)
            record_ids = db_service.save_conflict_batch(
                session_id=session_id,
                conflicts=conflicts_to_save,
            )

        return {
            "success": True,
            "data": results,
            "record_ids": record_ids,
            "total": len(results),
        }
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/latest")
def get_latest_conflict_batch(session_id: str = Query(..., min_length=1)):
    """
    获取 session 下最近一次批量冲突检测结果。
    """
    normalized_session_id = session_id.strip()
    if not normalized_session_id:
        raise ErrorResponse("session_id 不能为空", 400)
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    try:
        data = db_service.get_latest_conflict_batch(normalized_session_id)
        return {"success": True, "data": data}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)
