"""Message bus - central hub for agent communication.

This is the **core routing engine** of the multi-agent architecture.
All inter-agent messages flow through the bus, which:

1. Runs the middleware pipeline (logging, rate-limit …)
2. Delegates recipient resolution to the Router
3. Delivers to subscriber callbacks
4. Stores history for replay / audit

Supports:
- Async notification (fire-and-forget via ``send_notify``)
- Synchronous request-response (``send_request`` + ``wait_for_response``)
"""

import logging
import json
import threading
from collections import defaultdict, deque
from typing import Any, Callable, Deque, Dict, List, Optional

from backend_business.services.db_service import db_service
from .channel import channel_manager, Channel, ChannelType
from .message import AgentMessage, MessageType
from .router import MessageRouter
from .middleware import (
    Middleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    AuthorizationMiddleware,
    MetricsMiddleware,
)

logger = logging.getLogger(__name__)


class MessageBus:
    """Central message bus for routing messages between agents.

    Unlike the previous implementation, the bus now:
    - Uses ``MessageRouter`` for recipient resolution instead of inline logic.
    - Runs a configurable middleware pipeline before/after every publish.
    - Supports blocking ``wait_for_response`` for synchronous request-response.
    """

    def __init__(self, max_history: int = 1000) -> None:
        # Agent callbacks
        self._subscribers: Dict[str, List[Callable[[AgentMessage], None]]] = defaultdict(list)

        # History / audit
        self._message_history: Deque[AgentMessage] = deque(maxlen=max_history)
        self._message_index: Dict[str, AgentMessage] = {}  # message_id -> message

        # Synchronous request-response support
        self._pending_requests: Dict[str, AgentMessage] = {}
        self._response_events: Dict[str, threading.Event] = {}
        self._response_store: Dict[str, AgentMessage] = {}

        # Router & middlewares
        self._router = MessageRouter()
        self._middlewares: List[Middleware] = []

        # Install default middlewares
        self.add_middleware(LoggingMiddleware())
        self.add_middleware(RateLimitMiddleware())
        self.add_middleware(AuthorizationMiddleware())
        self._metrics = MetricsMiddleware()
        self.add_middleware(self._metrics)

    # ==================================================================
    # Middleware management
    # ==================================================================

    def add_middleware(self, mw: Middleware) -> None:
        self._middlewares.append(mw)

    def remove_middleware(self, name: str) -> None:
        self._middlewares = [m for m in self._middlewares if m.name != name]

    @property
    def metrics(self) -> MetricsMiddleware:
        return self._metrics

    # ==================================================================
    # Router access
    # ==================================================================

    @property
    def router(self) -> MessageRouter:
        return self._router

    # ==================================================================
    # Subscription
    # ==================================================================

    def subscribe(self, agent_id: str, callback: Callable[[AgentMessage], None]) -> None:
        """Subscribe an agent to receive messages."""
        if callback not in self._subscribers[agent_id]:
            self._subscribers[agent_id].append(callback)
            logger.info("Agent %s subscribed to message bus", agent_id)

    def unsubscribe(self, agent_id: str, callback: Optional[Callable[[AgentMessage], None]] = None) -> None:
        """Unsubscribe an agent from receiving messages."""
        if callback:
            if callback in self._subscribers[agent_id]:
                self._subscribers[agent_id].remove(callback)
        else:
            self._subscribers.pop(agent_id, None)
        logger.info("Agent %s unsubscribed from message bus", agent_id)

    def is_subscribed(self, agent_id: str) -> bool:
        return bool(self._subscribers.get(agent_id))

    # ==================================================================
    # Publishing (core)
    # ==================================================================

    def publish(self, message: AgentMessage) -> str:
        """Publish a message through the full pipeline.

        1. Run pre_publish middlewares (may block)
        2. Resolve recipients via Router
        3. Deliver to subscriber callbacks
        4. Fulfil pending synchronous waits
        5. Run post_publish middlewares
        """

        # 1) Pre-publish middleware pipeline
        for mw in self._middlewares:
            result = mw.pre_publish(message)
            if result is None:
                logger.info("Message %s blocked by middleware '%s'", message.message_id, mw.name)
                return message.message_id
            message = result

        # 2) Store in history + index
        self._message_history.append(message)
        self._message_index[message.message_id] = message

        # 3) Resolve recipients via router
        channel = channel_manager.get_channel(message.channel_id)
        if not channel:
            logger.warning("Channel %s not found for message %s", message.channel_id, message.message_id)
            return message.message_id

        channel_manager.sync_channel(channel.channel_id, replace_members=False)
        self._persist_message(message)

        recipients = self._router.resolve_recipients(message, channel)

        # Track requests before delivery so nested RESPONSE handling can pop it.
        if message.message_type == MessageType.REQUEST:
            self._pending_requests[message.message_id] = message

        # For RESPONSE messages, narrow down to only the original requester
        if message.message_type == MessageType.RESPONSE and message.reply_to:
            original = self._pending_requests.get(message.reply_to) or self.get_message(message.reply_to)
            if original:
                recipients = [original.sender_id]

        # 4) Deliver to subscriber callbacks
        delivered = 0
        for recipient_id in recipients:
            callbacks = self._subscribers.get(recipient_id, [])
            for callback in callbacks:
                try:
                    callback(message)
                    delivered += 1
                except Exception as e:
                    logger.error("Error delivering msg %s to %s: %s", message.message_id, recipient_id, e)

        # 5) Track requests / fulfil responses
        if message.message_type == MessageType.RESPONSE and message.reply_to:
            self._pending_requests.pop(message.reply_to, None)
            # Fulfil any synchronous waiter
            if message.reply_to in self._response_events:
                self._response_store[message.reply_to] = message
                self._response_events[message.reply_to].set()

        # 6) Post-publish middleware pipeline
        for mw in self._middlewares:
            try:
                mw.post_publish(message, delivered)
            except Exception as e:
                logger.error("post_publish error in middleware '%s': %s", mw.name, e)

        return message.message_id

    def _persist_message(self, message: AgentMessage) -> None:
        """Persist message to DB for audit/replay when DB is configured."""
        if not db_service:
            return

        msg_type = message.message_type.value if hasattr(message.message_type, "value") else str(message.message_type)
        try:
            with db_service._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO agent_messages (
                            message_id, channel_id, sender_id, message_type, content, reply_to, metadata
                        )
                        VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s::jsonb)
                        ON CONFLICT (message_id) DO NOTHING
                        """,
                        (
                            message.message_id,
                            message.channel_id,
                            message.sender_id,
                            msg_type,
                            json.dumps(message.content or {}, ensure_ascii=False),
                            message.reply_to,
                            json.dumps(message.metadata or {}, ensure_ascii=False),
                        ),
                    )
        except Exception as e:
            logger.warning("Failed to persist message %s: %s", message.message_id, e)

    # ==================================================================
    # High-level send helpers
    # ==================================================================

    def send_request(
        self,
        sender_id: str,
        recipient_id: str,
        content: Dict,
        channel_id: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send a REQUEST and return its message_id for tracking."""
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
        """Send a RESPONSE to a previous request."""
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
        """Send a one-way notification (fire-and-forget)."""
        message = AgentMessage(
            channel_id=channel_id,
            sender_id=sender_id,
            message_type=MessageType.NOTIFY,
            content=content,
        )
        return self.publish(message)

    # ==================================================================
    # Synchronous request-response
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

        Returns the response AgentMessage, or None on timeout.
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
    # ==================================================================

    def get_history(
        self,
        channel_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[AgentMessage]:
        """Get message history, optionally filtered by channel."""
        messages = list(self._message_history)
        if channel_id:
            messages = [m for m in messages if m.channel_id == channel_id]
        return messages[-limit:]

    def get_message(self, message_id: str) -> Optional[AgentMessage]:
        """Get a specific message by ID (O(1) via index)."""
        return self._message_index.get(message_id)


# Global singleton instance
message_bus = MessageBus()
