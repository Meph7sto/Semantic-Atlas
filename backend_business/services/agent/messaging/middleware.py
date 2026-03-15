"""Middleware pipeline for the message bus.

Each middleware receives a message before/after delivery and can
inspect, modify, or block it.  Middlewares are executed in registration
order (first-registered runs first on pre_publish, last on post_publish).
"""

import logging
import time
from collections import defaultdict
from typing import Optional

from .message import AgentMessage
from .channel import channel_manager

logger = logging.getLogger(__name__)


class Middleware:
    """Base class for message bus middlewares."""

    name: str = "base"

    def pre_publish(self, message: AgentMessage) -> Optional[AgentMessage]:
        """Called before a message is routed/delivered.

        Return the (possibly modified) message to continue, or ``None``
        to block the message entirely.
        """
        return message

    def post_publish(self, message: AgentMessage, recipient_count: int) -> None:
        """Called after a message has been delivered to all recipients."""


# ======================================================================
# Built-in middlewares
# ======================================================================


class LoggingMiddleware(Middleware):
    """Logs every published message for observability / auditing."""

    name = "logging"

    def pre_publish(self, message: AgentMessage) -> Optional[AgentMessage]:
        logger.info(
            "[MessageBus] PUBLISH  msg=%s  type=%s  sender=%s  channel=%s  reply_to=%s",
            message.message_id,
            message.message_type.value if hasattr(message.message_type, "value") else message.message_type,
            message.sender_id,
            message.channel_id,
            message.reply_to or "-",
        )
        return message

    def post_publish(self, message: AgentMessage, recipient_count: int) -> None:
        logger.info(
            "[MessageBus] DELIVERED  msg=%s  -> %d recipient(s)",
            message.message_id,
            recipient_count,
        )


class RateLimitMiddleware(Middleware):
    """Simple per-agent rate limiter (token-bucket-ish).

    Allows *max_per_window* messages per *window_seconds* per sender.
    Excess messages are logged as warnings but still delivered (soft limit).
    """

    name = "rate_limit"

    def __init__(self, max_per_window: int = 100, window_seconds: float = 60.0):
        self._max = max_per_window
        self._window = window_seconds
        self._buckets: dict[str, list[float]] = defaultdict(list)

    def pre_publish(self, message: AgentMessage) -> Optional[AgentMessage]:
        now = time.monotonic()
        bucket = self._buckets[message.sender_id]

        # Prune entries outside the window
        bucket[:] = [t for t in bucket if now - t < self._window]

        if len(bucket) >= self._max:
            logger.warning(
                "[RateLimit] Agent %s exceeded %d msgs / %.0fs window",
                message.sender_id,
                self._max,
                self._window,
            )
            # Soft limit: still allow, but warn.  Change to return None to hard-block.

        bucket.append(now)
        return message


class AuthorizationMiddleware(Middleware):
    """Basic membership-based authorization.

    A sender must be a member of the target channel, except for trusted
    system senders used by infrastructure components.
    """

    name = "authorization"

    def __init__(self, trusted_senders: Optional[set[str]] = None) -> None:
        self._trusted_senders = trusted_senders or {"system", "supervisor"}

    def pre_publish(self, message: AgentMessage) -> Optional[AgentMessage]:
        if message.sender_id in self._trusted_senders:
            return message

        channel = channel_manager.get_channel(message.channel_id)
        if channel is None:
            # Let bus decide how to handle unknown channels.
            return message

        if not channel.has_member(message.sender_id):
            logger.warning(
                "[Auth] Blocked message %s: sender %s is not a member of channel %s",
                message.message_id,
                message.sender_id,
                message.channel_id,
            )
            return None

        return message


class MetricsMiddleware(Middleware):
    """Collects simple in-memory counters for monitoring."""

    name = "metrics"

    def __init__(self) -> None:
        self.total_published: int = 0
        self.total_delivered: int = 0
        self.by_type: dict[str, int] = defaultdict(int)
        self.by_sender: dict[str, int] = defaultdict(int)

    def pre_publish(self, message: AgentMessage) -> Optional[AgentMessage]:
        self.total_published += 1
        msg_type = message.message_type.value if hasattr(message.message_type, "value") else str(message.message_type)
        self.by_type[msg_type] += 1
        self.by_sender[message.sender_id] += 1
        return message

    def post_publish(self, message: AgentMessage, recipient_count: int) -> None:
        self.total_delivered += recipient_count

    def snapshot(self) -> dict:
        return {
            "total_published": self.total_published,
            "total_delivered": self.total_delivered,
            "by_type": dict(self.by_type),
            "by_sender": dict(self.by_sender),
        }
