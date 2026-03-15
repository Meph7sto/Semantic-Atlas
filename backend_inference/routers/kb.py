"""
KB Router - 知识库检索 API 路由
"""

from fastapi import APIRouter, HTTPException

from schemas.kb_schemas import KBSearchRequest, KBSearchResponse, KBStatus
from services.audit_log_service import log_audit_event
from services.kb_service import get_kb_service

router = APIRouter(prefix="/kb", tags=["Knowledge Base"])


@router.post("/search", response_model=KBSearchResponse)
async def search_kb(request: KBSearchRequest) -> KBSearchResponse:
    """
    知识库检索接口

    Args:
        request: 检索请求，包含 query, kb_type, top_k, filters

    Returns:
        检索结果，包含 items, kb_version, total_searched
    """
    try:
        kb_service = get_kb_service()
        response = kb_service.search(
            query=request.query,
            kb_type=request.kb_type,
            top_k=request.top_k,
            filters=request.filters,
        )
        log_audit_event(
            event_type="kb.search",
            payload={
                "query": request.query,
                "kb_type": request.kb_type,
                "top_k": request.top_k,
                "filters": request.filters,
                "kb_version": response.kb_version,
                "total_searched": response.total_searched,
                "item_count": len(response.items),
                "item_ids": [item.evidence_id for item in response.items],
            },
        )
        return response
    except Exception as e:
        log_audit_event(
            event_type="kb.search",
            payload={
                "query": request.query,
                "kb_type": request.kb_type,
                "top_k": request.top_k,
                "filters": request.filters,
            },
            status="error",
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"KB search failed: {str(e)}")


@router.get("/status", response_model=KBStatus)
async def get_kb_status() -> KBStatus:
    """
    获取知识库状态

    Returns:
        知识库状态信息
    """
    try:
        kb_service = get_kb_service()
        status = kb_service.get_status()
        log_audit_event(
            event_type="kb.status",
            payload=status.dict(),
        )
        return status
    except Exception as e:
        log_audit_event(
            event_type="kb.status",
            payload={},
            status="error",
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"Get KB status failed: {str(e)}")


@router.post("/rebuild")
async def rebuild_kb():
    """
    重建知识库索引

    Returns:
        新的知识库版本
    """
    try:
        kb_service = get_kb_service()
        version = kb_service.build_indexes()
        payload = {"status": "ok", "kb_version": version}
        log_audit_event(
            event_type="kb.rebuild",
            payload=payload,
        )
        return payload
    except Exception as e:
        log_audit_event(
            event_type="kb.rebuild",
            payload={},
            status="error",
            error=str(e),
        )
        raise HTTPException(status_code=500, detail=f"KB rebuild failed: {str(e)}")
