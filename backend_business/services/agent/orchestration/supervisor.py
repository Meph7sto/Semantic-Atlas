"""Agent supervisor - manages lifecycle and health.
Agent 监督者 - 管理生命周期和健康状态。
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from backend_business.services.agent.messaging import message_bus, AgentMessage, MessageType
from backend_business.services.agent.messaging.channel import channel_manager, ChannelType
from backend_business.services.agent.registry import agent_registry

logger = logging.getLogger(__name__)


@dataclass
class AgentStatus:
    """Runtime status of a managed agent.
    受管 Agent 的运行时状态。
    """

    agent_id: str
    is_alive: bool = False  # 是否存活
    started_at: Optional[datetime] = None  # 启动时间
    last_heartbeat: Optional[datetime] = None  # 最后心跳时间
    messages_received: int = 0  # 接收消息数
    messages_sent: int = 0  # 发送消息数
    errors: int = 0  # 错误数

    def to_dict(self) -> dict:
        """Convert status to dictionary.
        将状态转换为字典。
        """
        return {
            "agent_id": self.agent_id,
            "is_alive": self.is_alive,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_heartbeat": self.last_heartbeat.isoformat() if self.last_heartbeat else None,
            "messages_received": self.messages_received,
            "messages_sent": self.messages_sent,
            "errors": self.errors,
        }


class AgentSupervisor:
    """Manages agent lifecycle: start → run → stop.
    管理 Agent 生命周期：启动 → 运行 → 停止。

    Usage::
    用法：

        supervisor.start_agent("requirements_agent")
        # ... agent is now subscribed and handling messages ...
        # ... agent 现在已订阅并处理消息 ...
        supervisor.stop_agent("requirements_agent")
    """

    def __init__(self) -> None:
        self._statuses: Dict[str, AgentStatus] = {}
        self._callbacks: Dict[str, Callable[[AgentMessage], None]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # 生命周期
    # ------------------------------------------------------------------

    def start_agent(
        self,
        agent_id: str,
        message_handler: Optional[Callable[[AgentMessage], None]] = None,
    ) -> AgentStatus:
        """Register an agent on the bus and mark it as alive.
        在总线上注册 Agent 并将其标记为存活。
        """
        agent_def = agent_registry.get(agent_id)
        if not agent_def:
            raise ValueError(f"Cannot start unknown agent: {agent_id}")

        status = self._statuses.get(agent_id)
        if status and status.is_alive:
            logger.warning("Agent %s is already alive; skipping start.", agent_id)
            return status

        status = AgentStatus(
            agent_id=agent_id,
            is_alive=True,
            started_at=datetime.now(timezone.utc),
            last_heartbeat=datetime.now(timezone.utc),
        )
        self._statuses[agent_id] = status

        # Default handler: update heartbeat counter
        # 默认处理程序：更新心跳计数器
        def _default_handler(msg: AgentMessage) -> None:
            status.messages_received += 1
            status.last_heartbeat = datetime.now(timezone.utc)
            if message_handler:
                try:
                    message_handler(msg)
                except Exception as e:
                    status.errors += 1
                    logger.error("Agent %s handler error: %s", agent_id, e)

        self._callbacks[agent_id] = _default_handler
        message_bus.subscribe(agent_id, _default_handler)

        logger.info("Supervisor: Agent %s started.", agent_id)
        return status

    def stop_agent(self, agent_id: str) -> None:
        """Unsubscribe an agent and mark it as dead.
        取消订阅 Agent 并将其标记为死亡。
        """
        cb = self._callbacks.pop(agent_id, None)
        if cb:
            message_bus.unsubscribe(agent_id, cb)

        status = self._statuses.get(agent_id)
        if status:
            status.is_alive = False

        logger.info("Supervisor: Agent %s stopped.", agent_id)

    def restart_agent(
        self,
        agent_id: str,
        message_handler: Optional[Callable[[AgentMessage], None]] = None,
    ) -> AgentStatus:
        """Stop then start an agent.
        停止然后启动 Agent。
        """
        self.stop_agent(agent_id)
        return self.start_agent(agent_id, message_handler)

    # ------------------------------------------------------------------
    # Status / observability
    # 状态 / 可观测性
    # ------------------------------------------------------------------

    def get_status(self, agent_id: str) -> Optional[AgentStatus]:
        """Get the status of a specific agent.
        获取特定 Agent 的状态。
        """
        return self._statuses.get(agent_id)

    def list_statuses(self) -> List[AgentStatus]:
        """List statuses of all managed agents.
        列出所有受管 Agent 的状态。
        """
        return list(self._statuses.values())

    def dashboard(self) -> Dict[str, dict]:
        """Return a serialisable snapshot of all agent statuses.
        返回所有 Agent 状态的可序列化快照。
        """
        return {s.agent_id: s.to_dict() for s in self._statuses.values()}

    def is_alive(self, agent_id: str) -> bool:
        """Check if an agent is currently alive.
        检查 Agent 当前是否存活。
        """
        status = self._statuses.get(agent_id)
        return bool(status and status.is_alive)

    # ------------------------------------------------------------------
    # Heartbeat
    # 心跳
    # ------------------------------------------------------------------

    def send_heartbeat(self, agent_id: str) -> Optional[str]:
        """Publish a HEARTBEAT message from *agent_id* on the system channel.
        从 *agent_id* 在系统频道上发布 HEARTBEAT 消息。

        Returns the message_id, or None if the agent is not alive.
        返回 message_id，如果 Agent 不存活则返回 None。
        """
        if not self.is_alive(agent_id):
            return None

        # Use a system broadcast channel for heartbeats
        # 使用系统广播频道进行心跳
        channel = channel_manager.create_channel(
            channel_type=ChannelType.BROADCAST,
            created_by="supervisor",
            name="system_heartbeat",
            members=[a.agent_id for a in agent_registry.list_agents()],
        )

        from backend_business.services.agent.messaging.message import AgentMessage as Msg

        hb = Msg(
            channel_id=channel.channel_id,
            sender_id=agent_id,
            message_type=MessageType.HEARTBEAT,
            content={"timestamp": datetime.now(timezone.utc).isoformat()},
        )
        msg_id = message_bus.publish(hb)

        status = self._statuses.get(agent_id)
        if status:
            status.last_heartbeat = datetime.now(timezone.utc)
            status.messages_sent += 1

        return msg_id


# Global singleton
# 全局单例
supervisor = AgentSupervisor()
