"""
KB Service - 配置常量

包含知识库服务的默认配置参数
"""

import os

# ========================
# 配置常量
# ========================
DEFAULT_EMBEDDING_MODEL = os.getenv(
    "KB_EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)
DEFAULT_PERSIST_DIR = "data/kb_indexes"
