"""Agent message protocol definition.
Agent 消息协议定义。
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class MessageType(str, Enum):
    """Message types for agent communication.
    Agent 通信的消息类型。
    """

    REQUEST = "request"           # Request another agent to perform a task; 请求另一个 Agent 执行任务
    RESPONSE = "response"         # Response to a request; 对请求的响应
    NOTIFY = "notify"             # One-way notification (no response expected); 单向通知（不期望响应）
    VOTE = "vote"                 # Voting in a group decision; 群组决策中的投票
    HEARTBEAT = "heartbeat"       # Keep-alive signal; 心跳信号
    TASK_RESULT = "task_result"   # Result of a completed task; 已完成任务的结果


@dataclass
class AgentMessage:
    """Unified message format for inter-agent communication.
    Agent 间通信的统一消息格式。
    """

    message_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:16]}")
    channel_id: str = ""  # 消息所属的频道 ID
    sender_id: str = ""  # 发送者 Agent ID
    message_type: MessageType = MessageType.NOTIFY  # 消息类型
    content: Dict[str, Any] = field(default_factory=dict)  # 消息内容载荷
    reply_to: Optional[str] = None  # 关联的原始消息 ID（用于回复）
    timestamp: datetime = field(default_factory=datetime.now)  # 发送时间戳
    metadata: Dict[str, Any] = field(default_factory=dict)  # 额外的元数据

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization.
        转换为字典以进行 JSON 序列化。
        """
        return {
            "message_id": self.message_id,
            "channel_id": self.channel_id,
            "sender_id": self.sender_id,
            "message_type": self.message_type.value,
            "content": self.content,
            "reply_to": self.reply_to,
            "timestamp": self.timestamp.isoformat(),
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AgentMessage":
        """Create from dictionary.
        从字典创建消息对象。
        """
        return cls(
            message_id=data.get("message_id", f"msg_{uuid.uuid4().hex[:16]}"),
            channel_id=data.get("channel_id", ""),
            sender_id=data.get("sender_id", ""),
            message_type=MessageType(data.get("message_type", "notify")),
            content=data.get("content", {}),
            reply_to=data.get("reply_to"),
            timestamp=datetime.fromisoformat(data["timestamp"]) if "timestamp" in data else datetime.now(),
            metadata=data.get("metadata", {}),
        )
