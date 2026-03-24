"""
需求去重路由 - FastAPI 版本
对应历史蓝图: dedup_bp (url_prefix="/api/v2/dedup")
"""

from fastapi import APIRouter

from backend_business.config import settings
from backend_business.services.requirements_deduplication import (
    RequirementsDeduplicationService,
)
from backend_business.api.routers.schemas.deduplication_schemas import (
    DetectDuplicatesRequest,
    DeleteRequirementsRequest,
    GetSimilarPairsRequest,
    MergeRequest,
    RegenerateLLMDecisionRequest,
    UpdateRequirementRequest,
)

router = APIRouter(prefix="/api/v2/dedup", tags=["deduplication"])

# 初始化去重服务
_dedup_service = RequirementsDeduplicationService(dsn=settings.POSTGRES_DSN)


def _service_with_threshold(threshold):
    """根据阈值创建去重服务实例"""
    if threshold is None:
        return _dedup_service
    return RequirementsDeduplicationService(
        dsn=settings.POSTGRES_DSN,
        similarity_threshold=float(threshold),
    )


@router.post("/detect")
def detect_duplicates(req: DetectDuplicatesRequest):
    """
    检测重复需求

    Request body:
    {
        "session_id": "xxx",              # Required
        "level": "L1" | "L2" | "L3",      # Optional, filter by level
        "with_llm_decision": true,         # Optional, default true
        "auto_merge": false,               # Optional, default false
        "model": "deepseek-reasoner",      # Optional
        "threshold": 0.85,                 # Optional, similarity threshold
        "max_concurrent": 5                # Optional, max concurrent LLM calls
    }

    Returns:
    {
        "duplicate_groups": [...],
        "total_duplicates": int,
        "total_requirements_scanned": int,
        "total_merged": int | null
    }
    """
    service = _service_with_threshold(req.threshold)
    result = service.detect_duplicates(
        session_id=req.session_id,
        level=req.level,
        with_llm_decision=req.with_llm_decision,
        auto_merge=req.auto_merge,
        model_name=req.model,
        max_concurrent=req.max_concurrent,
    )
    return result


@router.post("/merge")
def execute_merge(req: MergeRequest):
    """
    执行合并操作（用户确认后手动调用）

    Request body:
    {
        "session_id": "xxx",                  # Required
        "primary_req_id": "xxx",              # Required, the requirement to keep
        "to_delete_req_ids": ["id1", "id2"],  # Required, requirements to delete
        "merged_text": "...",                 # Required, the merged requirement text
        "merged_level": "L2",                 # Required
        "reason": "..."                       # Optional
    }

    Returns:
    {
        "primary_req_id": "xxx",
        "deleted_count": 2,
        "old_text": "...",
        "new_text": "...",
        "reason": "..."
    }
    """
    result = _dedup_service.execute_merge(
        session_id=req.session_id,
        primary_req_id=req.primary_req_id,
        to_delete_req_ids=req.to_delete_req_ids,
        merged_text=req.merged_text,
        merged_level=req.merged_level,
        reason=req.reason,
    )
    return result


@router.post("/delete")
def delete_requirements(req: DeleteRequirementsRequest):
    """
    批量删除需求

    Request body:
    {
        "session_id": "xxx",          # Required
        "req_ids": ["id1", "id2"],    # Required
        "reason": "..."               # Optional
    }

    Returns:
    {
        "deleted_count": 2
    }
    """
    result = _dedup_service.delete_requirements(
        session_id=req.session_id,
        req_ids=req.req_ids,
        reason=req.reason,
    )
    return result


@router.post("/update")
def update_requirement(req: UpdateRequirementRequest):
    """
    更新单个需求的文本和/或层级

    Request body:
    {
        "session_id": "xxx",      # Required
        "req_id": "xxx",          # Required
        "new_text": "...",        # Required
        "new_level": "L2",        # Optional
        "reason": "..."           # Optional
    }

    Returns:
    {
        "req_id": "xxx",
        "old_text": "...",
        "new_text": "..."
    }
    """
    result = _dedup_service.update_requirement(
        session_id=req.session_id,
        req_id=req.req_id,
        new_text=req.new_text,
        new_level=req.new_level,
        reason=req.reason,
    )
    return result


@router.post("/pairs")
def get_similar_pairs(req: GetSimilarPairsRequest):
    """
    获取所有相似的需求对（不分组）

    Request body:
    {
        "session_id": "xxx",          # Required
        "level": "L1" | "L2" | "L3",  # Optional
        "threshold": 0.85             # Optional
    }

    Returns:
    {
        "pairs": [{"req_1": {...}, "req_2": {...}, "similarity": 0.92}, ...],
        "total_pairs": int,
        "total_requirements_scanned": int
    }
    """
    service = _service_with_threshold(req.threshold)
    result = service.get_similar_pairs(
        session_id=req.session_id,
        level=req.level,
    )
    return result


@router.post("/regenerate")
def regenerate_llm_decision(req: RegenerateLLMDecisionRequest):
    """
    为指定的需求重新生成LLM合并建议

    Request body:
    {
        "session_id": "xxx",          # Required
        "req_ids": ["id1", "id2"],    # Required, at least 2
        "model": "deepseek-reasoner"  # Optional
    }

    Returns:
    {
        "requirements": [...],
        "similarity": float,
        "llm_decision": {
            "should_merge": bool,
            "merged_text": "...",
            "merged_level": "L2",
            "primary_req_id": "...",
            "reason": "...",
            "error": null
        }
    }
    """
    result = _dedup_service.regenerate_llm_decision(
        session_id=req.session_id,
        req_ids=req.req_ids,
        model_name=req.model,
    )
    return result
