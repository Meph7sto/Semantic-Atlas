"""
需求去重路由
对应 Flask blueprint: dedup_bp (url_prefix="/api/dedup")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/dedup", tags=["deduplication"])

# 路由将在 Phase 2 中迁移
