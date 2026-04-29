"""
L4 Generation Router - L4 需求生成 API 路由
"""

from fastapi import APIRouter, HTTPException

from schemas.l4_schemas import (
    GenerateConfig,
    GenerateL4Request,
    GenerateL4Response,
)
from services.audit_log_service import log_audit_event
from services.l4_generation_service import get_l4_generation_service

router = APIRouter(prefix="/l4", tags=["L4 Generation"])
root_router = APIRouter(tags=["L4 Generation"])


@router.post("/generate", response_model=GenerateL4Response)
def generate_l4(request: GenerateL4Request) -> GenerateL4Response:
    """
    生成 L4 需求

    Args:
        request: 生成请求，包含顶层需求列表和配置

    Returns:
        生成结果，包含每条顶层需求对应的 L4 列表
    """
    try:
        service = get_l4_generation_service()
        response = service.generate_l4(
            requirements=request.requirements,
            config=request.config,
            model_id=request.model,
            use_thinking_mode=request.use_thinking_mode,
        )
        log_audit_event(
            event_type="l4.generate",
            payload={
                "top_requirement_count": len(request.requirements),
                "top_requirement_ids": [req.id for req in request.requirements],
                "config": request.config.dict() if request.config else None,
                "kb_version": response.kb_version,
                "model_id": response.model_id,
                "result_summary": [
                    {
                        "source_top_id": result.source_top_id,
                        "l4_count": len(result.l4_requirements),
                        "open_question_count": len(result.open_questions),
                    }
                    for result in response.results
                ],
            },
        )
        return response
    except Exception as e:
        log_audit_event(
            event_type="l4.generate",
            payload={
                "top_requirement_count": len(request.requirements),
                "top_requirement_ids": [req.id for req in request.requirements],
                "model_id": request.model,
            },
            status="error",
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"L4 generation failed: {str(e)}")


# 兼容 mission.txt 中定义的 /generate_l4 路径
@router.post("/generate_l4", response_model=GenerateL4Response, include_in_schema=False)
def generate_l4_alias(request: GenerateL4Request) -> GenerateL4Response:
    """兼容别名"""
    return generate_l4(request)


@root_router.post("/generate_l4", response_model=GenerateL4Response)
def generate_l4_root(request: GenerateL4Request) -> GenerateL4Response:
    """mission.txt 根路径"""
    return generate_l4(request)
