from __future__ import annotations

from fastapi import APIRouter, HTTPException

from core.model_container import model_engine
from schemas.trace_output import (
    BatchTraceRelationRequest,
    BatchTraceRelationResponse,
    TraceRelationRequest,
    TraceRelationResponse,
)
from services.traceability_service import TraceabilityService

router = APIRouter(prefix="/traceability", tags=["Traceability"])

# 初始化追溯服务（所有业务逻辑均委托给 Service 层）
traceability_service = TraceabilityService(model_engine=model_engine)


@router.post("/relation", response_model=TraceRelationResponse)
async def analyze_relation(request: TraceRelationRequest):
    """
    单对需求关系追溯：判断顶层需求与底层需求之间是否存在直接追溯关系。
    """
    if model_engine.model is None:
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")

    try:
        return traceability_service.analyze_relation(
            high_level_requirement=request.high_level_requirement,
            low_level_requirement=request.low_level_requirement,
            max_new_tokens=request.max_new_tokens,
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/batch-relation", response_model=BatchTraceRelationResponse)
async def batch_analyze_relation(request: BatchTraceRelationRequest):
    """
    批量需求关系追溯：分析多对顶层需求与底层需求之间的追溯关系。
    """
    if model_engine.model is None:
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")

    # 清洗空字符串，避免无意义组合
    highs = [str(s).strip() for s in request.high_level_requirements if str(s).strip()]
    lows = [str(s).strip() for s in request.low_level_requirements if str(s).strip()]
    if not highs or not lows:
        raise HTTPException(status_code=400, detail="high_level_requirements 与 low_level_requirements 不能为空。")

    try:
        return traceability_service.batch_analyze(
            high_level_requirements=highs,
            low_level_requirements=lows,
            max_new_tokens=request.max_new_tokens,
        )
    except RuntimeError:
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
