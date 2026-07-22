"""Multi-instance lease and command-routing regression tests."""

from __future__ import annotations

import asyncio
import json
import re
import time
import uuid
from collections import defaultdict
from types import SimpleNamespace
from typing import Any

from backend_business.services.agent.coordinator.distributed_coordinator import (
    DistributedActorCoordinator,
)


class _FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, Any] = {}
        self.hashes: dict[str, dict[str, Any]] = defaultdict(dict)
        self.queues: dict[str, asyncio.Queue[Any]] = defaultdict(asyncio.Queue)
        self.expire_calls: list[tuple[str, int]] = []
        self.deleted_keys: list[str] = []

    async def ping(self):
        return True

    async def eval(self, script: str, key_count: int, *args: Any):
        keys = [str(item) for item in args[:key_count]]
        argv = [str(item) for item in args[key_count:]]
        if "acquire_actor_lease" in script:
            lock_key, instance_key, fence_key = keys
            if lock_key in self.values:
                return [0, self.values[lock_key]]
            token = int(self.values.get(fence_key, 0)) + 1
            self.values[fence_key] = token
            lock_value = f"{argv[0]}|{token}|{argv[1]}"
            self.values[lock_key] = lock_value
            self.values[instance_key] = argv[0]
            return [1, token, lock_value]
        if "ensure_actor_fence_floor" in script:
            fence_key = keys[0]
            current = int(self.values.get(fence_key, 0))
            current = max(current, int(argv[0]))
            self.values[fence_key] = current
            return current
        if "renew_actor_lease" in script:
            lock_key, instance_key = keys
            if self.values.get(lock_key) != argv[0]:
                return 0
            await self.expire(lock_key, int(argv[1]))
            self.values[instance_key] = argv[2]
            await self.expire(instance_key, int(argv[1]))
            return 1
        if "release_actor_lease" in script:
            lock_key, instance_key = keys
            if self.values.get(lock_key) != argv[0]:
                return 0
            self.values.pop(lock_key, None)
            self.values.pop(instance_key, None)
            return 1
        raise AssertionError("unexpected Lua script")

    async def get(self, key: str):
        return self.values.get(key)

    async def set(self, key: str, value: Any, ex: int | None = None, nx: bool = False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        if ex is not None:
            await self.expire(key, ex)
        return True

    async def delete(self, key: str):
        self.deleted_keys.append(key)
        self.values.pop(key, None)
        self.queues.pop(key, None)

    async def expire(self, key: str, ttl: int):
        self.expire_calls.append((key, int(ttl)))
        return key in self.values or key in self.queues

    async def rpush(self, key: str, value: Any):
        await self.queues[key].put(value)
        return self.queues[key].qsize()

    async def blpop(self, key: str, timeout: int = 0):
        queue = self.queues[key]
        try:
            if timeout:
                value = await asyncio.wait_for(queue.get(), timeout=timeout)
            else:
                value = await queue.get()
        except TimeoutError:
            return None
        return key, value

    async def hset(self, key: str, field: str, value: Any):
        self.hashes[key][field] = value

    async def hdel(self, key: str, field: str):
        self.hashes[key].pop(field, None)

    async def hgetall(self, key: str):
        return dict(self.hashes[key])

    async def aclose(self):
        return None


def _coordinator(fake: _FakeRedis, instance_id: str) -> DistributedActorCoordinator:
    coordinator = DistributedActorCoordinator(
        "redis://test",
        instance_id,
        lock_ttl=45,
        rpc_timeout=2,
    )
    coordinator._redis_client = fake
    return coordinator


def test_lease_renewal_is_owner_checked_and_refreshes_both_keys():
    async def _run():
        fake = _FakeRedis()
        coordinator = _coordinator(fake, "node-a")
        lost: list[tuple[str, int]] = []
        coordinator.set_lease_lost_handler(
            lambda requirement_id, token: lost.append((requirement_id, token))
        )

        assert await coordinator.acquire_lock("req-1") is True
        assert coordinator.get_fencing_token("req-1") == 1
        holder_key = coordinator._get_instance_key("req-1")
        fake.values.pop(holder_key)
        assert await coordinator._renew_lock("req-1") is True
        lock_key = coordinator._get_lock_key("req-1")
        assert (lock_key, 45) in fake.expire_calls
        assert (holder_key, 45) in fake.expire_calls
        assert fake.values[holder_key] == "node-a"

        fake.values[lock_key] = "node-b|2|replacement"
        assert await coordinator._renew_lock("req-1") is False
        assert lost == [("req-1", 1)]
        assert coordinator.get_fencing_token("req-1") is None

        await coordinator.cleanup()

    asyncio.run(_run())


def test_fencing_token_increases_after_a_new_owner_takes_over():
    async def _run():
        fake = _FakeRedis()
        first = _coordinator(fake, "node-a")
        second = _coordinator(fake, "node-b")

        assert await first.acquire_lock("req-2") is True
        assert first.get_fencing_token("req-2") == 1
        await first.release_lock("req-2")
        assert await second.acquire_lock("req-2") is True
        assert second.get_fencing_token("req-2") == 2

        await first.cleanup()
        await second.cleanup()

    asyncio.run(_run())


def test_remote_command_is_routed_to_the_current_lease_owner():
    async def _run():
        fake = _FakeRedis()
        owner = _coordinator(fake, "node-a")
        caller = _coordinator(fake, "node-b")
        received: list[tuple[str, dict[str, Any], int, float]] = []

        async def _handle(
            requirement_id: str,
            command: dict[str, Any],
            fencing_token: int,
            deadline_at: float,
        ):
            received.append((requirement_id, command, fencing_token, deadline_at))
            return {"status": "success", "handled_by": "node-a"}

        assert await owner.acquire_lock("req-3") is True
        await owner.start_request_listener(_handle)
        result = await caller.forward_request("req-3", {"type": "QueryState"})

        assert result == {"status": "success", "handled_by": "node-a"}
        assert received[0][:3] == ("req-3", {"type": "QueryState"}, 1)
        assert received[0][3] >= time.time() - owner._rpc_timeout

        await caller.cleanup()
        await owner.cleanup()

    asyncio.run(_run())


def test_routing_retry_and_api_identity_reuse_the_same_request_id():
    async def _run():
        fake = _FakeRedis()
        caller = _coordinator(fake, "node-caller")
        envelopes: list[dict[str, Any]] = []
        route_calls = 0
        original_rpush = fake.rpush

        async def _route(_requirement_id: str):
            nonlocal route_calls
            route_calls += 1
            return SimpleNamespace(
                instance_id=f"node-owner-{route_calls}",
                fencing_token=route_calls,
            )

        async def _rpush(key: str, value: Any):
            if key.startswith("actor:rpc:requests:"):
                envelope = json.loads(value)
                envelopes.append(envelope)
                if len(envelopes) == 1:
                    response = {
                        "ok": False,
                        "error_code": "lease_not_owned",
                        "error": "lease moved",
                    }
                else:
                    response = {
                        "ok": True,
                        "result": {"status": "success"},
                    }
                await original_rpush(
                    caller._get_response_queue_key(envelope["request_id"]),
                    json.dumps(response),
                )
                return 1
            return await original_rpush(key, value)

        caller.get_actor_route = _route  # type: ignore[method-assign]
        fake.rpush = _rpush  # type: ignore[method-assign]
        command = {
            "type": "UpdateRequirementContent",
            "idempotency_key": "client-operation-7",
        }

        assert await caller.forward_request("req-retry", command) == {"status": "success"}
        assert await caller.forward_request("req-retry", command) == {"status": "success"}

        expected_id = uuid.uuid5(
            uuid.NAMESPACE_URL,
            "semantic-atlas:req-retry:client-operation-7",
        ).hex
        assert [item["request_id"] for item in envelopes] == [
            expected_id,
            expected_id,
            expected_id,
        ]
        assert envelopes[0]["deadline_at"] == envelopes[1]["deadline_at"]
        await caller.cleanup()

    asyncio.run(_run())


def test_actor_lease_keys_share_a_redis_cluster_hash_tag():
    keys = [
        DistributedActorCoordinator._get_lock_key("req-cluster"),
        DistributedActorCoordinator._get_instance_key("req-cluster"),
        DistributedActorCoordinator._get_fencing_key("req-cluster"),
    ]

    tags = [re.search(r"\{([^}]+)\}", key) for key in keys]
    assert all(match is not None for match in tags)
    assert {match.group(1) for match in tags if match is not None} == {"actor:req-cluster"}


def test_durable_fencing_floor_recovers_a_reset_redis_counter():
    async def _run():
        fake = _FakeRedis()
        coordinator = _coordinator(fake, "node-recovered")

        assert await coordinator.ensure_fencing_floor("req-reset", 41) == 41
        assert await coordinator.acquire_lock("req-reset") is True
        assert coordinator.get_fencing_token("req-reset") == 42

        await coordinator.cleanup()

    asyncio.run(_run())


def test_forwarded_request_rejects_stale_fence_and_expired_deadline():
    async def _run():
        fake = _FakeRedis()
        owner = _coordinator(fake, "node-owner")
        handled: list[dict[str, Any]] = []

        async def _handle(
            _requirement_id: str,
            command: dict[str, Any],
            _fencing_token: int,
        ):
            handled.append(command)
            return {"status": "success"}

        assert await owner.acquire_lock("req-guarded") is True
        owner.set_request_handler(_handle)
        token = owner.get_fencing_token("req-guarded")

        stale = {
            "request_id": "stale-request",
            "requirement_id": "req-guarded",
            "command": {"type": "QueryState"},
            "fencing_token": token + 1,
            "deadline_at": time.time() + 10,
        }
        await owner._handle_forwarded_envelope(stale)
        stale_response = await fake.blpop(owner._get_response_queue_key("stale-request"), 1)
        assert stale_response is not None
        assert json.loads(stale_response[1])["error_code"] == "lease_not_owned"

        expired = {
            "request_id": "expired-request",
            "requirement_id": "req-guarded",
            "command": {"type": "QueryState"},
            "fencing_token": token,
            "deadline_at": time.time() - 1,
        }
        await owner._handle_forwarded_envelope(expired)
        expired_response = await fake.blpop(
            owner._get_response_queue_key("expired-request"),
            1,
        )
        assert expired_response is not None
        assert json.loads(expired_response[1])["error_code"] == "request_expired"
        assert handled == []
        assert await fake.get(owner._get_request_result_key("req-guarded", "stale-request")) is None
        assert (
            await fake.get(owner._get_request_result_key("req-guarded", "expired-request")) is None
        )

        await owner.cleanup()

    asyncio.run(_run())


def test_forwarded_request_result_is_idempotently_replayed():
    async def _run():
        fake = _FakeRedis()
        owner = _coordinator(fake, "node-owner")
        handled = 0

        async def _handle(
            _requirement_id: str,
            _command: dict[str, Any],
            _fencing_token: int,
        ):
            nonlocal handled
            handled += 1
            return {"status": "success", "invocation": handled}

        assert await owner.acquire_lock("req-idempotent") is True
        owner.set_request_handler(_handle)
        envelope = {
            "request_id": "stable-request-id",
            "requirement_id": "req-idempotent",
            "command": {"type": "UpdateRequirementContent"},
            "fencing_token": owner.get_fencing_token("req-idempotent"),
            "deadline_at": time.time() + 10,
        }

        await owner._handle_forwarded_envelope(envelope)
        first = await fake.blpop(owner._get_response_queue_key("stable-request-id"), 1)
        await owner._handle_forwarded_envelope(envelope)
        second = await fake.blpop(owner._get_response_queue_key("stable-request-id"), 1)

        assert first is not None and second is not None
        assert json.loads(first[1]) == json.loads(second[1])
        assert handled == 1

        await owner.cleanup()

    asyncio.run(_run())


def test_instance_liveness_prunes_stale_rows_and_cleanup_deletes_rpc_queue():
    async def _run():
        fake = _FakeRedis()
        coordinator = _coordinator(fake, "node-live")
        fake.hashes[coordinator._get_instances_key()]["node-dead"] = json.dumps(
            {"instance_id": "node-dead"}
        )
        queue_key = coordinator._get_request_queue_key("node-live")
        await fake.rpush(queue_key, "pending")

        await coordinator.register_instance()
        instances = await coordinator.get_cluster_instances()

        assert set(instances) == {"node-live"}
        assert coordinator._lock_ttl == 45
        await coordinator.cleanup()
        assert queue_key in fake.deleted_keys
        assert coordinator._get_instance_liveness_key("node-live") in fake.deleted_keys

    asyncio.run(_run())
