"""Core Message Bus implementation.
核心消息总线实现。
"""

import logging
import threading
from typing import Any, Callable, Dict, List, Optional

from backend_business.services.agent.messaging.message import AgentMessage, MessageType
from backend_business.services.agent.messaging.channel import channel_manager, ChannelType
from backend_business.services.agent.messaging.middleware import (
    Middleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    AuthorizationMiddleware,
    MetricsMiddleware,
)
from backend_business.services.agent.messaging.router import MessageRouter

logger = logging.getLogger(__name__)


class MessageBus:
    """In-process message bus for agent communication.
    用于 Agent 通信的进程内消息总线。

    Responsibilities:
    职责：
    1. Manage subscriptions (agent_id -> callback)
       管理订阅（agent_id -> 回调）
    2. Route messages to recipients
       将消息路由到接收者
    3. Apply middleware pipeline (logging, auth, rate-limit)
       应用中间件管道（日志记录、授权、速率限制）
    4. Provide sync request-response helpers
       提供同步请求-响应辅助函数
    """

    def __init__(self) -> None:
        self._subscribers: Dict[str, List[Callable[[AgentMessage], None]]] = {}  # agent_id -> [callbacks]
        self._router = MessageRouter()
        self._middlewares: List[Middleware] = []

        # Request-Response correlation (for synchronous wait)
        # 请求-响应关联（用于同步等待）
        self._response_events: Dict[str, threading.Event] = {}  # message_id -> Event
        self._response_store: Dict[str, AgentMessage] = {}  # message_id -> ResponseMessage

        # Basic history (in-memory ring buffer)
        # 基本历史记录（内存环形缓冲区）
        self._message_history: List[AgentMessage] = []
        self._history_limit = 1000
        self._message_index: Dict[str, AgentMessage] = {}

        # Register default middlewares
        # 注册默认中间件
        self.add_middleware(LoggingMiddleware())
        self.add_middleware(RateLimitMiddleware())
        self.add_middleware(AuthorizationMiddleware())
        self.add_middleware(MetricsMiddleware())

    def add_middleware(self, middleware: Middleware) -> None:
        """Add a middleware to the pipeline.
        向管道添加中间件。
        """
        self._middlewares.append(middleware)

    def subscribe(self, agent_id: str, callback: Callable[[AgentMessage], None]) -> None:
        """Subscribe an agent to receive messages.
        订阅 Agent 以接收消息。
        """
        if agent_id not in self._subscribers:
            self._subscribers[agent_id] = []
        self._subscribers[agent_id].append(callback)

    def unsubscribe(self, agent_id: str, callback: Callable[[AgentMessage], None]) -> None:
        """Unsubscribe a callback.
        取消订阅回调。
        """
        if agent_id in self._subscribers:
            try:
                self._subscribers[agent_id].remove(callback)
            except ValueError:
                pass

    def publish(self, message: AgentMessage) -> str:
        """Publish a message to the bus.
        向总线发布消息。

        Returns the message_id.
        返回 message_id。
        """
        # 1. Pre-publish middleware
        # 1. 预发布中间件处理
        for mw in self._middlewares:
            message = mw.pre_publish(message)
            if message is None:
                # Middleware blocked the message
                # 中间件拦截了消息
                return ""

        # 2. Persist to history
        # 2. 持久化到历史记录
        self._message_history.append(message)
        self._message_index[message.message_id] = message
        if len(self._message_history) > self._history_limit:
            removed = self._message_history.pop(0)
            self._message_index.pop(removed.message_id, None)

        # 3. Resolve recipients
        # 3. 解析接收者
        channel = channel_manager.get_channel(message.channel_id)
        if not channel:
            # Create ad-hoc channel if needed, or fail? For now, fail soft.
            # 如果需要则创建临时频道，或者失败？目前暂时软失败。
            logger.warning("Unknown channel %s for message %s", message.channel_id, message.message_id)
            return message.message_id

        recipients = self._router.resolve_recipients(message, channel)

        # 4. Deliver
        # 4. 投递消息
        delivered_count = 0
        for recipient_id in recipients:
            callbacks = self._subscribers.get(recipient_id, [])
            for cb in callbacks:
                try:
                    cb(message)
                    delivered_count += 1
                except Exception as e:
                    logger.error("Error delivering message %s to %s: %s", message.message_id, recipient_id, e)

        # 5. Handle synchronous response correlation
        # 5. 处理同步响应关联
        if message.message_type == MessageType.RESPONSE and message.reply_to:
            if message.reply_to in self._response_events:
                self._response_store[message.reply_to] = message
                self._response_events[message.reply_to].set()

        # 6. Post-publish middleware
        # 6. 后发布中间件处理
        for mw in reversed(self._middlewares):
            mw.post_publish(message, delivered_count)

        return message.message_id

    # ==================================================================
    # Convenience senders
    # 便捷发送方法
    # ==================================================================

    def send_request(
        self,
        sender_id: str,
        recipient_id: str,
        content: Dict,
        channel_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a REQUEST message.
        发送 REQUEST 消息。
        """
        if not channel_id:
            channel = channel_manager.get_or_create_direct_channel(sender_id, recipient_id)
            channel_id = channel.channel_id

        message = AgentMessage(
            channel_id=channel_id,
            sender_id=sender_id,
            message_type=MessageType.REQUEST,
            content=content,
            metadata=metadata or {},
        )
        return self.publish(message)

    def send_response(
        self,
        sender_id: str,
        channel_id: str,
        reply_to: str,
        content: Dict,
    ) -> str:
        """Send a RESPONSE message.
        发送 RESPONSE 消息。
        """
        message = AgentMessage(
            channel_id=channel_id,
            sender_id=sender_id,
            message_type=MessageType.RESPONSE,
            content=content,
            reply_to=reply_to,
        )
        return self.publish(message)

    def send_notify(
        self,
        sender_id: str,
        channel_id: str,
        content: Dict,
    ) -> str:
        """Send a one-way notification (fire-and-forget).
        发送单向通知（发送即忘）。
        """
        message = AgentMessage(
            channel_id=channel_id,
            sender_id=sender_id,
            message_type=MessageType.NOTIFY,
            content=content,
        )
        return self.publish(message)

    # ==================================================================
    # Synchronous request-response
    # 同步请求-响应
    # ==================================================================

    def request_and_wait(
        self,
        sender_id: str,
        recipient_id: str,
        content: Dict,
        channel_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        timeout: float = 180.0,
    ) -> Optional[AgentMessage]:
        """Send a REQUEST and block until the matching RESPONSE arrives.
        发送 REQUEST 并阻塞直到收到匹配的 RESPONSE。

        Returns the response AgentMessage, or None on timeout.
        返回响应消息 AgentMessage，如果超时则返回 None。
        """
        if not channel_id:
            channel = channel_manager.get_or_create_direct_channel(sender_id, recipient_id)
            channel_id = channel.channel_id

        message = AgentMessage(
            channel_id=channel_id,
            sender_id=sender_id,
            message_type=MessageType.REQUEST,
            content=content,
            metadata=metadata or {},
        )

        event = threading.Event()
        self._response_events[message.message_id] = event

        try:
            self.publish(message)
            event.wait(timeout=timeout)
            return self._response_store.pop(message.message_id, None)
        finally:
            self._response_events.pop(message.message_id, None)

    # ==================================================================
    # History / lookup
    # 历史记录 / 查找
    # ==================================================================

    def get_history(
        self,
        channel_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[AgentMessage]:
        """Get message history, optionally filtered by channel.
        获取消息历史记录，可选择按频道过滤。
        """
        messages = list(self._message_history)
        if channel_id:
            messages = [m for m in messages if m.channel_id == channel_id]
        return messages[-limit:]

    def get_message(self, message_id: str) -> Optional[AgentMessage]:
        """Get a specific message by ID (O(1) via index).
        通过 ID 获取特定消息（通过索引 O(1)）。
        """
        return self._message_index.get(message_id)


# Global singleton instance
# 全局单例实例
message_bus = MessageBus()
