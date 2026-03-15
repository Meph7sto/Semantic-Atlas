"""
权限管理 - 基线管理
"""

from fastapi import APIRouter, Depends, Query

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.permission_schemas import CreateBaselineRequest
from . import check_project_access, get_db_service

router = APIRouter()


@router.post("/projects/{project_id}/baselines")
def create_baseline(
    project_id: str,
    req: CreateBaselineRequest,
    current_user: dict = Depends(get_current_user),
):
    """创建基线。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    if not db_service.check_permission(project_id, user_id, "req:baseline_manage"):
        raise ErrorResponse("无管理基线权限", 403)

    version = req.version
    existing = db_service.get_baseline_by_version(project_id, version)
    if existing:
        raise ErrorResponse("版本号已存在", 400)

    baseline = db_service.create_baseline(project_id, version, user_id, req.locked)
    if not baseline:
        raise ErrorResponse("创建基线失败", 400)

    return baseline


@router.get("/projects/{project_id}/baselines")
def list_project_baselines(
    project_id: str,
    include_locked: bool = Query(True),
    current_user: dict = Depends(get_current_user),
):
    """列出项目的所有基线。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
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
    """锁定基线。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    baseline = db_service.get_baseline(baseline_id)
    if not baseline:
        raise ErrorResponse("基线不存在", 404)

    project_id = baseline["project_id"]
    if not db_service.check_permission(project_id, user_id, "req:baseline_manage"):
        raise ErrorResponse("无管理基线权限", 403)

    updated_baseline = db_service.lock_baseline(baseline_id, user_id)
    if not updated_baseline:
        raise ErrorResponse("锁定基线失败", 400)

    return updated_baseline


@router.post("/baselines/{baseline_id}/unlock")
def unlock_baseline(
    baseline_id: str,
    current_user: dict = Depends(get_current_user),
):
    """解锁基线。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    baseline = db_service.get_baseline(baseline_id)
    if not baseline:
        raise ErrorResponse("基线不存在", 404)

    project_id = baseline["project_id"]
    if not db_service.check_permission(project_id, user_id, "req:baseline_manage"):
        raise ErrorResponse("无管理基线权限", 403)

    updated_baseline = db_service.unlock_baseline(baseline_id, user_id)
    if not updated_baseline:
        raise ErrorResponse("解锁基线失败", 400)

    return updated_baseline
