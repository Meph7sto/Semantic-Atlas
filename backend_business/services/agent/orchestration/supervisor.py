"""Agent supervisor - lifecycle management for agents on the message bus.

The supervisor:
1. Tracks which agents are currently "alive" (subscribed to the bus).
2. Provides start/stop helpers that wire up bus subscriptions.
3. Emits heartbeat signals (optional) so peers know an agent is available.
4. Exposes a status dashboard for observability.
"""

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from backend_business.services.agent.messaging import message_bus, AgentMessage, MessageType
from backend_business.services.agent.messaging.channel import channel_manager, ChannelType
from backend_business.services.agent.registry import agent_registry

logger = logging.getLogger(__name__)


@dataclass
class AgentStatus:
    """Runtime status of a managed agent."""

    agent_id: str
    is_alive: bool = False
    started_at: Optional[datetime] = None
    last_heartbeat: Optional[datetime] = None
    messages_received: int = 0
    messages_sent: int = 0
    errors: int = 0

    def to_dict(self) -> dict:
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

    Usage::

        supervisor.start_agent("requirements_agent")
        # ... agent is now subscribed and handling messages ...
        supervisor.stop_agent("requirements_agent")
    """

    def __init__(self) -> None:
        self._statuses: Dict[str, AgentStatus] = {}
        self._callbacks: Dict[str, Callable[[AgentMessage], None]] = {}

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    def start_agent(
        self,
        agent_id: str,
        message_handler: Optional[Callable[[AgentMessage], None]] = None,
    ) -> AgentStatus:
        """Register an agent on the bus and mark it as alive."""
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
        """Unsubscribe an agent and mark it as dead."""
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
        """Stop then start an agent."""
        self.stop_agent(agent_id)
        return self.start_agent(agent_id, message_handler)

    # ------------------------------------------------------------------
    # Status / observability
    # ------------------------------------------------------------------

    def get_status(self, agent_id: str) -> Optional[AgentStatus]:
        return self._statuses.get(agent_id)

    def list_statuses(self) -> List[AgentStatus]:
        return list(self._statuses.values())

    def dashboard(self) -> Dict[str, dict]:
        """Return a serialisable snapshot of all agent statuses."""
        return {s.agent_id: s.to_dict() for s in self._statuses.values()}

    def is_alive(self, agent_id: str) -> bool:
        status = self._statuses.get(agent_id)
        return bool(status and status.is_alive)

    # ------------------------------------------------------------------
    # Heartbeat
    # ------------------------------------------------------------------

    def send_heartbeat(self, agent_id: str) -> Optional[str]:
        """Publish a HEARTBEAT message from *agent_id* on the system channel.

        Returns the message_id, or None if the agent is not alive.
        """
        if not self.is_alive(agent_id):
            return None

        # Use a system broadcast channel for heartbeats
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
supervisor = AgentSupervisor()
