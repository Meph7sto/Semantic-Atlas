"""Message routing strategies for the message bus.

Routes messages to the correct recipients based on channel type,
message type, and custom routing rules.
"""

import logging
from typing import Dict, List, Optional, Callable

from .message import AgentMessage, MessageType
from .channel import Channel, ChannelType

logger = logging.getLogger(__name__)


class RoutingRule:
    """A single routing rule: if predicate matches, override/filter recipients."""

    def __init__(
        self,
        name: str,
        predicate: Callable[[AgentMessage, Channel], bool],
        resolver: Callable[[AgentMessage, Channel, List[str]], List[str]],
        priority: int = 0,
    ):
        self.name = name
        self.predicate = predicate
        self.resolver = resolver
        self.priority = priority


class MessageRouter:
    """Determines who receives a message based on channel, message type, and rules.

    The router applies built-in routing logic first (channel-type based), then
    applies any custom rules in priority order.
    """

    def __init__(self) -> None:
        self._rules: List[RoutingRule] = []

    def add_rule(self, rule: RoutingRule) -> None:
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, name: str) -> None:
        self._rules = [r for r in self._rules if r.name != name]

    # ------------------------------------------------------------------
    # Core routing
    # ------------------------------------------------------------------

    def resolve_recipients(
        self,
        message: AgentMessage,
        channel: Channel,
    ) -> List[str]:
        """Return the list of agent_ids that should receive *message*."""

        # 1) Built-in routing by channel type
        recipients = self._builtin_route(message, channel)

        # 2) Apply custom rules in priority order
        for rule in self._rules:
            try:
                if rule.predicate(message, channel):
                    recipients = rule.resolver(message, channel, recipients)
                    logger.debug(
                        "Routing rule '%s' applied -> %d recipients",
                        rule.name,
                        len(recipients),
                    )
            except Exception as e:
                logger.error("Routing rule '%s' failed: %s", rule.name, e)

        return recipients

    # ------------------------------------------------------------------
    # Built-in strategies
    # ------------------------------------------------------------------

    def _builtin_route(
        self,
        message: AgentMessage,
        channel: Channel,
    ) -> List[str]:
        """Default channel-type-aware routing."""

        all_members = channel.members

        # Exclude sender (never deliver a message back to its author)
        candidates = [m for m in all_members if m != message.sender_id]

        # RESPONSE → only to original requester
        if message.message_type == MessageType.RESPONSE and message.reply_to:
            # The caller (bus) will resolve the original sender via _pending_requests
            # For now, return candidates as-is; the bus can narrow them down.
            pass

        # BROADCAST → all members, including sender
        if channel.channel_type == ChannelType.BROADCAST:
            candidates = list(all_members)

        # DIRECT → the single peer
        if channel.channel_type == ChannelType.DIRECT:
            candidates = [m for m in all_members if m != message.sender_id]

        return candidates
