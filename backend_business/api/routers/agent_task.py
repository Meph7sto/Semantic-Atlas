"""
Agent 任务路由
对应 Flask blueprint: agent_task_bp (url_prefix="/api/agent-tasks")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/agent-tasks", tags=["agent-task"])

# 路由将在 Phase 2 中迁移
