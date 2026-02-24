"""
权限管理路由
对应 Flask blueprint: permission_bp (url_prefix="/api/permission")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/permission", tags=["permission"])

# 路由将在 Phase 2 中迁移
