import logging

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from core.model_container import model_engine
from schemas.conflict_report import ConflictCheckRequest, ConflictCheckResponse
from services.conflict_service import ConflictService

# 创建 API Router，设置前缀为 /conflict，标签为 Conflict Detection
router = APIRouter(prefix="/conflict", tags=["Conflict Detection"])

# 初始化冲突检测服务
conflict_service = ConflictService(model_engine)

logger = logging.getLogger(__name__)


@router.post("/check", response_model=ConflictCheckResponse)
async def check_conflict(request: ConflictCheckRequest):
    """
    专门分析两个需求是否存在潜在冲突。
    """
    try:
        # 调用服务层进行冲突检测
        result = conflict_service.check_conflict(
            requirement_a=request.requirement_a,
            requirement_b=request.requirement_b,
            model=request.model,
            use_thinking_mode=request.use_thinking_mode,
        )
        return result
            
    except RuntimeError as e:
        logger.exception("Conflict check failed with RuntimeError.")
        # 如果模型服务未初始化或不可用，抛出 503 错误
        raise HTTPException(status_code=503, detail="Model service not initialized or unavailable.")
    except Exception as e:
        logger.exception("Conflict check failed with unexpected exception.")
        # 捕获其他异常，抛出 500 错误
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/stream_check")
async def stream_check_conflict(request: ConflictCheckRequest):
    """
    流式冲突检测接口
    """
    return StreamingResponse(
        conflict_service.check_conflict_stream(
            request.requirement_a, 
            request.requirement_b,
            model=request.model,
            use_thinking_mode=request.use_thinking_mode
        ),
        media_type="application/x-ndjson"
    )
