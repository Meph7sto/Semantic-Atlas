"""
权限管理 - 权限上下文
"""

from fastapi import APIRouter, Depends

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from . import get_db_service

router = APIRouter()


@router.get("/projects/{project_id}/context")
def get_user_context(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取用户在项目中的权限上下文。"""
    db_service = get_db_service()
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)

    if not user:
        raise ErrorResponse("用户不存在", 404)
    if not db_service.can_access_project(project_id, user_id, user):
        raise ErrorResponse("无访问项目权限", 403)

    context = db_service.get_user_context(project_id, user_id, user)
    return context
