"""Message routing strategies for the message bus.
消息总线的消息路由策略。

Routes messages to the correct recipients based on channel type,
message type, and custom routing rules.
基于频道类型、消息类型和自定义路由规则，将消息路由到正确的接收者。
"""

import logging
from typing import Dict, List, Optional, Callable

from .message import AgentMessage, MessageType
from .channel import Channel, ChannelType

logger = logging.getLogger(__name__)


class RoutingRule:
    """A single routing rule: if predicate matches, override/filter recipients.
    单个路由规则：如果谓词匹配，则覆盖/过滤接收者。
    """

    def __init__(
        self,
        name: str,
        predicate: Callable[[AgentMessage, Channel], bool],
        resolver: Callable[[AgentMessage, Channel, List[str]], List[str]],
        priority: int = 0,
    ):
        self.name = name
        self.predicate = predicate  # 判断规则是否适用
        self.resolver = resolver  # 解析接收者列表
        self.priority = priority  # 规则优先级


class MessageRouter:
    """Determines who receives a message based on channel, message type, and rules.
    基于频道、消息类型和规则确定谁接收消息。

    The router applies built-in routing logic first (channel-type based), then
    applies any custom rules in priority order.
    路由器首先应用内置路由逻辑（基于频道类型），然后按优先级顺序应用任何自定义规则。
    """

    def __init__(self) -> None:
        self._rules: List[RoutingRule] = []

    def add_rule(self, rule: RoutingRule) -> None:
        """Add a custom routing rule.
        添加自定义路由规则。
        """
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority, reverse=True)

    def remove_rule(self, name: str) -> None:
        """Remove a routing rule by name.
        按名称移除路由规则。
        """
        self._rules = [r for r in self._rules if r.name != name]

    # ------------------------------------------------------------------
    # Core routing
    # 核心路由
    # ------------------------------------------------------------------

    def resolve_recipients(
        self,
        message: AgentMessage,
        channel: Channel,
    ) -> List[str]:
        """Return the list of agent_ids that should receive *message*.
        返回应接收 *message* 的 agent_id 列表。
        """

        # 1) Built-in routing by channel type
        # 1) 基于频道类型的内置路由
        recipients = self._builtin_route(message, channel)

        # 2) Apply custom rules in priority order
        # 2) 按优先级应用自定义规则
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
    # 内置策略
    # ------------------------------------------------------------------

    def _builtin_route(
        self,
        message: AgentMessage,
        channel: Channel,
    ) -> List[str]:
        """Default channel-type-aware routing.
        默认的频道类型感知路由。
        """

        all_members = channel.members

        # Exclude sender (never deliver a message back to its author)
        # 排除发送者（永远不把消息发回给作者）
        candidates = [m for m in all_members if m != message.sender_id]

        # RESPONSE → only to original requester
        # RESPONSE → 仅发给原始请求者
        if message.message_type == MessageType.RESPONSE and message.reply_to:
            # The caller (bus) will resolve the original sender via _pending_requests
            # For now, return candidates as-is; the bus can narrow them down.
            # 调用者（总线）将通过 _pending_requests 解析原始发送者
            # 目前按原样返回候选者；总线可以缩小范围。
            pass

        # BROADCAST → all members, including sender
        # BROADCAST → 所有成员，包括发送者
        if channel.channel_type == ChannelType.BROADCAST:
            candidates = list(all_members)

        # DIRECT → the single peer
        # DIRECT → 单个对等方
        if channel.channel_type == ChannelType.DIRECT:
            candidates = [m for m in all_members if m != message.sender_id]

        return candidates
