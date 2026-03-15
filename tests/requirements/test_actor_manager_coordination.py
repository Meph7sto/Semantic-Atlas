"""
ActorManager distributed coordination tests for P0 lock enforcement.
"""

import asyncio
import os
import sys
from typing import Any

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.actor import actor_manager as actor_manager_module
from backend_business.services.actor.actor_manager import ActorManager
from backend_business.services.actor.actors.requirement_actor import InfrastructureException


class _StubActor:
    def __init__(self, requirement_id: str, event_store: Any):
        self.requirement_id = requirement_id
        self.event_store = event_store
        self.is_faulted = False
        self.last_accessed = 0.0
        self.mailbox = asyncio.Queue()

    async def activate(self):
        return None

    async def start(self):
        return None

    async def stop(self):
        return None

    async def send_command(self, command: dict):
        return {"status": "success", "requirement_id": self.requirement_id, "command": command}


class _StubCoordinator:
    def __init__(
        self,
        acquire_result: bool = True,
        holder: str | None = None,
        available: bool = True,
    ):
        self.acquire_result = acquire_result
        self.holder = holder
        self.available = available
        self.registered = False
        self.acquire_calls: list[str] = []
        self.release_calls: list[str] = []

    async def is_available(self) -> bool:
        return self.available

    async def register_instance(self, metadata: dict | None = None):
        self.registered = True

    async def heartbeat(self, interval: float = 30.0):
        while True:
            await asyncio.sleep(60)

    async def acquire_lock(self, requirement_id: str, ttl: int | None = None) -> bool:
        self.acquire_calls.append(requirement_id)
        return self.acquire_result

    async def get_lock_holder(self, requirement_id: str):
        return self.holder

    async def release_lock(self, requirement_id: str):
        self.release_calls.append(requirement_id)

    async def cleanup(self):
        return None


def _reset_actor_manager_singleton(monkeypatch):
    ActorManager._instance = None
    ActorManager._actors = {}
    monkeypatch.setattr(actor_manager_module, "RequirementActor", _StubActor)


def test_send_command_rejects_when_distributed_lock_not_acquired(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    coordinator = _StubCoordinator(acquire_result=False, holder="node-b:5002")
    manager = ActorManager(event_store=object(), coordinator=coordinator)

    async def _run():
        try:
            await manager.send_command("req-1", {"type": "QueryState"})
            raise AssertionError("expected InfrastructureException")
        except InfrastructureException:
            pass
        assert coordinator.acquire_calls == ["req-1"]
        await manager.shutdown()
        ActorManager._instance = None
        ActorManager._actors = {}

    asyncio.run(_run())


def test_force_passivate_releases_distributed_lock(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    coordinator = _StubCoordinator(acquire_result=True)
    manager = ActorManager(event_store=object(), coordinator=coordinator)

    async def _run():
        result = await manager.send_command("req-2", {"type": "QueryState"})
        assert result["status"] == "success"
        await manager.force_passivate("req-2")
        assert "req-2" in coordinator.release_calls
        await manager.shutdown()
        ActorManager._instance = None
        ActorManager._actors = {}

    asyncio.run(_run())


def test_send_command_rejects_when_coordinator_unavailable(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    coordinator = _StubCoordinator(acquire_result=True, available=False)
    manager = ActorManager(event_store=object(), coordinator=coordinator)

    async def _run():
        try:
            await manager.send_command("req-3", {"type": "QueryState"})
            raise AssertionError("expected InfrastructureException")
        except InfrastructureException:
            pass
        await manager.shutdown()
        ActorManager._instance = None
        ActorManager._actors = {}

    asyncio.run(_run())
