"""Actor manager integration for requirement agent tool execution."""

from __future__ import annotations

import asyncio
import threading
from typing import Any

from backend_business.config import settings

from .utils import actor_instance_id


class RequirementAgentActorRuntime:
    def __init__(self) -> None:
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
                instance_id=actor_instance_id(),
            )
        return ActorManager.get_instance(event_store, coordinator=coordinator)

    def ensure_actor_loop(self) -> asyncio.AbstractEventLoop:
        if self._actor_loop and self._actor_loop_thread and self._actor_loop_thread.is_alive():
            return self._actor_loop

        loop = asyncio.new_event_loop()

        def _runner():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(
            target=_runner,
            name="requirement-agent-actor-loop",
            daemon=True,
        )
        thread.start()
        self._actor_loop = loop
        self._actor_loop_thread = thread
        return loop

    def run_actor_coro(self, coro: Any):
        loop = self.ensure_actor_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)

    def actor_query(self, actor_manager: Any, requirement_id: str) -> dict[str, Any]:
        return self.run_actor_coro(
            actor_manager.send_command(
                requirement_id,
                {"type": "QueryState", "source": "requirement_agent_chat"},
            )
        )

    def actor_write(
        self,
        actor_manager: Any,
        requirement_id: str,
        command: dict[str, Any],
    ) -> dict[str, Any]:
        return self.run_actor_coro(actor_manager.send_command(requirement_id, command))

