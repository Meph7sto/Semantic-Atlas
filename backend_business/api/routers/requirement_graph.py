"""
需求图谱路由。

该接口只聚合既有需求管理、追溯、冲突检测、需求分类结果，不改动原分析流程。
"""

from typing import Optional

from fastapi import APIRouter, Query

from backend_business.api.http.errors import ErrorResponse
from backend_business.services.db_service import db_service
from backend_business.services.requirement_graph_service import RequirementGraphService


router = APIRouter(prefix="/api/v2/requirement-graph", tags=["requirement-graph"])


def _require_graph_service() -> RequirementGraphService:
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)
    return RequirementGraphService(db_service)


@router.get("")
def get_requirement_graph(
    project_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    limit: int = Query(default=600, ge=50, le=2000),
):
    """
    生成需求图谱。

    节点仅包含两类：
    - requirement：需求节点
    - stakeholder：利益相关方节点
    """
    normalized_project_id = project_id.strip() if project_id else None
    normalized_session_id = session_id.strip() if session_id else None
    if not normalized_project_id and not normalized_session_id:
        raise ErrorResponse("project_id 和 session_id 至少提供一个", 400)

    try:
        graph = _require_graph_service().build_graph(
            project_id=normalized_project_id,
            session_id=normalized_session_id,
            limit=limit,
        )
        return {"success": True, "data": graph}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)
