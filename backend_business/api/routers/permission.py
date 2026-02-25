"""
权限管理路由 - FastAPI 版本
对应 Flask blueprint: permission_bp (url_prefix="/api/permission")
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from backend_business.services.db_service import db_service
from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.permission_schemas import (
    AddProjectMemberRequest,
    ApproveChangeRequestRequest,
    ApproveReviewRequest,
    CreateBaselineRequest,
    CreateChangeRequestRequest,
    CreateReviewRequest,
    RejectChangeRequestRequest,
    RejectReviewRequest,
    SetUserRolesRequest,
)

router = APIRouter(prefix="/api/permission", tags=["permission"])


# ========================
# 辅助函数
# ========================

def check_project_access(project_id: str, user_id: str) -> bool:
    """检查用户是否有访问项目的权限"""
    return db_service.is_project_member(project_id, user_id)


# ========================
# 项目成员管理
# ========================

@router.post("/projects/{project_id}/members")
def add_project_member(
    project_id: str,
    req: AddProjectMemberRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    添加项目成员

    Request Body:
        {
            "user_id": "user-xxx",
            "member_roles": ["PO", "BA"]  # 可选：同时分配角色
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    # 检查是否有权限添加成员
    if not db_service.check_permission(project_id, user_id, "proj:add_member"):
        raise ErrorResponse("无添加成员权限", 403)

    target_user_id = req.user_id

    # 检查目标用户是否存在
    target_user = db_service.get_user_by_id(target_user_id)
    if not target_user:
        raise ErrorResponse("目标用户不存在", 404)

    # 添加成员
    member = db_service.add_project_member(project_id, target_user_id, user_id)
    if not member:
        raise ErrorResponse("添加成员失败（可能已是成员）", 400)

    # 如果指定了角色，批量分配
    roles = req.member_roles
    if roles:
        for role_id in roles:
            db_service.assign_role(project_id, target_user_id, role_id, user_id)

    # 返回包含角色的成员信息
    result = db_service.list_project_members(project_id, include_roles=True)
    member_info = next((m for m in result["members"] if m["user_id"] == target_user_id), member)

    return member_info


@router.get("/projects/{project_id}/members")
def list_project_members(
    project_id: str,
    include_roles: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    """
    列出项目成员

    Query Params:
        include_roles: 是否包含角色信息 (true/false)

    Response:
        {
            "success": true,
            "data": {
                "members": [...],
                "total": 10
            }
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    # 检查是否有访问项目的权限
    if not check_project_access(project_id, user_id):
        raise ErrorResponse("无访问项目权限", 403)

    result = db_service.list_project_members(
        project_id,
        include_roles=include_roles,
    )

    return result


@router.delete("/projects/{project_id}/members/{user_id}")
def remove_project_member(
    project_id: str,
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    移除项目成员

    Response:
        {
            "success": true,
            "data": {"removed": true}
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    operator_id = current_user["user_id"]

    # 不能移除自己
    if operator_id == user_id:
        raise ErrorResponse("不能移除自己", 400)

    # 检查是否有权限移除成员
    if not db_service.check_permission(project_id, operator_id, "proj:remove_member"):
        raise ErrorResponse("无移除成员权限", 403)

    # 移除成员
    success = db_service.remove_project_member(project_id, user_id)
    if not success:
        raise ErrorResponse("移除成员失败", 400)

    return {"removed": True}


@router.put("/projects/{project_id}/members/{user_id}/roles")
def set_user_roles(
    project_id: str,
    user_id: str,
    req: SetUserRolesRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    设置用户角色（全量替换）

    Request Body:
        {
            "roles": ["PO", "BA"]
        }

    Response:
        {
            "success": true,
            "data": {
                "added": [...],
                "removed": [...],
                "kept": [...]
            }
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    operator_id = current_user["user_id"]

    # 检查是否有权限管理成员
    if not db_service.check_permission(project_id, operator_id, "proj:add_member"):
        raise ErrorResponse("无管理成员权限", 403)

    roles = req.roles

    result = db_service.set_user_roles(project_id, user_id, roles, operator_id)

    if "error" in result:
        raise ErrorResponse(result["error"], 400)

    return result


# ========================
# 评审指派管理
# ========================

@router.post("/requirements/{requirement_id}/reviews")
def create_review_assignment(
    requirement_id: str,
    req: CreateReviewRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    创建评审指派

    Request Body:
        {
            "reviewer_id": "user-xxx",
            "seq": 1,
            "comment": "请评审此需求"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    reviewer_id = req.reviewer_id
    seq = req.seq
    comment = req.comment

    # 检查评审人是否存在
    reviewer = db_service.get_user_by_id(reviewer_id)
    if not reviewer:
        raise ErrorResponse("评审人不存在", 404)

    # 创建评审指派
    assignment = db_service.create_review_assignment(
        requirement_id=requirement_id,
        reviewer_id=reviewer_id,
        initiated_by=user_id,
        seq=seq,
        comment=comment,
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
    """
    列出需求的所有评审

    Query Params:
        status: 筛选状态 (PENDING, APPROVED, REJECTED, WITHDRAWN)

    Response:
        {
            "success": true,
            "data": [...]
        }
    """
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
    """
    通过评审

    Request Body:
        {
            "comment": "评审通过"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
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
    """
    驳回评审

    Request Body:
        {
            "comment": "评审驳回原因"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
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
    """
    撤回评审

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
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
    """
    获取当前用户的待处理评审列表

    Query Params:
        project_id: 项目 ID（可选）

    Response:
        {
            "success": true,
            "data": [...]
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    reviews = db_service.get_user_pending_reviews(user_id, project_id)

    return reviews


# ========================
# 基线管理
# ========================

@router.post("/projects/{project_id}/baselines")
def create_baseline(
    project_id: str,
    req: CreateBaselineRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    创建基线

    Request Body:
        {
            "version": "1.0.0",
            "locked": false
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    # 检查是否有权限管理基线
    if not db_service.check_permission(project_id, user_id, "req:baseline_manage"):
        raise ErrorResponse("无管理基线权限", 403)

    version = req.version
    locked = req.locked

    # 检查版本号是否已存在
    existing = db_service.get_baseline_by_version(project_id, version)
    if existing:
        raise ErrorResponse("版本号已存在", 400)

    baseline = db_service.create_baseline(project_id, version, user_id, locked)

    if not baseline:
        raise ErrorResponse("创建基线失败", 400)

    return baseline


@router.get("/projects/{project_id}/baselines")
def list_project_baselines(
    project_id: str,
    include_locked: bool = Query(True),
    current_user: dict = Depends(get_current_user),
):
    """
    列出项目的所有基线

    Query Params:
        include_locked: 是否包含已锁定的基线 (true/false，默认 true)

    Response:
        {
            "success": true,
            "data": [...]
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    # 检查是否有访问项目的权限
    if not check_project_access(project_id, user_id):
        raise ErrorResponse("无访问项目权限", 403)

    baselines = db_service.list_project_baselines(
        project_id,
        include_locked=include_locked,
    )

    return baselines


@router.post("/baselines/{baseline_id}/lock")
def lock_baseline(
    baseline_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    锁定基线

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    # 获取基线信息以获取项目 ID
    baseline = db_service.get_baseline(baseline_id)
    if not baseline:
        raise ErrorResponse("基线不存在", 404)

    project_id = baseline["project_id"]

    # 检查是否有权限管理基线
    if not db_service.check_permission(project_id, user_id, "req:baseline_manage"):
        raise ErrorResponse("无管理基线权限", 403)

    # 锁定基线
    updated_baseline = db_service.lock_baseline(baseline_id, user_id)

    if not updated_baseline:
        raise ErrorResponse("锁定基线失败", 400)

    return updated_baseline


@router.post("/baselines/{baseline_id}/unlock")
def unlock_baseline(
    baseline_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    解锁基线

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    # 获取基线信息以获取项目 ID
    baseline = db_service.get_baseline(baseline_id)
    if not baseline:
        raise ErrorResponse("基线不存在", 404)

    project_id = baseline["project_id"]

    # 检查是否有权限管理基线
    if not db_service.check_permission(project_id, user_id, "req:baseline_manage"):
        raise ErrorResponse("无管理基线权限", 403)

    # 解锁基线
    updated_baseline = db_service.unlock_baseline(baseline_id, user_id)

    if not updated_baseline:
        raise ErrorResponse("解锁基线失败", 400)

    return updated_baseline


# ========================
# 变更请求管理
# ========================

@router.post("/requirements/{requirement_id}/change-requests")
def create_change_request(
    requirement_id: str,
    req: CreateChangeRequestRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    创建变更请求

    Request Body:
        {
            "baseline_id": 123,
            "reason": "需要修改需求优先级",
            "change_summary": "将优先级从 3 改为 5"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    baseline_id = req.baseline_id
    reason = req.reason
    change_summary = req.change_summary

    # 检查基线是否存在
    baseline = db_service.get_baseline(baseline_id)
    if not baseline:
        raise ErrorResponse("基线不存在", 404)

    project_id = baseline["project_id"]

    # 检查是否有权限创建变更请求
    if not db_service.check_permission(project_id, user_id, "req:change_request"):
        raise ErrorResponse("无创建变更请求权限", 403)

    # 创建变更请求
    change_request = db_service.create_change_request(
        requirement_id=requirement_id,
        baseline_id=baseline_id,
        requested_by=user_id,
        reason=reason,
        change_summary=change_summary,
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
    """
    列出需求的所有变更请求

    Query Params:
        status: 筛选状态 (PENDING, APPROVED, REJECTED)

    Response:
        {
            "success": true,
            "data": [...]
        }
    """
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
    """
    批准变更请求

    Request Body:
        {
            "review_comment": "同意变更"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    review_comment = req.review_comment if req else None

    # 获取变更请求信息以获取项目 ID
    change_request = db_service.get_change_request(request_id)
    if not change_request:
        raise ErrorResponse("变更请求不存在", 404)

    project_id = change_request["project_id"]

    # 检查是否有权限批准变更
    if not db_service.check_permission(project_id, user_id, "req:change_approve"):
        raise ErrorResponse("无批准变更权限", 403)

    # 批准变更请求
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
    """
    驳回变更请求

    Request Body:
        {
            "review_comment": "驳回原因"
        }

    Response:
        {
            "success": true,
            "data": {...}
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    review_comment = req.review_comment if req else None

    # 获取变更请求信息以获取项目 ID
    change_request = db_service.get_change_request(request_id)
    if not change_request:
        raise ErrorResponse("变更请求不存在", 404)

    project_id = change_request["project_id"]

    # 检查是否有权限驳回变更
    if not db_service.check_permission(project_id, user_id, "req:change_reject"):
        raise ErrorResponse("无驳回变更权限", 403)

    # 驳回变更请求
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
    """
    获取待审批的变更请求列表

    Query Params:
        project_id: 项目 ID（可选）

    Response:
        {
            "success": true,
            "data": [...]
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    # 获取用户的所有项目（如果未指定项目 ID）
    if not project_id:
        projects = db_service.get_accessible_projects(user_id)
        # 过滤有权限的项目
        accessible_projects = []
        for p_id in projects:
            if db_service.check_permission(p_id, user_id, "req:change_approve"):
                accessible_projects.append(p_id)

        # 收集所有可访问项目的待审批变更请求
        all_requests = []
        for p_id in accessible_projects:
            requests = db_service.get_pending_change_requests(project_id=p_id)
            all_requests.extend(requests)
    else:
        # 检查是否有权限批准变更
        if not db_service.check_permission(project_id, user_id, "req:change_approve"):
            raise ErrorResponse("无查看待审批变更权限", 403)

        all_requests = db_service.get_pending_change_requests(project_id=project_id)

    return all_requests


# ========================
# 权限上下文
# ========================

@router.get("/projects/{project_id}/context")
def get_user_context(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    获取用户在项目中的权限上下文

    Response:
        {
            "success": true,
            "data": {
                "user_id": "user-xxx",
                "system_identity": "SYS_USER",
                "roles": ["PO", "BA"],
                "permissions": [...]
            }
        }
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)

    if not user:
        raise ErrorResponse("用户不存在", 404)

    context = db_service.get_user_context(project_id, user_id, user)

    return context
