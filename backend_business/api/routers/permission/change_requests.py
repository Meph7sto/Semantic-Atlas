"""
权限管理 - 变更请求管理
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.permission_schemas import (
    ApproveChangeRequestRequest,
    CreateChangeRequestRequest,
    RejectChangeRequestRequest,
)
from . import get_db_service

router = APIRouter()


@router.post("/requirements/{requirement_id}/change-requests")
def create_change_request(
    requirement_id: str,
    req: CreateChangeRequestRequest,
    current_user: dict = Depends(get_current_user),
):
    """创建变更请求。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    baseline = db_service.get_baseline(req.baseline_id)
    if not baseline:
        raise ErrorResponse("基线不存在", 404)

    project_id = baseline["project_id"]
    if not db_service.check_permission(project_id, user_id, "req:change_request"):
        raise ErrorResponse("无创建变更请求权限", 403)

    change_request = db_service.create_change_request(
        requirement_id=requirement_id,
        baseline_id=req.baseline_id,
        requested_by=user_id,
        reason=req.reason,
        change_summary=req.change_summary,
    )

    if not change_request:
        raise ErrorResponse("创建变更请求失败", 400)

    return change_request


@router.get("/requirements/{requirement_id}/change-requests")
def list_requirement_change_requests(
    requirement_id: str,
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """列出需求的所有变更请求。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    change_requests = db_service.list_requirement_change_requests(
        requirement_id, status=status
    )
    return change_requests


@router.post("/change-requests/{request_id}/approve")
def approve_change_request(
    request_id: str,
    req: Optional[ApproveChangeRequestRequest] = None,
    current_user: dict = Depends(get_current_user),
):
    """批准变更请求。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    review_comment = req.review_comment if req else None

    change_request = db_service.get_change_request(request_id)
    if not change_request:
        raise ErrorResponse("变更请求不存在", 404)

    project_id = change_request["project_id"]
    if not db_service.check_permission(project_id, user_id, "req:change_approve"):
        raise ErrorResponse("无批准变更权限", 403)

    updated_request = db_service.approve_change_request(
        request_id, user_id, review_comment
    )
    if not updated_request:
        raise ErrorResponse("批准变更请求失败", 400)

    return updated_request


@router.post("/change-requests/{request_id}/reject")
def reject_change_request(
    request_id: str,
    req: Optional[RejectChangeRequestRequest] = None,
    current_user: dict = Depends(get_current_user),
):
    """驳回变更请求。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    review_comment = req.review_comment if req else None

    change_request = db_service.get_change_request(request_id)
    if not change_request:
        raise ErrorResponse("变更请求不存在", 404)

    project_id = change_request["project_id"]
    if not db_service.check_permission(project_id, user_id, "req:change_reject"):
        raise ErrorResponse("无驳回变更权限", 403)

    updated_request = db_service.reject_change_request(
        request_id, user_id, review_comment
    )
    if not updated_request:
        raise ErrorResponse("驳回变更请求失败", 400)

    return updated_request


@router.get("/change-requests/pending")
def get_pending_change_requests(
    project_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """获取待审批的变更请求列表。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    if not project_id:
        projects = db_service.get_accessible_projects(user_id)
        accessible_projects = []
        for p_id in projects:
            if db_service.check_permission(p_id, user_id, "req:change_approve"):
                accessible_projects.append(p_id)

        all_requests = []
        for p_id in accessible_projects:
            requests = db_service.get_pending_change_requests(project_id=p_id)
            all_requests.extend(requests)
    else:
        if not db_service.check_permission(project_id, user_id, "req:change_approve"):
            raise ErrorResponse("无查看待审批变更权限", 403)

        all_requests = db_service.get_pending_change_requests(project_id=project_id)

    return all_requests
