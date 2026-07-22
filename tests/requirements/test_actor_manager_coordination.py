"""
ActorManager distributed coordination tests for P0 lock enforcement.
"""

import asyncio
import os
import sys
import time
import threading
import time
from typing import Any

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.actor import actor_manager as actor_manager_module
from backend_business.services.actor.actor_manager import ActorManager
from backend_business.services.actor.actors.requirement_actor import (
    InfrastructureException,
    RequirementActor,
)


class _StubActor:
    def __init__(self, requirement_id: str, event_store: Any):
        self.requirement_id = requirement_id
        self.event_store = event_store
        self.is_faulted = False
        self.lease_invalidated = False
        self.fencing_token: int | None = None
        self.invalidated = False
        self.last_accessed = 0.0
        self.mailbox = asyncio.Queue()
        self.command_deadlines: list[float | None] = []

    async def activate(self):
        events = getattr(self.event_store, "events", None)
        if events is not None:
            events.append(("activate", self.fencing_token))
        on_activate = getattr(self.event_store, "on_actor_activate", None)
        if callable(on_activate):
            on_activate(self)
        return None

    async def start(self):
        return None

    async def stop(self):
        return None

    async def invalidate_lease(self, *, fencing_token: int):
        self.invalidated = True
        self.lease_invalidated = True
        self.is_faulted = True

    async def send_command(self, command: dict, *, deadline_at: float | None = None):
        self.command_deadlines.append(deadline_at)
        return {"status": "success", "requirement_id": self.requirement_id, "command": command}


class _StubCoordinator:
    def __init__(
        self,
        acquire_result: bool = True,
        holder: str | None = None,
        available: bool = True,
        order: list[tuple[str, int]] | None = None,
    ):
        self.acquire_result = acquire_result
        self.holder = holder
        self.available = available
        self.registered = False
        self.acquire_calls: list[str] = []
        self.release_calls: list[str] = []
        self.fencing_token = 0
        self.owned = False
        self.floor = 0
        self.order = order

    async def is_available(self) -> bool:
        return self.available

    async def register_instance(self, metadata: dict | None = None):
        self.registered = True

    async def heartbeat(self, interval: float = 30.0):
        while True:
            await asyncio.sleep(60)

    async def acquire_lock(self, requirement_id: str, ttl: int | None = None) -> bool:
        self.acquire_calls.append(requirement_id)
        if self.order is not None:
            self.order.append(("acquire", self.floor))
        if self.acquire_result:
            self.fencing_token = max(self.fencing_token, self.floor) + 1
            self.owned = True
        return self.acquire_result

    async def ensure_fencing_floor(self, requirement_id: str, floor: int) -> int:
        self.floor = max(self.floor, floor)
        if self.order is not None:
            self.order.append(("ensure", self.floor))
        return self.floor

    def get_fencing_token(self, requirement_id: str) -> int | None:
        return self.fencing_token if self.owned else None

    async def owns_lease(
        self,
        requirement_id: str,
        expected_fencing_token: int | None = None,
    ) -> bool:
        return self.owned and (
            expected_fencing_token is None
            or expected_fencing_token == self.fencing_token
        )

    async def get_lock_holder(self, requirement_id: str):
        return self.holder

    async def release_lock(self, requirement_id: str):
        self.release_calls.append(requirement_id)
        self.owned = False

    async def cleanup(self):
        return None


class _ForwardingCoordinator(_StubCoordinator):
    def __init__(self, *, acquire_result: bool = False):
        super().__init__(acquire_result=acquire_result, holder="node-b:5002")
        self.forward_calls: list[tuple[str, dict]] = []

    async def forward_request(self, requirement_id: str, command: dict):
        self.forward_calls.append((requirement_id, command))
        return {"status": "success", "handled_by": "node-b:5002"}


def _reset_actor_manager_singleton(monkeypatch):
    ActorManager._instance = None
    ActorManager._actors = {}
    monkeypatch.setattr(actor_manager_module, "RequirementActor", _StubActor)


class _FenceEventStore:
    def __init__(self, floor: int, order: list[tuple[str, int]]):
        self.floor = floor
        self.order = order
        self.events = order

    def get_actor_fencing_token(self, requirement_id: str) -> int:
        self.order.append(("read_floor", self.floor))
        return self.floor

    def claim_actor_fence(self, requirement_id: str, fencing_token: int) -> int:
        self.order.append(("claim", fencing_token))
        assert fencing_token > self.floor
        self.floor = fencing_token
        return fencing_token


class _BlockingReplayEventStore(_FenceEventStore):
    def __init__(self):
        super().__init__(0, [])
        self.replay_entered = threading.Event()
        self.release_replay = threading.Event()

    def get_latest_snapshot(self, requirement_id: str):
        self.replay_entered.set()
        self.release_replay.wait(timeout=0.5)
        return None

    def replay_events(self, requirement_id: str, from_version: int = 0):
        return []

    def save_snapshot(
        self,
        requirement_id: str,
        version: int,
        state_data: dict,
        reason: str,
        **_kwargs,
    ):
        return f"{requirement_id}_{version}_{reason}"


class _HeartbeatProbeCoordinator(_StubCoordinator):
    def __init__(self, event_store: _BlockingReplayEventStore):
        super().__init__()
        self.event_store = event_store
        self.heartbeat_tick = asyncio.Event()
        self.heartbeat_at: float | None = None

    async def heartbeat(self, interval: float = 30.0):
        while not self.event_store.replay_entered.is_set():
            await asyncio.sleep(0)
        self.heartbeat_at = time.monotonic()
        self.heartbeat_tick.set()
        self.event_store.release_replay.set()
        while True:
            await asyncio.sleep(60)


def test_send_command_rejects_when_distributed_lock_not_acquired(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    coordinator = _StubCoordinator(acquire_result=False, holder="node-b:5002")
    manager = ActorManager(event_store=_FenceEventStore(0, []), coordinator=coordinator)

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
    manager = ActorManager(event_store=_FenceEventStore(0, []), coordinator=coordinator)

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
    manager = ActorManager(event_store=_FenceEventStore(0, []), coordinator=coordinator)

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


def test_send_command_routes_to_remote_actor_owner(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    coordinator = _ForwardingCoordinator()
    manager = ActorManager(event_store=_FenceEventStore(0, []), coordinator=coordinator)

    async def _run():
        command = {"type": "QueryState"}
        result = await manager.send_command("req-routed", command)
        assert result == {"status": "success", "handled_by": "node-b:5002"}
        assert coordinator.forward_calls == [("req-routed", command)]
        assert "req-routed" not in manager._actors
        await manager.shutdown()
        ActorManager._instance = None
        ActorManager._actors = {}

    asyncio.run(_run())


def test_forwarded_command_carries_deadline_into_actor_mailbox(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    coordinator = _StubCoordinator(acquire_result=True)
    manager = ActorManager(event_store=_FenceEventStore(0, []), coordinator=coordinator)

    async def _run():
        await manager.send_command("req-deadline", {"type": "QueryState"})
        actor = manager._actors["req-deadline"]
        deadline_at = time.time() + 5

        result = await manager._handle_forwarded_command(
            "req-deadline",
            {"type": "UpdateRequirementContent"},
            coordinator.fencing_token,
            deadline_at,
        )

        assert result["status"] == "success"
        assert actor.command_deadlines == [None, deadline_at]
        await manager.shutdown()
        ActorManager._instance = None
        ActorManager._actors = {}

    asyncio.run(_run())


def test_actor_claims_durable_fence_before_replaying_state(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    order: list[tuple[str, int]] = []
    event_store = _FenceEventStore(41, order)
    coordinator = _StubCoordinator(order=order)
    manager = ActorManager(event_store=event_store, coordinator=coordinator)

    async def _run():
        result = await manager.send_command("req-fence-order", {"type": "QueryState"})

        assert result["status"] == "success"
        assert callable(manager._actors["req-fence-order"].lease_validator)
        assert order[:5] == [
            ("read_floor", 41),
            ("ensure", 41),
            ("acquire", 41),
            ("claim", 42),
            ("activate", 42),
        ]
        await manager.shutdown()
        ActorManager._instance = None
        ActorManager._actors = {}

    asyncio.run(_run())


def test_existing_local_actor_is_evicted_when_lease_is_no_longer_owned(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    coordinator = _ForwardingCoordinator(acquire_result=True)
    manager = ActorManager(event_store=_FenceEventStore(0, []), coordinator=coordinator)

    async def _run():
        first = await manager.send_command("req-stale-local", {"type": "QueryState"})
        assert first["status"] == "success"
        stale_actor = manager._actors["req-stale-local"]

        coordinator.owned = False
        coordinator.holder = "node-b:5002"
        second = await manager.send_command(
            "req-stale-local",
            {"type": "QueryState"},
        )

        assert second == {"status": "success", "handled_by": "node-b:5002"}
        assert stale_actor.invalidated is True
        assert "req-stale-local" not in manager._actors
        assert coordinator.release_calls == ["req-stale-local"]
        await manager.shutdown()
        ActorManager._instance = None
        ActorManager._actors = {}

    asyncio.run(_run())


def test_expired_local_lease_reacquires_with_a_new_durable_fence(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    coordinator = _StubCoordinator(acquire_result=True, holder=None)
    event_store = _FenceEventStore(0, [])
    manager = ActorManager(event_store=event_store, coordinator=coordinator)

    async def _run():
        await manager.send_command("req-recover", {"type": "QueryState"})
        stale_actor = manager._actors["req-recover"]
        assert stale_actor.fencing_token == 1

        coordinator.owned = False
        await manager.send_command("req-recover", {"type": "QueryState"})
        recovered_actor = manager._actors["req-recover"]

        assert stale_actor.invalidated is True
        assert recovered_actor is not stale_actor
        assert recovered_actor.fencing_token == 2
        assert event_store.floor == 2
        await manager.shutdown()
        ActorManager._instance = None
        ActorManager._actors = {}

    asyncio.run(_run())


def test_activation_fails_closed_when_lease_is_lost_during_replay(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    coordinator = _ForwardingCoordinator(acquire_result=True)
    event_store = _FenceEventStore(0, [])
    activated: list[_StubActor] = []

    def _lose_lease(actor: _StubActor) -> None:
        activated.append(actor)
        coordinator.owned = False

    event_store.on_actor_activate = _lose_lease  # type: ignore[attr-defined]
    manager = ActorManager(event_store=event_store, coordinator=coordinator)

    async def _run():
        result = await manager.send_command(
            "req-lost-during-replay",
            {"type": "QueryState"},
        )

        assert result == {"status": "success", "handled_by": "node-b:5002"}
        assert len(activated) == 1
        assert activated[0].invalidated is True
        assert "req-lost-during-replay" not in manager._actors
        assert coordinator.release_calls == ["req-lost-during-replay"]
        await manager.shutdown()
        ActorManager._instance = None
        ActorManager._actors = {}

    asyncio.run(_run())


def test_stale_lease_loss_callback_does_not_evict_newer_actor(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    manager = ActorManager(event_store=object(), coordinator=None)
    actor = _StubActor("req-newer-owner", object())
    actor.fencing_token = 8
    manager._actors[actor.requirement_id] = actor

    async def _run():
        await manager._handle_lease_lost(actor.requirement_id, fencing_token=7)

        assert manager._actors[actor.requirement_id] is actor
        assert actor.invalidated is False

        await manager._handle_lease_lost(actor.requirement_id, fencing_token=8)
        assert actor.requirement_id not in manager._actors
        assert actor.invalidated is True
        ActorManager._instance = None
        ActorManager._actors = {}

    asyncio.run(_run())


def test_blocking_state_replay_does_not_stall_broker_heartbeat(monkeypatch):
    _reset_actor_manager_singleton(monkeypatch)
    monkeypatch.setattr(actor_manager_module, "RequirementActor", RequirementActor)
    event_store = _BlockingReplayEventStore()
    coordinator = _HeartbeatProbeCoordinator(event_store)
    manager = ActorManager(event_store=event_store, coordinator=coordinator)

    async def _run():
        started_at = time.monotonic()
        command_task = asyncio.create_task(
            manager.send_command("req-blocking-replay", {"type": "QueryState"})
        )

        await asyncio.wait_for(coordinator.heartbeat_tick.wait(), timeout=1)
        assert coordinator.heartbeat_at is not None
        assert coordinator.heartbeat_at - started_at < 0.25
        assert (await command_task)["status"] == "success"

        await manager.shutdown()
        ActorManager._instance = None
        ActorManager._actors = {}

    asyncio.run(_run())
