"""
RequirementActor 开发态追踪广播。

用于将 Actor 生命周期事件推送给调试端（WebSocket）。
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Set

_SUBSCRIBERS: Set[asyncio.Queue] = set()
_QUEUE_MAX_SIZE = 200


def subscribe() -> asyncio.Queue:
    """注册一个追踪订阅队列。"""
    queue: asyncio.Queue = asyncio.Queue(maxsize=_QUEUE_MAX_SIZE)
    _SUBSCRIBERS.add(queue)
    return queue


def unsubscribe(queue: asyncio.Queue) -> None:
    """取消一个追踪订阅队列。"""
    _SUBSCRIBERS.discard(queue)


def emit_actor_trace(requirement_id: str, stage: str, level: str = "info", **details: Any) -> None:
    """
    广播一条 Actor 调试追踪事件。

    Args:
        requirement_id: 需求 ID
        stage: 生命周期阶段
        level: 日志级别（info/warning/error）
        **details: 扩展字段
    """
    payload: Dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "requirement_id": requirement_id,
        "stage": stage,
        "level": level,
        **details,
    }

    if not _SUBSCRIBERS:
        return

    for queue in list(_SUBSCRIBERS):
        try:
            if queue.full():
                queue.get_nowait()
            queue.put_nowait(payload)
        except Exception:
            # 调试广播不应影响主链路
            continue

