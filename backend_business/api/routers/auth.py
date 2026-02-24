"""
认证路由
对应 Flask blueprint: auth_bp (url_prefix="/api")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["auth"])

# 路由将在 Phase 2 中迁移
# @router.post("/auth/login")
# async def login():
#     pass
