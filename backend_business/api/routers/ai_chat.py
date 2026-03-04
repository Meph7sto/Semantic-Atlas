"""
AI 对话路由
对应 Flask blueprint: ai_chat_bp (url_prefix="/api/ai-chat")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/ai-chat", tags=["ai-chat"])

# 路由将在 Phase 2 中迁移
