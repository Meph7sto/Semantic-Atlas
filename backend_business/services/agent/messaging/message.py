"""Agent message protocol definition."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, Optional


class MessageType(str, Enum):
    """Message types for agent communication."""

    REQUEST = "request"           # Request another agent to perform a task
    RESPONSE = "response"         # Response to a request
    NOTIFY = "notify"             # One-way notification (no response expected)
    VOTE = "vote"                 # Voting in a group decision
    HEARTBEAT = "heartbeat"       # Keep-alive signal
    TASK_RESULT = "task_result"   # Result of a completed task


@dataclass
class AgentMessage:
    """Unified message format for inter-agent communication."""

    message_id: str = field(default_factory=lambda: f"msg_{uuid.uuid4().hex[:16]}")
    channel_id: str = ""
    sender_id: str = ""
    message_type: MessageType = MessageType.NOTIFY
    content: Dict[str, Any] = field(default_factory=dict)
    reply_to: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
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
        """Create from dictionary."""
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
