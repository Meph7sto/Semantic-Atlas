"""Channel management for agent communication.
Agent 通信的频道管理。
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional

from backend_business.services.db_service import db_service

logger = logging.getLogger(__name__)


class ChannelType(str, Enum):
    """Channel types for different communication patterns.
    不同通信模式的频道类型。
    """

    DIRECT = "direct"        # 1:1 private channel; 1对1 私有频道
    GROUP = "group"          # Multi-agent collaboration; 多 Agent 协作群组
    BROADCAST = "broadcast"  # System-wide announcements; 系统范围公告


@dataclass
class Channel:
    """Represents a communication channel between agents.
    表示 Agent 之间的通信频道。
    """

    channel_id: str = field(default_factory=lambda: f"ch_{uuid.uuid4().hex[:16]}")
    channel_type: ChannelType = ChannelType.DIRECT  # 频道类型
    name: str = ""  # 频道名称（可选）
    project_id: Optional[str] = None  # 关联的项目 ID（可选）
    created_by: str = ""  # 创建者 Agent ID
    created_at: datetime = field(default_factory=datetime.now)  # 创建时间
    is_archived: bool = False  # 是否已归档
    members: List[str] = field(default_factory=list)  # List of agent_ids; 成员列表

    def add_member(self, agent_id: str) -> None:
        """Add an agent to the channel.
        将 Agent 添加到频道。
        """
        if agent_id not in self.members:
            self.members.append(agent_id)

    def remove_member(self, agent_id: str) -> None:
        """Remove an agent from the channel.
        将 Agent 从频道移除。
        """
        if agent_id in self.members:
            self.members.remove(agent_id)

    def has_member(self, agent_id: str) -> bool:
        """Check if an agent is a member of this channel.
        检查 Agent 是否为该频道的成员。
        """
        return agent_id in self.members

    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization.
        转换为字典以进行序列化。
        """
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
    """Manages channels in memory (can be extended to persist in DB).
    在内存中管理频道（可扩展为持久化到 DB）。
    """

    def __init__(self):
        self._channels: Dict[str, Channel] = {}

    def _persist_channel(self, channel: Channel, replace_members: bool = True) -> None:
        """Persist channel + members to DB when DB is available.
        当 DB 可用时，将频道和成员持久化到数据库。
        """
        if not db_service:
            return

        try:
            with db_service._connect() as conn:
                with conn.cursor() as cur:
                    # 插入或更新频道基本信息
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
                        # 全量替换成员列表
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
        """Create a new channel.
        创建一个新频道。
        """
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
        """Get a channel by ID.
        根据 ID 获取频道。
        """
        return self._channels.get(channel_id)

    def get_direct_channel(self, agent1: str, agent2: str) -> Optional[Channel]:
        """Find existing direct channel between two agents.
        查找两个 Agent 之间现有的直连频道。
        """
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
        """Get or create a direct channel between two agents.
        获取或创建两个 Agent 之间的直连频道。
        """
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
        """List all channels, optionally filtered by agent membership.
        列出所有频道，可选择按 Agent 成员身份过滤。
        """
        channels = list(self._channels.values())
        if agent_id:
            channels = [ch for ch in channels if ch.has_member(agent_id)]
        return channels

    def sync_channel(self, channel_id: str, replace_members: bool = False) -> bool:
        """Force-persist an existing in-memory channel to DB.
        强制将现有的内存频道持久化到 DB。
        """
        channel = self._channels.get(channel_id)
        if not channel:
            return False
        self._persist_channel(channel, replace_members=replace_members)
        return True

    def archive_channel(self, channel_id: str) -> bool:
        """Archive a channel.
        归档频道。
        """
        channel = self._channels.get(channel_id)
        if channel:
            channel.is_archived = True
            self._persist_channel(channel, replace_members=False)
            return True
        return False


# Global singleton instance
# 全局单例实例
channel_manager = ChannelManager()
