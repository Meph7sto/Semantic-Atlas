"""
冲突分析路由
对应 Flask blueprint: conflict_bp (url_prefix="/api/conflict")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/conflict", tags=["conflict"])

# 路由将在 Phase 2 中迁移
