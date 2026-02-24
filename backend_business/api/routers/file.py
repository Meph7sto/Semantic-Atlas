"""
文件上传/下载路由
对应 Flask blueprint: file_bp (url_prefix="/api")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["file"])

# 路由将在 Phase 2 中迁移
