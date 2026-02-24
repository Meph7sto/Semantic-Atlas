"""
项目管理路由
对应 Flask blueprint: manage_bp (url_prefix="/api/manage")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/manage", tags=["manage"])

# 路由将在 Phase 2 中迁移
