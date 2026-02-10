"""Messaging package - bus, channels, and message definitions.
消息包 - 总线、频道和消息定义。
"""

from backend_business.services.agent.messaging.message import AgentMessage, MessageType
from backend_business.services.agent.messaging.channel import Channel, ChannelType, channel_manager
from backend_business.services.agent.messaging.bus import message_bus

__all__ = [
    "AgentMessage",
    "MessageType",
    "Channel",
    "ChannelType",
    "channel_manager",
    "message_bus",
]
