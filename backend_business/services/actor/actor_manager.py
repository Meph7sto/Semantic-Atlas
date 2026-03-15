"""
ActorManager - 全局 Actor 管理器

负责 Actor 的创建、查找、路由和生命周期管理
"""

import asyncio
import logging
import os
import time
from typing import Dict, Optional

from backend_business.services.event_store.event_store import EventStore
from backend_business.services.agent.coordinator.distributed_coordinator import (
    DistributedActorCoordinator,
)
from backend_business.services.actor.actors.requirement_actor import (
    RequirementActor, InfrastructureException
)
from backend_business.services.actor.dev_trace import emit_actor_trace

logger = logging.getLogger(__name__)


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

        await self.coordinator.register_instance(
            {
                "service": "backend_business",
                "pid": os.getpid(),
            }
        )
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
        actor = await self._get_or_create_actor(requirement_id)
        return await actor.send_command(command)

    async def _get_or_create_actor(self, requirement_id: str) -> RequirementActor:
        """
        获取或创建 Actor

        Args:
            requirement_id: 需求 ID

        Returns:
            RequirementActor 实例
        """
        async with self._lock:
            if requirement_id not in self._actors:
                await self._ensure_coordination_started()
                await self._ensure_passivation_loop_started()

                lock_acquired = False
                if self.coordinator is not None:
                    lock_acquired = await self.coordinator.acquire_lock(requirement_id)
                    if not lock_acquired:
                        holder = await self.coordinator.get_lock_holder(requirement_id)
                        holder_text = holder or "unknown"
                        raise InfrastructureException(
                            f"Actor {requirement_id} 已在实例 {holder_text} 激活，当前实例拒绝并发激活"
                        )

                # 创建新 Actor
                actor = RequirementActor(requirement_id, self.event_store)
                try:
                    emit_actor_trace(requirement_id, "activation_started")
                    await actor.activate()
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

            return self._actors[requirement_id]

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
