"""
Event Store 模块

提供基于事件的持久化存储服务，支持：
- 仅追加的事件写入
- 事件流重放
- 状态快照存储
"""

from .event_store import EventStore

__all__ = ["EventStore"]
