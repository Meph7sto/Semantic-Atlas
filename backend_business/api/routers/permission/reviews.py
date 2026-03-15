"""
权限管理 - 评审指派管理
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.permission_schemas import (
    ApproveReviewRequest,
    CreateReviewRequest,
    RejectReviewRequest,
)
from . import get_db_service

router = APIRouter()


@router.post("/requirements/{requirement_id}/reviews")
def create_review_assignment(
    requirement_id: str,
    req: CreateReviewRequest,
    current_user: dict = Depends(get_current_user),
):
    """创建评审指派。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    reviewer_id = req.reviewer_id

    reviewer = db_service.get_user_by_id(reviewer_id)
    if not reviewer:
        raise ErrorResponse("评审人不存在", 404)

    assignment = db_service.create_review_assignment(
        requirement_id=requirement_id,
        reviewer_id=reviewer_id,
        initiated_by=user_id,
        seq=req.seq,
        comment=req.comment,
    )

    if not assignment:
        raise ErrorResponse("创建评审指派失败", 400)

    return assignment


@router.get("/requirements/{requirement_id}/reviews")
def list_requirement_reviews(
    requirement_id: str,
    status: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """列出需求的所有评审。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    reviews = db_service.list_requirement_reviews(requirement_id, status=status)
    return reviews


@router.post("/reviews/{assignment_id}/approve")
def approve_review(
    assignment_id: str,
    req: Optional[ApproveReviewRequest] = None,
    current_user: dict = Depends(get_current_user),
):
    """通过评审。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    comment = req.comment if req else None
    assignment = db_service.approve_review(assignment_id, user_id, comment)

    if not assignment:
        raise ErrorResponse("审批失败（无权限或评审不存在）", 400)

    return assignment


@router.post("/reviews/{assignment_id}/reject")
def reject_review(
    assignment_id: str,
    req: Optional[RejectReviewRequest] = None,
    current_user: dict = Depends(get_current_user),
):
    """驳回评审。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    comment = req.comment if req else None
    assignment = db_service.reject_review(assignment_id, user_id, comment)

    if not assignment:
        raise ErrorResponse("驳回失败（无权限或评审不存在）", 400)

    return assignment


@router.post("/reviews/{assignment_id}/withdraw")
def withdraw_review(
    assignment_id: str,
    current_user: dict = Depends(get_current_user),
):
    """撤回评审。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    assignment = db_service.withdraw_review(assignment_id, user_id)

    if not assignment:
        raise ErrorResponse("撤回失败（无权限或评审不存在）", 400)

    return assignment


@router.get("/user/pending-reviews")
def get_user_pending_reviews(
    project_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """获取当前用户的待处理评审列表。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    reviews = db_service.get_user_pending_reviews(user_id, project_id)
    return reviews
