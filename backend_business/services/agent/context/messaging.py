"""Messaging context - state for inter-agent communication."""

from dataclasses import dataclass, field
from typing import List, Optional


@dataclass
class MessagingContext:
    """Carries channel / conversation info when an agent participates in messaging."""

    channel_id: str
    channel_type: str = "direct"                    # direct / group / broadcast
    peer_agents: List[str] = field(default_factory=list)
    reply_to_message_id: Optional[str] = None       # replying to a specific message
    thread_id: Optional[str] = None                 # sub-thread within a group channel
