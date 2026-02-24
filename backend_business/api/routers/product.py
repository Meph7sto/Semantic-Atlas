"""
产品管理路由
对应 Flask blueprint: product_bp (url_prefix="/api/product")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/product", tags=["product"])

# 路由将在 Phase 2 中迁移
