"""
ActorManager - 全局 Actor 管理器

负责 Actor 的创建、查找、路由和生命周期管理
"""

import asyncio
import logging
import os
import time
from typing import Dict, Optional

from backend_business.services.actor.actors.requirement_actor import (
    ActorCommandDeadlineExceeded,
    InfrastructureException,
    RequirementActor,
)
from backend_business.services.actor.dev_trace import emit_actor_trace
from backend_business.services.agent.coordinator.distributed_coordinator import (
    DistributedActorCoordinator,
    ForwardedActorCommandExpired,
)
from backend_business.services.event_store.event_store import EventStore

logger = logging.getLogger(__name__)


class _RemoteActorOwned(Exception):
    def __init__(self, requirement_id: str, holder: str | None) -> None:
        self.requirement_id = requirement_id
        self.holder = holder
        super().__init__(requirement_id)


class ActorManager:
    """全局 Actor 管理器 - 单例模式"""

    _instance: Optional["ActorManager"] = None
    _actors: Dict[str, RequirementActor] = {}
    IDLE_TIMEOUT_SECONDS = 600.0
    PASSIVATION_SCAN_INTERVAL_SECONDS = 60.0

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(
        self,
        event_store: EventStore,
        coordinator: Optional[DistributedActorCoordinator] = None,
    ):
        if not hasattr(self, '_initialized'):
            self.event_store = event_store
            self.coordinator = coordinator
            self._lock = asyncio.Lock()
            self._heartbeat_task: Optional[asyncio.Task] = None
            self._passivation_task: Optional[asyncio.Task] = None
            self._initialized = True
            logger.info("ActorManager initialized")
        elif coordinator is not None and getattr(self, "coordinator", None) is None:
            # 允许在后续注入 coordinator（兼容历史单例创建路径）
            self.coordinator = coordinator

    @classmethod
    def get_instance(
        cls,
        event_store: EventStore,
        coordinator: Optional[DistributedActorCoordinator] = None,
    ) -> "ActorManager":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls(event_store, coordinator=coordinator)
        elif coordinator is not None and getattr(cls._instance, "coordinator", None) is None:
            cls._instance.coordinator = coordinator
        return cls._instance

    async def _ensure_coordination_started(self):
        """启动分布式协调心跳（仅首次）。"""
        if self.coordinator is None:
            return

        available = await self.coordinator.is_available()
        if not available:
            raise InfrastructureException(
                "分布式协调器不可用，拒绝激活 RequirementActor 以避免跨节点重复实例"
            )

        if self._heartbeat_task and not self._heartbeat_task.done():
            return

        set_lease_lost_handler = getattr(
            self.coordinator,
            "set_lease_lost_handler",
            None,
        )
        if callable(set_lease_lost_handler):
            set_lease_lost_handler(self._handle_lease_lost)

        await self.coordinator.register_instance(
            {
                "service": "backend_business",
                "pid": os.getpid(),
            }
        )
        start_request_listener = getattr(
            self.coordinator,
            "start_request_listener",
            None,
        )
        if callable(start_request_listener):
            await start_request_listener(self._handle_forwarded_command)
        self._heartbeat_task = asyncio.create_task(self.coordinator.heartbeat())

    async def _ensure_passivation_loop_started(self):
        """启动空闲 Actor 自动回收循环（仅首次）。"""
        if self._passivation_task and not self._passivation_task.done():
            return
        self._passivation_task = asyncio.create_task(self._passivation_housekeeping_loop())

    async def send_command(self, requirement_id: str, command: Dict) -> Dict:
        """
        发送命令到指定 Actor

        Args:
            requirement_id: 需求 ID
            command: 命令字典

        Returns:
            命令执行结果
        """
        try:
            actor = await self._get_or_create_actor(requirement_id)
        except _RemoteActorOwned as remote:
            forward_request = getattr(self.coordinator, "forward_request", None)
            if not callable(forward_request):
                holder_text = remote.holder or "unknown"
                raise InfrastructureException(
                    f"Actor {requirement_id} 已在实例 {holder_text} 激活，且当前协调器不支持命令转发"
                ) from remote
            try:
                forwarded = await forward_request(requirement_id, command)
            except Exception as exc:
                raise InfrastructureException(
                    f"无法将 Actor {requirement_id} 命令转发到实例 {remote.holder or 'unknown'}: {exc}"
                ) from exc
            if forwarded is None:
                raise InfrastructureException(
                    f"Actor {requirement_id} 的远端持有者不可用"
                )
            return forwarded
        return await actor.send_command(command)

    async def _handle_forwarded_command(
        self,
        requirement_id: str,
        command: Dict,
        fencing_token: int | None = None,
        deadline_at: float | None = None,
    ) -> Dict:
        """Execute a routed command only on the node owning the actor lease."""
        actor = await self._get_or_create_actor(
            requirement_id,
            expected_fencing_token=fencing_token,
        )
        try:
            if deadline_at is None:
                return await actor.send_command(command)
            return await actor.send_command(command, deadline_at=deadline_at)
        except ActorCommandDeadlineExceeded as exc:
            raise ForwardedActorCommandExpired(str(exc)) from exc

    async def _handle_lease_lost(
        self,
        requirement_id: str,
        fencing_token: int,
    ) -> None:
        """Fail closed when Redis reports that a local lease was replaced."""
        async with self._lock:
            actor = self._actors.get(requirement_id)
            if actor is None:
                return
            actor_token = getattr(actor, "fencing_token", None)
            if actor_token != fencing_token:
                emit_actor_trace(
                    requirement_id,
                    "stale_lease_lost_ignored",
                    fencing_token=fencing_token,
                    active_fencing_token=actor_token,
                )
                return
            self._actors.pop(requirement_id, None)
            await self._invalidate_actor_unlocked(
                requirement_id,
                actor,
                fencing_token=fencing_token,
            )
            emit_actor_trace(
                requirement_id,
                "lease_lost",
                level="error",
                fencing_token=fencing_token,
            )

    async def _invalidate_actor_unlocked(
        self,
        requirement_id: str,
        actor: RequirementActor,
        *,
        fencing_token: int,
    ) -> None:
        invalidate = getattr(actor, "invalidate_lease", None)
        try:
            if callable(invalidate):
                await invalidate(fencing_token=fencing_token)
            else:
                await actor.stop()
        except Exception as exc:
            logger.error(
                "Failed to stop actor after lease loss: %s, error=%s",
                requirement_id,
                exc,
            )

    async def _owns_expected_lease(
        self,
        requirement_id: str,
        expected_fencing_token: int | None,
    ) -> bool:
        if self.coordinator is None:
            return expected_fencing_token is None

        get_fencing_token = getattr(self.coordinator, "get_fencing_token", None)
        local_token = get_fencing_token(requirement_id) if callable(get_fencing_token) else None
        if expected_fencing_token is not None and local_token != expected_fencing_token:
            return False

        owns_lease = getattr(self.coordinator, "owns_lease", None)
        if callable(owns_lease):
            return bool(await owns_lease(requirement_id, expected_fencing_token))
        owns_lock = getattr(self.coordinator, "owns_lock", None)
        if callable(owns_lock):
            return bool(await owns_lock(requirement_id))
        return True

    async def _validate_command_lease(
        self,
        requirement_id: str,
        fencing_token: int | None,
    ) -> bool:
        if self.coordinator is None:
            return fencing_token is None
        if fencing_token is None:
            return False
        return await self._owns_expected_lease(requirement_id, fencing_token)

    async def _get_durable_fencing_floor(self, requirement_id: str) -> int:
        getter = getattr(self.event_store, "get_actor_fencing_token", None)
        if not callable(getter):
            raise InfrastructureException(
                "分布式 Actor 需要支持 durable fencing 的 EventStore"
            )
        return int(await asyncio.to_thread(getter, requirement_id))

    async def _claim_durable_fence(
        self,
        requirement_id: str,
        fencing_token: int,
    ) -> None:
        claim = getattr(self.event_store, "claim_actor_fence", None)
        if not callable(claim):
            raise InfrastructureException(
                "分布式 Actor 需要支持 durable fencing 的 EventStore"
            )
        claimed_token = int(
            await asyncio.to_thread(claim, requirement_id, fencing_token)
        )
        if claimed_token != fencing_token:
            raise InfrastructureException(
                f"Actor {requirement_id} 持久化 fencing token 不一致: "
                f"expected={fencing_token}, claimed={claimed_token}"
            )

    async def _get_or_create_actor(
        self,
        requirement_id: str,
        *,
        expected_fencing_token: int | None = None,
    ) -> RequirementActor:
        """
        获取或创建 Actor

        Args:
            requirement_id: 需求 ID

        Returns:
            RequirementActor 实例
        """
        async with self._lock:
            actor = self._actors.get(requirement_id)
            if actor is not None and getattr(actor, "lease_invalidated", False):
                self._actors.pop(requirement_id, None)
                if self.coordinator is not None:
                    await self.coordinator.release_lock(requirement_id)
                if expected_fencing_token is not None:
                    holder = await self.coordinator.get_lock_holder(requirement_id)
                    raise _RemoteActorOwned(requirement_id, holder)
                actor = None

            if actor is not None and self.coordinator is not None:
                if not await self._owns_expected_lease(
                    requirement_id,
                    expected_fencing_token,
                ):
                    self._actors.pop(requirement_id, None)
                    stale_token = int(getattr(actor, "fencing_token", 0) or 0)
                    await self._invalidate_actor_unlocked(
                        requirement_id,
                        actor,
                        fencing_token=stale_token,
                    )
                    await self.coordinator.release_lock(requirement_id)
                    holder = await self.coordinator.get_lock_holder(requirement_id)
                    if holder is not None or expected_fencing_token is not None:
                        raise _RemoteActorOwned(requirement_id, holder)
                    actor = None

            if actor is not None:
                return actor

            await self._ensure_coordination_started()
            await self._ensure_passivation_loop_started()

            if expected_fencing_token is not None and not await self._owns_expected_lease(
                requirement_id,
                expected_fencing_token,
            ):
                holder = await self.coordinator.get_lock_holder(requirement_id)
                raise _RemoteActorOwned(requirement_id, holder)

            lock_acquired = False
            fencing_token: int | None = None
            if self.coordinator is not None:
                durable_floor = await self._get_durable_fencing_floor(requirement_id)
                ensure_floor = getattr(self.coordinator, "ensure_fencing_floor", None)
                if not callable(ensure_floor):
                    raise InfrastructureException(
                        "分布式 Actor 协调器不支持 durable fencing floor"
                    )
                await ensure_floor(requirement_id, durable_floor)
                lock_acquired = await self.coordinator.acquire_lock(requirement_id)
                if not lock_acquired:
                    holder = await self.coordinator.get_lock_holder(requirement_id)
                    raise _RemoteActorOwned(requirement_id, holder)
                get_fencing_token = getattr(
                    self.coordinator,
                    "get_fencing_token",
                    None,
                )
                if callable(get_fencing_token):
                    fencing_token = get_fencing_token(requirement_id)
                if fencing_token is None:
                    await self.coordinator.release_lock(requirement_id)
                    raise InfrastructureException(
                        f"Actor {requirement_id} 未获得 fencing token"
                    )
                if (
                    expected_fencing_token is not None
                    and fencing_token != expected_fencing_token
                ):
                    await self.coordinator.release_lock(requirement_id)
                    holder = await self.coordinator.get_lock_holder(requirement_id)
                    raise _RemoteActorOwned(requirement_id, holder)

            actor = RequirementActor(requirement_id, self.event_store)
            actor.fencing_token = fencing_token
            actor.lease_validator = self._validate_command_lease
            try:
                if fencing_token is not None:
                    await self._claim_durable_fence(requirement_id, fencing_token)
                emit_actor_trace(requirement_id, "activation_started")
                await actor.activate()
                if self.coordinator is not None and not await self._owns_expected_lease(
                    requirement_id,
                    fencing_token,
                ):
                    await self._invalidate_actor_unlocked(
                        requirement_id,
                        actor,
                        fencing_token=int(fencing_token or 0),
                    )
                    await self.coordinator.release_lock(requirement_id)
                    lock_acquired = False
                    holder = await self.coordinator.get_lock_holder(requirement_id)
                    raise _RemoteActorOwned(requirement_id, holder)
                await actor.start()
                self._actors[requirement_id] = actor
                logger.info(f"Actor activated: {requirement_id}, total={len(self._actors)}")
                emit_actor_trace(requirement_id, "activation_completed", total_actors=len(self._actors))
            except Exception:
                if lock_acquired and self.coordinator is not None:
                    await self.coordinator.release_lock(requirement_id)
                emit_actor_trace(
                    requirement_id,
                    "activation_failed",
                    level="error",
                )
                raise

            return actor

    async def activate_actor(self, requirement_id: str):
        """显式激活 Actor（仍受分布式唯一性约束）。"""
        await self._get_or_create_actor(requirement_id)

    async def force_passivate(self, requirement_id: str):
        """
        强制休眠 Actor

        Args:
            requirement_id: 需求 ID
        """
        async with self._lock:
            if requirement_id in self._actors:
                await self._passivate_actor_unlocked(requirement_id, reason="force")

    async def passivate_idle_actors(self, idle_timeout: float = 600):
        """
        休眠空闲的 Actor

        Args:
            idle_timeout: 空闲超时时间（秒）
        """
        async with self._lock:
            current_time = time.time()
            to_passivate = []
            for req_id, actor in self._actors.items():
                idle_time = current_time - actor.last_accessed
                if idle_time >= idle_timeout and actor.mailbox.empty():
                    to_passivate.append(req_id)

            for req_id in to_passivate:
                await self._passivate_actor_unlocked(req_id, reason="idle")

    def get_stats(self) -> Dict:
        """
        获取 Actor 统计信息

        Returns:
            统计信息字典
        """
        active_count = sum(1 for a in self._actors.values() if not a.is_faulted)
        faulted_count = sum(1 for a in self._actors.values() if a.is_faulted)
        mailbox_sizes = {
            req_id: actor.mailbox.qsize()
            for req_id, actor in self._actors.items()
        }

        return {
            "total_actors": len(self._actors),
            "active_actors": active_count,
            "faulted_actors": faulted_count,
            "actor_ids": list(self._actors.keys()),
            "mailbox_sizes": mailbox_sizes
        }

    async def shutdown(self):
        """关闭所有 Actor"""
        if self._passivation_task and not self._passivation_task.done():
            self._passivation_task.cancel()
            try:
                await self._passivation_task
            except asyncio.CancelledError:
                pass

        logger.info(f"Shutting down {len(self._actors)} actors...")
        for requirement_id, actor in list(self._actors.items()):
            try:
                await actor.stop()
                if self.coordinator is not None:
                    await self.coordinator.release_lock(requirement_id)
            except Exception as e:
                logger.error(f"Error stopping actor {requirement_id}: {e}")
        self._actors.clear()

        if self._heartbeat_task and not self._heartbeat_task.done():
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self.coordinator is not None:
            await self.coordinator.cleanup()

        logger.info("All actors shut down")

    async def _passivate_actor_unlocked(self, requirement_id: str, reason: str) -> bool:
        """
        在持有 _lock 前提下尝试回收 Actor。

        快照失败时不卸载，避免状态丢失。
        """
        actor = self._actors.get(requirement_id)
        if actor is None:
            return False

        emit_actor_trace(requirement_id, "passivation_started", reason=reason)
        try:
            await actor.stop()
        except InfrastructureException as exc:
            actor.last_accessed = time.time()
            logger.warning(
                "Passivation skipped due to snapshot failure: %s, reason=%s, error=%s",
                requirement_id,
                reason,
                exc,
            )
            emit_actor_trace(
                requirement_id,
                "passivation_skipped",
                reason=reason,
                level="warning",
                error=str(exc),
            )
            return False

        del self._actors[requirement_id]
        if self.coordinator is not None:
            await self.coordinator.release_lock(requirement_id)

        logger.info(f"Actor passivated: {requirement_id}, total={len(self._actors)}")
        emit_actor_trace(requirement_id, "passivation_completed", reason=reason, total_actors=len(self._actors))
        return True

    async def _passivation_housekeeping_loop(self):
        """自动执行空闲 Actor 回收。"""
        while True:
            try:
                await asyncio.sleep(self.PASSIVATION_SCAN_INTERVAL_SECONDS)
                await self.passivate_idle_actors(self.IDLE_TIMEOUT_SECONDS)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Passivation housekeeping loop error: {exc}")
