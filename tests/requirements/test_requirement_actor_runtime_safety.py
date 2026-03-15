"""
RequirementActor 运行时安全性测试（P1 问题回归）。
"""

import asyncio
import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.actor.actor_manager import ActorManager
from backend_business.services.actor.actors.requirement_actor import (
    InfrastructureException,
    RequirementActor,
)


class _StubEventStore:
    def get_latest_snapshot(self, requirement_id: str):
        return None

    def replay_events(self, requirement_id: str, from_version: int = 0):
        return []

    def save_snapshot(self, requirement_id: str, version: int, state_data: dict, reason: str):
        return f"{requirement_id}_{version}_{reason}"


class _FailingStopActor:
    def __init__(self):
        self.last_accessed = 0.0
        self.mailbox = asyncio.Queue()
        self.is_faulted = False

    async def stop(self):
        raise InfrastructureException("snapshot failed")


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

