"""Messaging context - state for inter-agent communication.
消息上下文 - Agent 间通信的状态。
"""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MessagingContext:
    """Carries channel / conversation info when an agent participates in messaging.
    当 Agent 参与消息传递时携带频道/对话信息。
    """

    channel_id: str  # 当前通信频道 ID
    channel_type: str = "direct"  # direct / group / broadcast; 直连 / 群组 / 广播
    peer_agents: List[str] = field(default_factory=list)  # 对方 Agent ID 列表
    reply_to_message_id: Optional[str] = None  # replying to a specific message; 回复特定消息 ID
    thread_id: Optional[str] = None  # sub-thread within a group channel; 群组频道内的子线程 ID
