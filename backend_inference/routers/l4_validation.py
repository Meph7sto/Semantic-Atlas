"""
L4 Validation Router - L4 需求校验 API 路由
"""

from fastapi import APIRouter, HTTPException

from schemas.l4_schemas import (
    ValidateL4Request,
    ValidateL4Response,
)
from services.audit_log_service import log_audit_event
from services.l4_validator_service import get_l4_validator_service

router = APIRouter(prefix="/l4", tags=["L4 Validation"])
root_router = APIRouter(tags=["L4 Validation"])


@router.post("/validate", response_model=ValidateL4Response)
async def validate_l4(request: ValidateL4Request) -> ValidateL4Response:
    """
    校验 L4 需求

    Args:
        request: 校验请求，包含待校验的 L4 列表

    Returns:
        校验结果，包含每条 L4 的问题列表和覆盖率统计
    """
    try:
        service = get_l4_validator_service()
        response = service.validate_batch(
            request.l4_requirements,
            expected_top_ids=request.expected_top_ids,
            open_questions_by_top_id=request.open_questions_by_top_id,
            allowed_evidence_ids=request.allowed_evidence_ids,
            confidence_threshold=request.confidence_threshold,
        )
        log_audit_event(
            event_type="l4.validate",
            payload={
                "l4_count": len(request.l4_requirements),
                "top_requirement_ids": list(
                    {
                        item.source_top_id
                        for item in request.l4_requirements
                        if item.source_top_id
                    }
                ),
                "expected_top_ids": request.expected_top_ids,
                "open_questions_by_top_id": request.open_questions_by_top_id,
                "allowed_evidence_ids": request.allowed_evidence_ids,
                "confidence_threshold": request.confidence_threshold,
                "coverage_summary": response.coverage_summary.dict(),
                "global_pass": response.global_pass,
            },
        )
        return response
    except Exception as e:
        log_audit_event(
            event_type="l4.validate",
            payload={"l4_count": len(request.l4_requirements)},
            status="error",
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"L4 validation failed: {str(e)}")


# 兼容 mission.txt 中定义的 /validate_l4 路径
@router.post("/validate_l4", response_model=ValidateL4Response, include_in_schema=False)
async def validate_l4_alias(request: ValidateL4Request) -> ValidateL4Response:
    """兼容别名"""
    return await validate_l4(request)


@root_router.post("/validate_l4", response_model=ValidateL4Response)
async def validate_l4_root(request: ValidateL4Request) -> ValidateL4Response:
    """mission.txt 根路径"""
    return await validate_l4(request)
