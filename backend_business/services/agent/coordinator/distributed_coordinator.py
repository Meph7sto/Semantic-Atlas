"""Redis-backed coordination for globally addressed RequirementActors."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import time
import uuid
from collections.abc import Awaitable, Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger(__name__)


class ActorCoordinationError(RuntimeError):
    """Raised when actor coordination cannot preserve routing semantics."""


class ForwardedActorCommandError(ActorCoordinationError):
    """Raised when a remote actor owner rejects a forwarded command."""


class ForwardedActorCommandExpired(ActorCoordinationError):
    """Raised when a queued forwarded command reaches its caller deadline."""


@dataclass(frozen=True)
class _ActorLease:
    requirement_id: str
    lock_value: str
    fencing_token: int
    ttl_seconds: int


@dataclass(frozen=True)
class _ActorRoute:
    instance_id: str
    fencing_token: int


RequestHandler = Callable[..., dict[str, Any] | Awaitable[dict[str, Any]]]
LeaseLostHandler = Callable[[str, int], Any | Awaitable[Any]]


_ACQUIRE_LEASE_SCRIPT = """
-- acquire_actor_lease
if redis.call("EXISTS", KEYS[1]) == 1 then
    return {0, redis.call("GET", KEYS[1])}
end
local token = redis.call("INCR", KEYS[3])
local value = ARGV[1] .. "|" .. tostring(token) .. "|" .. ARGV[2]
redis.call("SET", KEYS[1], value, "EX", ARGV[3])
redis.call("SET", KEYS[2], ARGV[1], "EX", ARGV[3])
return {1, tostring(token), value}
"""

_ENSURE_FENCE_FLOOR_SCRIPT = """
-- ensure_actor_fence_floor
local current = tonumber(redis.call("GET", KEYS[1]) or "0")
local floor = tonumber(ARGV[1])
if current < floor then
    redis.call("SET", KEYS[1], tostring(floor))
    return floor
end
return current
"""

_RENEW_LEASE_SCRIPT = """
-- renew_actor_lease
if redis.call("GET", KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call("EXPIRE", KEYS[1], ARGV[2])
redis.call("SET", KEYS[2], ARGV[3], "EX", ARGV[2])
return 1
"""

_RELEASE_LEASE_SCRIPT = """
-- release_actor_lease
if redis.call("GET", KEYS[1]) ~= ARGV[1] then
    return 0
end
redis.call("DEL", KEYS[1])
redis.call("DEL", KEYS[2])
return 1
"""


def _decode_redis_value(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8")
    return str(value)


class DistributedActorCoordinator:
    """Own actor leases and route commands to the node holding each lease.

    A lease contains a monotonically increasing fencing token. Renewal and
    release compare the complete lease value in Redis, so a stale process can
    neither extend nor remove a newer owner's lease.
    """

    def __init__(
        self,
        redis_url: str,
        instance_id: str,
        *,
        lock_ttl: int = 90,
        rpc_timeout: float = 30.0,
    ) -> None:
        if lock_ttl < 1:
            raise ValueError("lock_ttl must be positive")
        if rpc_timeout <= 0:
            raise ValueError("rpc_timeout must be positive")
        self.redis_url = redis_url
        self.instance_id = instance_id
        self._lock_ttl = int(lock_ttl)
        self._rpc_timeout = float(rpc_timeout)
        self._instance_ttl = max(3, self._lock_ttl)
        self._request_cache_ttl = max(60, int(self._rpc_timeout * 4))
        self._leases: dict[str, _ActorLease] = {}
        # Kept as a compatibility view for existing diagnostics/tests.
        self._locks: dict[str, str] = {}
        self._local_fencing_tokens: dict[str, int] = {}
        self._redis_client: Any | None = None
        self._request_handler: RequestHandler | None = None
        self._lease_lost_handler: LeaseLostHandler | None = None
        self._request_listener_task: asyncio.Task[None] | None = None

    def _get_redis_client(self) -> Any | None:
        if self._redis_client is None:
            try:
                import redis.asyncio as redis

                self._redis_client = redis.from_url(self.redis_url)
                logger.info("Redis actor coordinator connected: %s", self.redis_url)
            except ImportError:
                logger.warning("redis package not available; distributed coordination disabled")
        return self._redis_client

    @staticmethod
    def _get_actor_slot(requirement_id: str) -> str:
        return f"{{actor:{requirement_id}}}"

    @staticmethod
    def _get_lock_key(requirement_id: str) -> str:
        return f"actor:lock:{DistributedActorCoordinator._get_actor_slot(requirement_id)}"

    @staticmethod
    def _get_instance_key(requirement_id: str) -> str:
        return f"actor:holder:{DistributedActorCoordinator._get_actor_slot(requirement_id)}"

    @staticmethod
    def _get_fencing_key(requirement_id: str) -> str:
        return f"actor:fence:{DistributedActorCoordinator._get_actor_slot(requirement_id)}"

    @staticmethod
    def _get_instances_key() -> str:
        return "instances:actors"

    @staticmethod
    def _get_request_queue_key(instance_id: str) -> str:
        return f"actor:rpc:requests:{instance_id}"

    @staticmethod
    def _get_response_queue_key(request_id: str) -> str:
        return f"actor:rpc:responses:{request_id}"

    @staticmethod
    def _get_request_result_key(requirement_id: str, request_id: str) -> str:
        return f"actor:rpc:result:{{actor:{requirement_id}}}:{request_id}"

    @staticmethod
    def _get_instance_liveness_key(instance_id: str) -> str:
        return f"actor:instances:live:{instance_id}"

    async def is_available(self) -> bool:
        redis_client = self._get_redis_client()
        if redis_client is None:
            return False
        try:
            await redis_client.ping()
            return True
        except Exception as exc:
            logger.warning("Redis actor coordinator unavailable: %s", exc)
            return False

    async def ensure_fencing_floor(self, requirement_id: str, floor: int) -> int:
        """Keep Redis fencing monotonic with the durable database fence."""
        durable_floor = int(floor)
        if durable_floor < 0:
            raise ValueError("fencing floor cannot be negative")
        redis_client = self._get_redis_client()
        if redis_client is None:
            current = self._local_fencing_tokens.get(requirement_id, 0)
            current = max(current, durable_floor)
            self._local_fencing_tokens[requirement_id] = current
            return current
        result = await redis_client.eval(
            _ENSURE_FENCE_FLOOR_SCRIPT,
            1,
            self._get_fencing_key(requirement_id),
            durable_floor,
        )
        return int(_decode_redis_value(result))

    async def acquire_lock(self, requirement_id: str, ttl: int | None = None) -> bool:
        existing = self._leases.get(requirement_id)
        if existing is not None and await self.owns_lock(requirement_id):
            return True

        redis_client = self._get_redis_client()
        lock_ttl = int(self._lock_ttl if ttl is None else ttl)
        if lock_ttl < 1:
            raise ValueError("ttl must be positive")
        if redis_client is None:
            token = self._local_fencing_tokens.get(requirement_id, 0) + 1
            self._local_fencing_tokens[requirement_id] = token
            lock_value = f"{self.instance_id}|{token}|local"
            self._remember_lease(requirement_id, lock_value, token, lock_ttl)
            return True

        try:
            result = await redis_client.eval(
                _ACQUIRE_LEASE_SCRIPT,
                3,
                self._get_lock_key(requirement_id),
                self._get_instance_key(requirement_id),
                self._get_fencing_key(requirement_id),
                self.instance_id,
                uuid.uuid4().hex,
                lock_ttl,
            )
            if not result or int(_decode_redis_value(result[0])) != 1:
                return False
            token = int(_decode_redis_value(result[1]))
            lock_value = _decode_redis_value(result[2])
            self._remember_lease(requirement_id, lock_value, token, lock_ttl)
            logger.info(
                "Actor lease acquired: requirement=%s instance=%s fence=%s",
                requirement_id,
                self.instance_id,
                token,
            )
            return True
        except Exception as exc:
            logger.error("Error acquiring actor lease for %s: %s", requirement_id, exc)
            return False

    def _remember_lease(
        self,
        requirement_id: str,
        lock_value: str,
        fencing_token: int,
        ttl_seconds: int,
    ) -> None:
        self._leases[requirement_id] = _ActorLease(
            requirement_id=requirement_id,
            lock_value=lock_value,
            fencing_token=fencing_token,
            ttl_seconds=ttl_seconds,
        )
        self._locks[requirement_id] = lock_value

    def get_fencing_token(self, requirement_id: str) -> int | None:
        lease = self._leases.get(requirement_id)
        return lease.fencing_token if lease is not None else None

    async def owns_lease(
        self,
        requirement_id: str,
        expected_fencing_token: int | None = None,
    ) -> bool:
        lease = self._leases.get(requirement_id)
        if lease is None:
            return False
        if (
            expected_fencing_token is not None
            and lease.fencing_token != int(expected_fencing_token)
        ):
            return False
        return await self.owns_lock(requirement_id)

    async def owns_lock(self, requirement_id: str) -> bool:
        lease = self._leases.get(requirement_id)
        if lease is None:
            return False
        redis_client = self._get_redis_client()
        if redis_client is None:
            return True
        try:
            current = await redis_client.get(self._get_lock_key(requirement_id))
            return current is not None and _decode_redis_value(current) == lease.lock_value
        except Exception as exc:
            logger.error("Error checking actor lease for %s: %s", requirement_id, exc)
            return False

    async def release_lock(self, requirement_id: str) -> None:
        lease = self._leases.get(requirement_id)
        redis_client = self._get_redis_client()
        try:
            if lease is not None and redis_client is not None:
                await redis_client.eval(
                    _RELEASE_LEASE_SCRIPT,
                    2,
                    self._get_lock_key(requirement_id),
                    self._get_instance_key(requirement_id),
                    lease.lock_value,
                )
        except Exception as exc:
            logger.error("Error releasing actor lease for %s: %s", requirement_id, exc)
        finally:
            self._leases.pop(requirement_id, None)
            self._locks.pop(requirement_id, None)

    def set_request_handler(self, handler: RequestHandler) -> None:
        self._request_handler = handler

    def set_lease_lost_handler(self, handler: LeaseLostHandler) -> None:
        self._lease_lost_handler = handler

    async def start_request_listener(
        self,
        handler: RequestHandler | None = None,
    ) -> None:
        if handler is not None:
            self.set_request_handler(handler)
        if self._request_handler is None:
            raise ValueError("request handler is required")
        if self._request_listener_task and not self._request_listener_task.done():
            return
        if self._get_redis_client() is None:
            raise ActorCoordinationError("Redis is required for remote actor routing")
        self._request_listener_task = asyncio.create_task(
            self._request_listener_loop(),
            name=f"actor-rpc-{self.instance_id}",
        )

    async def forward_request(
        self,
        requirement_id: str,
        command: dict[str, Any],
    ) -> dict[str, Any] | None:
        redis_client = self._get_redis_client()
        if redis_client is None:
            return None

        supplied_id = command.get("idempotency_key") or command.get("request_id")
        request_id = (
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                f"semantic-atlas:{requirement_id}:{supplied_id}",
            ).hex
            if supplied_id
            else uuid.uuid4().hex
        )
        deadline_at = time.time() + self._rpc_timeout
        for attempt in range(2):
            route = await self.get_actor_route(requirement_id)
            if route is None:
                return None
            holder = route.instance_id
            if holder == self.instance_id and self._request_handler is not None:
                if not await self.owns_lease(requirement_id, route.fencing_token):
                    return None
                return await self._invoke_request_handler(
                    requirement_id,
                    command,
                    route.fencing_token,
                    deadline_at,
                )

            response_key = self._get_response_queue_key(request_id)
            envelope = {
                "request_id": request_id,
                "requirement_id": requirement_id,
                "command": command,
                "fencing_token": route.fencing_token,
                "sender_instance_id": self.instance_id,
                "sent_at": datetime.now(UTC).isoformat(),
                "deadline_at": deadline_at,
            }
            try:
                queue_key = self._get_request_queue_key(holder)
                await redis_client.rpush(
                    queue_key,
                    json.dumps(envelope, ensure_ascii=False),
                )
                await redis_client.expire(queue_key, self._request_cache_ttl)
                remaining = deadline_at - time.time()
                if remaining <= 0:
                    raise ActorCoordinationError("actor command deadline expired before routing")
                response_item = await redis_client.blpop(
                    response_key,
                    timeout=max(1, int(remaining + 0.999)),
                )
            except TimeoutError:
                response_item = None
            except Exception as exc:
                raise ActorCoordinationError(
                    f"failed to forward actor command to {holder}: {exc}"
                ) from exc
            finally:
                try:
                    await redis_client.delete(response_key)
                except Exception:
                    logger.debug("Unable to delete actor RPC response key", exc_info=True)

            if not response_item:
                raise ActorCoordinationError(
                    f"timed out forwarding actor command to {holder}"
                )
            raw_response = response_item[1] if isinstance(response_item, (list, tuple)) else response_item
            response = json.loads(_decode_redis_value(raw_response))
            if response.get("ok"):
                result = response.get("result")
                return result if isinstance(result, dict) else {"result": result}
            if response.get("error_code") == "lease_not_owned" and attempt == 0:
                continue
            raise ForwardedActorCommandError(str(response.get("error") or "remote actor failed"))
        return None

    async def _request_listener_loop(self) -> None:
        redis_client = self._get_redis_client()
        if redis_client is None:
            return
        queue_key = self._get_request_queue_key(self.instance_id)
        while True:
            try:
                item = await redis_client.blpop(queue_key, timeout=1)
                if not item:
                    continue
                raw_envelope = item[1] if isinstance(item, (list, tuple)) else item
                envelope = json.loads(_decode_redis_value(raw_envelope))
                await self._handle_forwarded_envelope(envelope)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Actor RPC listener failed while processing a command")

    async def _handle_forwarded_envelope(self, envelope: dict[str, Any]) -> None:
        redis_client = self._get_redis_client()
        if redis_client is None:
            return
        request_id = str(envelope.get("request_id") or "").strip()
        requirement_id = str(envelope.get("requirement_id") or "").strip()
        command = envelope.get("command")
        if not request_id:
            return
        result_key = self._get_request_result_key(requirement_id, request_id)
        response: dict[str, Any]
        if not requirement_id or not isinstance(command, dict):
            response = {"ok": False, "error": "invalid forwarded actor command"}
        else:
            cached_response = await redis_client.get(result_key)
            if cached_response is not None:
                await self._send_rpc_response(
                    request_id,
                    json.loads(_decode_redis_value(cached_response)),
                )
                return

            try:
                fencing_token = int(envelope.get("fencing_token"))
                deadline_at = float(envelope.get("deadline_at"))
            except (TypeError, ValueError):
                response = {
                    "ok": False,
                    "error_code": "invalid_request",
                    "error": "forwarded actor command is missing lease metadata",
                }
            else:
                if time.time() > deadline_at:
                    response = {
                        "ok": False,
                        "error_code": "request_expired",
                        "error": "forwarded actor command deadline expired",
                    }
                elif not await self.owns_lease(requirement_id, fencing_token):
                    response = {
                        "ok": False,
                        "error_code": "lease_not_owned",
                        "error": (
                            f"instance {self.instance_id} no longer owns "
                            f"{requirement_id} at fence {fencing_token}"
                        ),
                    }
                elif self._request_handler is None:
                    response = {
                        "ok": False,
                        "error": "actor request handler is not configured",
                    }
                else:
                    try:
                        result = await self._invoke_request_handler(
                            requirement_id,
                            command,
                            fencing_token,
                            deadline_at,
                        )
                        response = {"ok": True, "result": result}
                    except ForwardedActorCommandExpired as exc:
                        response = {
                            "ok": False,
                            "error_code": "request_expired",
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        }
                    except Exception as exc:
                        response = {
                            "ok": False,
                            "error": str(exc),
                            "error_type": type(exc).__name__,
                        }

                    if response.get("error_code") != "request_expired":
                        await redis_client.set(
                            result_key,
                            json.dumps(response, ensure_ascii=False),
                            ex=self._request_cache_ttl,
                        )

        await self._send_rpc_response(request_id, response)

    async def _send_rpc_response(
        self,
        request_id: str,
        response: dict[str, Any],
    ) -> None:
        redis_client = self._get_redis_client()
        if redis_client is None:
            return
        response_key = self._get_response_queue_key(request_id)
        await redis_client.rpush(response_key, json.dumps(response, ensure_ascii=False))
        await redis_client.expire(response_key, max(1, int(self._rpc_timeout * 2)))

    async def _invoke_request_handler(
        self,
        requirement_id: str,
        command: dict[str, Any],
        fencing_token: int,
        deadline_at: float,
    ) -> dict[str, Any]:
        if self._request_handler is None:
            raise ActorCoordinationError("actor request handler is not configured")
        handler = self._request_handler
        candidates = (
            (requirement_id, command, fencing_token, deadline_at),
            (requirement_id, command, fencing_token),
            (requirement_id, command),
        )
        try:
            signature = inspect.signature(handler)
        except (TypeError, ValueError):
            result = handler(*candidates[0])
        else:
            for arguments in candidates:
                try:
                    signature.bind(*arguments)
                except TypeError:
                    continue
                result = handler(*arguments)
                break
            else:
                raise ActorCoordinationError(
                    "actor request handler has an incompatible signature"
                )
        if inspect.isawaitable(result):
            result = await result
        if not isinstance(result, dict):
            raise ActorCoordinationError("actor request handler must return a mapping")
        return result

    async def register_instance(self, metadata: dict[str, Any] | None = None) -> None:
        redis_client = self._get_redis_client()
        if redis_client is None:
            return
        instance_info = {
            "instance_id": self.instance_id,
            "registered_at": datetime.now(UTC).isoformat(),
            "rpc_queue": self._get_request_queue_key(self.instance_id),
            "metadata": metadata or {},
        }
        try:
            encoded = json.dumps(instance_info, ensure_ascii=False)
            await redis_client.hset(
                self._get_instances_key(),
                self.instance_id,
                encoded,
            )
            await redis_client.set(
                self._get_instance_liveness_key(self.instance_id),
                encoded,
                ex=self._instance_ttl,
            )
            await self._prune_stale_instances()
        except Exception as exc:
            logger.error("Error registering actor instance %s: %s", self.instance_id, exc)

    async def _prune_stale_instances(self) -> None:
        redis_client = self._get_redis_client()
        if redis_client is None:
            return
        instances = await redis_client.hgetall(self._get_instances_key())
        for instance_id in instances:
            decoded_id = _decode_redis_value(instance_id)
            live = await redis_client.get(self._get_instance_liveness_key(decoded_id))
            if live is None:
                await redis_client.hdel(self._get_instances_key(), decoded_id)

    async def unregister_instance(self) -> None:
        redis_client = self._get_redis_client()
        if redis_client is None:
            return
        try:
            await redis_client.hdel(self._get_instances_key(), self.instance_id)
            await redis_client.delete(self._get_instance_liveness_key(self.instance_id))
        except Exception as exc:
            logger.error("Error unregistering actor instance %s: %s", self.instance_id, exc)

    async def get_cluster_instances(self) -> dict[str, dict[str, Any]]:
        redis_client = self._get_redis_client()
        if redis_client is None:
            return {}
        try:
            await self._prune_stale_instances()
            instances = await redis_client.hgetall(self._get_instances_key())
            return {
                _decode_redis_value(key): json.loads(_decode_redis_value(value))
                for key, value in instances.items()
            }
        except Exception as exc:
            logger.error("Error listing actor instances: %s", exc)
            return {}

    async def get_actor_route(self, requirement_id: str) -> _ActorRoute | None:
        redis_client = self._get_redis_client()
        if redis_client is None:
            lease = self._leases.get(requirement_id)
            if lease is None:
                return None
            return _ActorRoute(self.instance_id, lease.fencing_token)
        try:
            current = await redis_client.get(self._get_lock_key(requirement_id))
            if current is None:
                return None
            lock_value = _decode_redis_value(current)
            instance_id, token_text, _nonce = lock_value.split("|", 2)
            return _ActorRoute(instance_id, int(token_text))
        except (TypeError, ValueError) as exc:
            logger.error("Invalid actor lease value for %s: %s", requirement_id, exc)
            return None
        except Exception as exc:
            logger.error("Error reading actor route for %s: %s", requirement_id, exc)
            return None

    async def get_lock_holder(self, requirement_id: str) -> str | None:
        route = await self.get_actor_route(requirement_id)
        return route.instance_id if route is not None else None

    async def heartbeat(self, interval: float | None = None) -> None:
        if interval is None:
            interval = max(0.25, self._lock_ttl / 3)
        if interval <= 0:
            raise ValueError("heartbeat interval must be positive")
        if self._get_redis_client() is None:
            return
        while True:
            try:
                await self.register_instance()
                for requirement_id in list(self._leases):
                    await self._renew_lock(requirement_id)
                await asyncio.sleep(interval)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.error("Actor coordinator heartbeat failed: %s", exc)
                await asyncio.sleep(interval)

    async def _renew_lock(self, requirement_id: str) -> bool:
        lease = self._leases.get(requirement_id)
        if lease is None:
            return False
        redis_client = self._get_redis_client()
        if redis_client is None:
            return True
        try:
            renewed = await redis_client.eval(
                _RENEW_LEASE_SCRIPT,
                2,
                self._get_lock_key(requirement_id),
                self._get_instance_key(requirement_id),
                lease.lock_value,
                lease.ttl_seconds,
                self.instance_id,
            )
            if int(_decode_redis_value(renewed)) == 1:
                return True
        except Exception as exc:
            logger.error("Error renewing actor lease for %s: %s", requirement_id, exc)

        self._leases.pop(requirement_id, None)
        self._locks.pop(requirement_id, None)
        await self._notify_lease_lost(requirement_id, lease.fencing_token)
        return False

    async def _notify_lease_lost(self, requirement_id: str, fencing_token: int) -> None:
        if self._lease_lost_handler is None:
            return
        try:
            result = self._lease_lost_handler(requirement_id, fencing_token)
            if inspect.isawaitable(result):
                await result
        except Exception:
            logger.exception("Actor lease-loss handler failed for %s", requirement_id)

    async def cleanup(self) -> None:
        listener = self._request_listener_task
        if listener is not None and not listener.done():
            listener.cancel()
            with suppress(asyncio.CancelledError):
                await listener
        self._request_listener_task = None

        for requirement_id in list(self._leases):
            await self.release_lock(requirement_id)
        await self.unregister_instance()

        redis_client = self._redis_client
        if redis_client is not None:
            try:
                await redis_client.delete(self._get_request_queue_key(self.instance_id))
            except Exception:
                logger.debug("Unable to delete actor RPC request queue", exc_info=True)
            close = getattr(redis_client, "aclose", None) or getattr(redis_client, "close", None)
            if callable(close):
                result = close()
                if inspect.isawaitable(result):
                    await result
        self._redis_client = None
