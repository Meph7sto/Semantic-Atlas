"""
权限管理路由聚合
统一 v2 前缀：/api/v2/permission/*
"""

from fastapi import APIRouter

from backend_business.services.db_service import db_service as _db_service

db_service = _db_service


def get_db_service():
    """获取当前数据库服务实例，支持在测试中 monkeypatch package 级变量。"""
    return db_service


def check_project_access(project_id: str, user_id: str) -> bool:
    """检查用户是否有访问项目的权限。"""
    service = get_db_service()
    user = service.get_user_by_id(user_id)
    return service.can_access_project(project_id, user_id, user)


from . import baselines, change_requests, context, members, reviews

router = APIRouter(prefix="/api/v2/permission", tags=["permission"])
router.include_router(members.router)
router.include_router(reviews.router)
router.include_router(baselines.router)
router.include_router(change_requests.router)
router.include_router(context.router)
