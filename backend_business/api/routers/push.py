"""
推送通知路由
对应 Flask blueprint: push_bp (url_prefix="/api/push")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/push", tags=["push"])

# 路由将在 Phase 2 中迁移
