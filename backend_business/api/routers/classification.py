"""
需求分类路由
对应 Flask blueprint: classification_bp (url_prefix="/api/classification")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/classification", tags=["classification"])

# 路由将在 Phase 2 中迁移
