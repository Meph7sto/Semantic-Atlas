"""
权限管理 - 项目成员管理
"""

from fastapi import APIRouter, Depends, Query

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.permission_schemas import (
    AddProjectMemberRequest,
    SetUserRolesRequest,
)
from . import check_project_access, get_db_service

router = APIRouter()


@router.post("/projects/{project_id}/members")
def add_project_member(
    project_id: str,
    req: AddProjectMemberRequest,
    current_user: dict = Depends(get_current_user),
):
    """添加项目成员。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]

    if not db_service.check_permission(project_id, user_id, "proj:add_member"):
        raise ErrorResponse("无添加成员权限", 403)

    target_user_id = req.user_id
    target_user = db_service.get_user_by_id(target_user_id)
    if not target_user:
        raise ErrorResponse("目标用户不存在", 404)

    member = db_service.add_project_member(project_id, target_user_id, user_id)
    if not member:
        raise ErrorResponse("添加成员失败（可能已是成员）", 400)

    roles = req.member_roles
    if roles:
        for role_id in roles:
            db_service.assign_role(project_id, target_user_id, role_id, user_id)

    result = db_service.list_project_members(project_id, include_roles=True)
    member_info = next((m for m in result["members"] if m["user_id"] == target_user_id), member)

    return member_info


@router.get("/projects/{project_id}/members")
def list_project_members(
    project_id: str,
    include_roles: bool = Query(False),
    current_user: dict = Depends(get_current_user),
):
    """列出项目成员。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
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
    """移除项目成员。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    operator_id = current_user["user_id"]

    if operator_id == user_id:
        raise ErrorResponse("不能移除自己", 400)

    if not db_service.check_permission(project_id, operator_id, "proj:remove_member"):
        raise ErrorResponse("无移除成员权限", 403)

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
    """设置用户角色（全量替换）。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    operator_id = current_user["user_id"]

    if not db_service.check_permission(project_id, operator_id, "proj:add_member"):
        raise ErrorResponse("无管理成员权限", 403)

    result = db_service.set_user_roles(project_id, user_id, req.roles, operator_id)
    if "error" in result:
        raise ErrorResponse(result["error"], 400)

    return result
