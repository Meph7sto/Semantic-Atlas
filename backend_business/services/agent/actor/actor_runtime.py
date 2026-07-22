"""Generic actor manager integration runtime for agents."""

from __future__ import annotations

import asyncio
import inspect
import os
import socket
import threading
from collections.abc import Callable
from concurrent.futures import TimeoutError as FutureTimeoutError
from typing import Any

from backend_business.config import settings


class AgentActorRuntime:
    """Provides actor-manager access and a dedicated async loop for agent calls."""

    _broker_loop: asyncio.AbstractEventLoop | None = None
    _broker_loop_thread: threading.Thread | None = None
    _broker_lock = threading.Lock()

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
        loop = self.ensure_actor_loop()
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is loop:
            return self._create_actor_manager()
        return self.run_actor_call(self._create_actor_manager)

    async def get_actor_manager_async(self):
        return await self.await_actor_call(self._create_actor_manager)

    def _create_actor_manager(self):
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
        """Return the process-wide actor broker loop.

        ActorManager is a process singleton and owns asyncio primitives and tasks.
        A single broker loop keeps every caller, including separate agent service
        instances and FastAPI request loops, from using those objects cross-loop.
        """
        runtime_type = AgentActorRuntime
        with runtime_type._broker_lock:
            loop = runtime_type._broker_loop
            thread = runtime_type._broker_loop_thread
            if loop is None or loop.is_closed() or thread is None or not thread.is_alive():
                loop = asyncio.new_event_loop()
                ready = threading.Event()

                def _runner() -> None:
                    asyncio.set_event_loop(loop)
                    ready.set()
                    loop.run_forever()

                thread = threading.Thread(
                    target=_runner,
                    name=self._loop_thread_name,
                    daemon=True,
                )
                runtime_type._broker_loop = loop
                runtime_type._broker_loop_thread = thread
                thread.start()
                ready.wait(timeout=2.0)

            # Keep the historical instance attributes for compatibility with
            # diagnostics and test cleanup helpers.
            self._actor_loop = loop
            self._actor_loop_thread = thread
            return loop

    @staticmethod
    async def _invoke_actor_call(
        callback: Callable[..., Any],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> Any:
        result = callback(*args, **kwargs)
        if inspect.isawaitable(result):
            return await result
        return result

    def run_actor_coro(self, coro: Any):
        loop = self.ensure_actor_loop()
        try:
            running_loop = asyncio.get_running_loop()
        except RuntimeError:
            running_loop = None
        if running_loop is loop:
            coro.close()
            raise RuntimeError("run_actor_coro cannot block the actor broker loop")
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        try:
            return future.result(timeout=self._command_timeout_seconds)
        except FutureTimeoutError:
            future.cancel()
            raise

    async def await_actor_coro(self, coro: Any):
        """Await actor work from any caller loop without blocking that loop."""
        loop = self.ensure_actor_loop()
        if asyncio.get_running_loop() is loop:
            return await coro

        future = asyncio.run_coroutine_threadsafe(coro, loop)
        wrapped = asyncio.wrap_future(future)
        try:
            return await asyncio.wait_for(
                wrapped,
                timeout=self._command_timeout_seconds,
            )
        except BaseException:
            if not future.done():
                future.cancel()
            raise

    def run_actor_call(self, callback: Callable[..., Any], *args: Any, **kwargs: Any):
        return self.run_actor_coro(self._invoke_actor_call(callback, args, kwargs))

    async def await_actor_call(
        self,
        callback: Callable[..., Any],
        *args: Any,
        **kwargs: Any,
    ) -> Any:
        return await self.await_actor_coro(
            self._invoke_actor_call(callback, args, kwargs)
        )

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
