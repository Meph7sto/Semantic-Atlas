"""
需求分析路由
对应 Flask blueprint: analysis_bp (url_prefix="/api")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["analysis"])

# 路由将在 Phase 2 中迁移
# @router.post("/analysis/start")
# async def start_analysis():
#     pass
