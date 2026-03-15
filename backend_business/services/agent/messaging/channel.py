"""Channel management for agent communication."""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from backend_business.services.db_service import db_service

logger = logging.getLogger(__name__)


class ChannelType(str, Enum):
    """Channel types for different communication patterns."""

    DIRECT = "direct"        # 1:1 private channel
    GROUP = "group"          # Multi-agent collaboration
    BROADCAST = "broadcast"  # System-wide announcements


@dataclass
class Channel:
    """Represents a communication channel between agents."""

    channel_id: str = field(default_factory=lambda: f"ch_{uuid.uuid4().hex[:16]}")
    channel_type: ChannelType = ChannelType.DIRECT
    name: str = ""
    project_id: Optional[str] = None
    created_by: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    is_archived: bool = False
    members: List[str] = field(default_factory=list)  # List of agent_ids

    def add_member(self, agent_id: str) -> None:
        """Add an agent to the channel."""
        if agent_id not in self.members:
            self.members.append(agent_id)

    def remove_member(self, agent_id: str) -> None:
        """Remove an agent from the channel."""
        if agent_id in self.members:
            self.members.remove(agent_id)

    def has_member(self, agent_id: str) -> bool:
        """Check if an agent is a member of this channel."""
        return agent_id in self.members

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization."""
        return {
            "channel_id": self.channel_id,
            "channel_type": self.channel_type.value,
            "name": self.name,
            "project_id": self.project_id,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "is_archived": self.is_archived,
            "members": self.members,
        }


class ChannelManager:
    """Manages channels in memory (can be extended to persist in DB)."""

    def __init__(self):
        self._channels: Dict[str, Channel] = {}

    def _persist_channel(self, channel: Channel, replace_members: bool = True) -> None:
        """Persist channel + members to DB when DB is available."""
        if not db_service:
            return

        try:
            with db_service._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO agent_channels (
                            channel_id, channel_type, name, project_id, created_by, is_archived
                        )
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (channel_id)
                        DO UPDATE SET
                            channel_type = EXCLUDED.channel_type,
                            name = EXCLUDED.name,
                            project_id = EXCLUDED.project_id,
                            created_by = EXCLUDED.created_by,
                            is_archived = EXCLUDED.is_archived
                        """,
                        (
                            channel.channel_id,
                            channel.channel_type.value,
                            channel.name or None,
                            channel.project_id,
                            channel.created_by,
                            channel.is_archived,
                        ),
                    )

                    if replace_members:
                        cur.execute(
                            "DELETE FROM agent_channel_members WHERE channel_id = %s",
                            (channel.channel_id,),
                        )
                        for agent_id in channel.members:
                            cur.execute(
                                """
                                INSERT INTO agent_channel_members (channel_id, agent_id, role)
                                VALUES (%s, %s, 'member')
                                ON CONFLICT (channel_id, agent_id) DO NOTHING
                                """,
                                (channel.channel_id, agent_id),
                            )
        except Exception as e:
            logger.warning(
                "Failed to persist channel %s to DB: %s",
                channel.channel_id,
                e,
            )

    def create_channel(
        self,
        channel_type: ChannelType,
        created_by: str,
        name: str = "",
        project_id: Optional[str] = None,
        members: Optional[List[str]] = None,
    ) -> Channel:
        """Create a new channel."""
        channel = Channel(
            channel_type=channel_type,
            name=name,
            project_id=project_id,
            created_by=created_by,
            members=members or [],
        )
        self._channels[channel.channel_id] = channel
        self._persist_channel(channel, replace_members=True)
        return channel

    def get_channel(self, channel_id: str) -> Optional[Channel]:
        """Get a channel by ID."""
        return self._channels.get(channel_id)

    def get_direct_channel(self, agent1: str, agent2: str) -> Optional[Channel]:
        """Find existing direct channel between two agents."""
        for channel in self._channels.values():
            if (
                channel.channel_type == ChannelType.DIRECT
                and set(channel.members) == {agent1, agent2}
            ):
                return channel
        return None

    def get_or_create_direct_channel(
        self,
        agent1: str,
        agent2: str,
        project_id: Optional[str] = None,
    ) -> Channel:
        """Get or create a direct channel between two agents."""
        existing = self.get_direct_channel(agent1, agent2)
        if existing:
            if project_id and not existing.project_id:
                existing.project_id = project_id
                self._persist_channel(existing, replace_members=False)
            return existing

        return self.create_channel(
            channel_type=ChannelType.DIRECT,
            created_by=agent1,
            name=f"{agent1}-{agent2}",
            project_id=project_id,
            members=[agent1, agent2],
        )

    def list_channels(self, agent_id: Optional[str] = None) -> List[Channel]:
        """List all channels, optionally filtered by agent membership."""
        channels = list(self._channels.values())
        if agent_id:
            channels = [ch for ch in channels if ch.has_member(agent_id)]
        return channels

    def sync_channel(self, channel_id: str, replace_members: bool = False) -> bool:
        """Force-persist an existing in-memory channel to DB."""
        channel = self._channels.get(channel_id)
        if not channel:
            return False
        self._persist_channel(channel, replace_members=replace_members)
        return True

    def archive_channel(self, channel_id: str) -> bool:
        """Archive a channel."""
        channel = self._channels.get(channel_id)
        if channel:
            channel.is_archived = True
            self._persist_channel(channel, replace_members=False)
            return True
        return False


channel_manager = ChannelManager()
