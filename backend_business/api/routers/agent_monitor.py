"""
Agent 监控路由
对应 Flask blueprint: agent_monitor_bp (url_prefix="/api/agent-monitor")
"""

from fastapi import APIRouter

router = APIRouter(prefix="/api/agent-monitor", tags=["agent-monitor"])

# 路由将在 Phase 2 中迁移
