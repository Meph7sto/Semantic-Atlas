"""Generic actor manager integration runtime for agents."""

from __future__ import annotations

import asyncio
import os
import socket
import threading
from typing import Any

from backend_business.config import settings


class AgentActorRuntime:
    """Provides actor-manager access and a dedicated async loop for agent calls."""

    def __init__(
        self,
        *,
        query_source: str = "agent",
        loop_thread_name: str = "agent-actor-loop",
        command_timeout_seconds: int = 60,
    ) -> None:
        self._query_source = query_source
        self._loop_thread_name = loop_thread_name
        self._command_timeout_seconds = command_timeout_seconds
        self._actor_loop: asyncio.AbstractEventLoop | None = None
        self._actor_loop_thread: threading.Thread | None = None

    def get_actor_manager(self):
        from backend_business.services.actor.actor_manager import ActorManager
        from backend_business.services.agent.coordinator.distributed_coordinator import (
            DistributedActorCoordinator,
        )
        from backend_business.services.event_store.event_store import EventStore

        event_store = EventStore(settings.POSTGRES_DSN)
        coordinator = None
        if settings.REDIS_URL:
            coordinator = DistributedActorCoordinator(
                redis_url=settings.REDIS_URL,
                instance_id=self._get_instance_id(),
            )
        return ActorManager.get_instance(event_store, coordinator=coordinator)

    def ensure_actor_loop(self) -> asyncio.AbstractEventLoop:
        if self._actor_loop and self._actor_loop_thread and self._actor_loop_thread.is_alive():
            return self._actor_loop

        loop = asyncio.new_event_loop()

        def _runner() -> None:
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(
            target=_runner,
            name=self._loop_thread_name,
            daemon=True,
        )
        thread.start()
        self._actor_loop = loop
        self._actor_loop_thread = thread
        return loop

    def run_actor_coro(self, coro: Any):
        loop = self.ensure_actor_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=self._command_timeout_seconds)

    def actor_query(self, actor_manager: Any, entity_id: str) -> dict[str, Any]:
        return self.run_actor_coro(
            actor_manager.send_command(
                entity_id,
                {"type": "QueryState", "source": self._query_source},
            )
        )

    def actor_write(self, actor_manager: Any, entity_id: str, command: dict[str, Any]) -> dict[str, Any]:
        return self.run_actor_coro(actor_manager.send_command(entity_id, command))

    @staticmethod
    def _get_instance_id() -> str:
        configured = settings.ACTOR_INSTANCE_ID
        if configured:
            return configured
        host = os.environ.get("HOSTNAME") or socket.gethostname() or "unknown-host"
        return f"{host}:{os.getpid()}"

