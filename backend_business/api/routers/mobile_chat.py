"""
移动端对话路由
对应 Flask blueprint: mobile_chat_bp (url_prefix="/api/mobile")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/mobile", tags=["mobile-chat"])

# 路由将在 Phase 2 中迁移
