"""
需求管理路由
对应 Flask blueprint: requirements_bp (url_prefix="/api")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["requirements"])

# 路由将在 Phase 2 中迁移
