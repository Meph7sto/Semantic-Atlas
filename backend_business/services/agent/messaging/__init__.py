"""Multi-agent messaging infrastructure.

Provides the message bus, channels, routing, and middleware pipeline
that form the communication backbone for inter-agent collaboration.
"""

from .message import AgentMessage, MessageType
from .bus import message_bus, MessageBus
from .channel import Channel, ChannelType, channel_manager, ChannelManager
from .router import MessageRouter, RoutingRule
from .middleware import (
    Middleware,
    LoggingMiddleware,
    RateLimitMiddleware,
    AuthorizationMiddleware,
    MetricsMiddleware,
)

__all__ = [
    # Message protocol
    "AgentMessage",
    "MessageType",
    # Bus
    "MessageBus",
    "message_bus",
    # Channel
    "Channel",
    "ChannelType",
    "ChannelManager",
    "channel_manager",
    # Router
    "MessageRouter",
    "RoutingRule",
    # Middleware
    "Middleware",
    "LoggingMiddleware",
    "RateLimitMiddleware",
    "AuthorizationMiddleware",
    "MetricsMiddleware",
]
