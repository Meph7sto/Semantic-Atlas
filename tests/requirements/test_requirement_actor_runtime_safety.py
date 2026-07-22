"""
RequirementActor 运行时安全性测试（P1 问题回归）。
"""

import asyncio
import os
import sys
import time

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.actor.actor_manager import ActorManager
from backend_business.services.actor.actors.requirement_actor import (
    ActorCommandDeadlineExceeded,
    InfrastructureException,
    RequirementActor,
)
from backend_business.services.event_store.event_store import StaleActorLeaseError


class _StubEventStore:
    def get_latest_snapshot(self, requirement_id: str):
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


class _FailingStopActor:
    def __init__(self):
        self.last_accessed = 0.0
        self.mailbox = asyncio.Queue()
        self.is_faulted = False

    async def stop(self):
        raise InfrastructureException("snapshot failed")


class _CapturingEventStore:
    def __init__(self):
        self.events: list[dict] = []

    def append_event(self, event: dict):
        self.events.append(dict(event))
        return "event-1", 1


class _StaleFenceEventStore(_StubEventStore):
    def append_event(self, event: dict):
        raise StaleActorLeaseError("newer owner already claimed the fence")


def test_faulted_actor_fails_backlogged_futures():
    async def _run():
        actor = RequirementActor("req-fault", _StubEventStore())
        actor.MAX_RETRIES = 1

        async def _always_fail(_command):
            raise InfrastructureException("db down")

        actor._handle_command = _always_fail  # type: ignore[method-assign]
        await actor.start()

        task1 = asyncio.create_task(actor.send_command({"type": "UpdateRequirementContent"}))
        task2 = asyncio.create_task(actor.send_command({"type": "ChangeStatus"}))

        try:
            await asyncio.wait_for(task1, timeout=3)
            raise AssertionError("task1 should fail")
        except InfrastructureException:
            pass

        try:
            await asyncio.wait_for(task2, timeout=3)
            raise AssertionError("task2 should fail")
        except InfrastructureException:
            pass

        assert actor.is_faulted is True
        await actor.stop()

    asyncio.run(_run())


def test_idle_passivation_keeps_actor_when_snapshot_fails():
    ActorManager._instance = None
    ActorManager._actors = {}
    manager = ActorManager(event_store=object(), coordinator=None)
    manager._actors["req-passivation"] = _FailingStopActor()  # type: ignore[assignment]

    async def _run():
        await manager.passivate_idle_actors(idle_timeout=0)
        assert "req-passivation" in manager._actors
        await manager.shutdown()

    asyncio.run(_run())
    ActorManager._instance = None
    ActorManager._actors = {}


def test_actor_attaches_fencing_token_to_event_store_writes():
    async def _run():
        event_store = _CapturingEventStore()
        actor = RequirementActor("req-fenced", event_store)  # type: ignore[arg-type]
        actor.fencing_token = 17

        await actor._append_event(
            {
                "requirement_id": "req-fenced",
                "event_type": "RequirementCreated",
                "event_data": {},
            }
        )

        assert event_store.events[0]["fencing_token"] == 17

    asyncio.run(_run())


def test_stale_database_fence_invalidates_actor_and_stops_mailbox():
    async def _run():
        actor = RequirementActor("req-stale-fence", _StaleFenceEventStore())
        actor.fencing_token = 7
        await actor.start()

        try:
            await actor.send_command(
                {
                    "type": "UpdateRequirementContent",
                    "updates": {"title": "must not persist"},
                }
            )
            raise AssertionError("stale fenced command should fail")
        except InfrastructureException as exc:
            assert "持久化租约已失效" in str(exc)

        await asyncio.sleep(0)
        assert actor.is_faulted is True
        assert actor.lease_invalidated is True
        assert actor._consumer_task is not None
        assert actor._consumer_task.done() is True

        try:
            await actor.send_command({"type": "QueryState"})
            raise AssertionError("invalidated actor should reject subsequent reads")
        except InfrastructureException:
            pass

    asyncio.run(_run())


def test_actor_revalidates_lease_before_every_query_state_command():
    async def _run():
        actor = RequirementActor("req-command-fence", _StubEventStore())
        validations: list[tuple[str, int | None]] = []

        async def _validate(requirement_id: str, fencing_token: int | None) -> bool:
            validations.append((requirement_id, fencing_token))
            return len(validations) == 1

        actor.fencing_token = 23
        actor.lease_validator = _validate
        await actor.start()

        first = await actor.send_command({"type": "QueryState"})
        assert first["status"] == "success"

        try:
            await actor.send_command({"type": "QueryState"})
            raise AssertionError("lost lease must reject queued QueryState")
        except InfrastructureException as exc:
            assert "持久化租约已失效" in str(exc)

        assert validations == [
            ("req-command-fence", 23),
            ("req-command-fence", 23),
        ]
        assert actor.lease_invalidated is True

    asyncio.run(_run())


def test_queued_command_does_not_start_after_forwarding_deadline():
    async def _run():
        actor = RequirementActor("req-deadline", _StubEventStore())
        first_started = asyncio.Event()
        release_first = asyncio.Event()
        handled: list[str] = []

        async def _handle(command: dict):
            handled.append(command["type"])
            if command["type"] == "FirstCommand":
                first_started.set()
                await release_first.wait()
            return {"status": "success"}

        actor._handle_command = _handle  # type: ignore[method-assign]
        await actor.start()
        first = asyncio.create_task(actor.send_command({"type": "FirstCommand"}))
        await first_started.wait()
        expired = asyncio.create_task(
            actor.send_command(
                {"type": "ExpiredMutation"},
                deadline_at=time.time() + 0.02,
            )
        )
        await asyncio.sleep(0.05)
        release_first.set()

        assert await first == {"status": "success"}
        try:
            await expired
            raise AssertionError("expired queued mutation should not execute")
        except ActorCommandDeadlineExceeded:
            pass

        assert handled == ["FirstCommand"]
        assert actor.is_faulted is False
        await actor.stop()

    asyncio.run(_run())
