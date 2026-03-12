"""需求图谱路由。"""

from typing import Optional

from fastapi import APIRouter, Body, Query

from backend_business.api.http.errors import ErrorResponse
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service
from backend_business.services.requirement_graph_service import RequirementGraphService


router = APIRouter(prefix="/api/v2/requirement-graph", tags=["requirement-graph"])


def _require_graph_service() -> RequirementGraphService:
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)
    return RequirementGraphService(db_service, ai_client=ai_proxy)


def _normalize_graph_scope(project_id: Optional[str], session_id: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    normalized_project_id = project_id.strip() if project_id else None
    normalized_session_id = session_id.strip() if session_id else None
    if not normalized_project_id and not normalized_session_id:
        raise ErrorResponse("project_id 和 session_id 至少提供一个", 400)
    return normalized_project_id, normalized_session_id


@router.get("")
def get_requirement_graph(
    project_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    limit: int = Query(default=600, ge=50, le=2000),
    infer: bool = Query(default=False),
    relation_mode: Optional[str] = Query(default=None),
    inference_limit: int = Query(default=48, ge=12, le=120),
    review_concurrency: int = Query(default=3, ge=1, le=8),
    model: str = Query(default="deepseek-reasoner"),
):
    """
    生成需求图谱。

    节点仅包含两类：
    - requirement：需求节点
    - stakeholder：利益相关方节点
    """
    normalized_project_id, normalized_session_id = _normalize_graph_scope(project_id, session_id)

    try:
        graph = _require_graph_service().build_graph(
            project_id=normalized_project_id,
            session_id=normalized_session_id,
            limit=limit,
            infer_relations=infer,
            relation_mode=(relation_mode or "").strip().lower() or None,
            inference_model=(model or "deepseek-reasoner").strip() or "deepseek-reasoner",
            inference_limit=inference_limit,
            review_concurrency=review_concurrency,
        )
        return {"success": True, "data": graph}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/latest")
def get_latest_requirement_graph_snapshot(
    project_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    relation_mode: Optional[str] = Query(default=None),
    limit: int = Query(default=600, ge=50, le=2000),
):
    normalized_project_id, normalized_session_id = _normalize_graph_scope(project_id, session_id)

    try:
        graph = _require_graph_service().get_latest_snapshot_graph(
            project_id=normalized_project_id,
            session_id=normalized_session_id,
            relation_mode=(relation_mode or "").strip().lower() or None,
            limit=limit,
        )
        return {"success": True, "data": graph}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/history")
def list_requirement_graph_snapshot_history(
    project_id: Optional[str] = Query(default=None),
    session_id: Optional[str] = Query(default=None),
    relation_mode: Optional[str] = Query(default=None),
    limit: int = Query(default=20, ge=1, le=100),
):
    normalized_project_id, normalized_session_id = _normalize_graph_scope(project_id, session_id)

    try:
        items = _require_graph_service().list_snapshot_history(
            project_id=normalized_project_id,
            session_id=normalized_session_id,
            relation_mode=(relation_mode or "").strip().lower() or None,
            limit=limit,
        )
        return {"success": True, "data": {"items": items}}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/snapshots/{snapshot_id}")
def get_requirement_graph_snapshot(snapshot_id: str, limit: int = Query(default=600, ge=50, le=2000)):
    normalized_snapshot_id = (snapshot_id or "").strip()
    if not normalized_snapshot_id:
        raise ErrorResponse("snapshot_id 不能为空", 400)

    try:
        graph = _require_graph_service().get_snapshot_graph(normalized_snapshot_id, limit=limit)
        return {"success": True, "data": graph}
    except ValueError as exc:
        raise ErrorResponse(str(exc), 404)
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/infer")
def infer_requirement_graph(payload: Optional[dict] = Body(default=None)):
    payload = payload or {}
    normalized_project_id = (payload.get("project_id") or "").strip() or None
    normalized_session_id = (payload.get("session_id") or "").strip() or None
    if not normalized_project_id and not normalized_session_id:
        raise ErrorResponse("project_id 和 session_id 至少提供一个", 400)

    limit = int(payload.get("limit") or 80)
    inference_limit = int(payload.get("inference_limit") or min(limit, 48))
    review_concurrency = int(payload.get("review_concurrency") or 3)
    model = (payload.get("model") or "deepseek-reasoner").strip() or "deepseek-reasoner"
    relation_mode = (payload.get("relation_mode") or "llm").strip().lower() or "llm"
    review_edges = payload.get("review_edges") if isinstance(payload.get("review_edges"), list) else None

    try:
        graph = _require_graph_service().build_graph(
            project_id=normalized_project_id,
            session_id=normalized_session_id,
            limit=limit,
            infer_relations=True,
            relation_mode=relation_mode,
            inference_model=model,
            inference_limit=inference_limit,
            review_edges=review_edges,
            review_concurrency=review_concurrency,
        )
        return {"success": True, "data": graph}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)
