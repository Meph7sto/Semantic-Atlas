"""
分布式协调器 - Redis 分布式锁方案

确保同一 requirement_id 在集群中只有一个 Actor 实例
"""

import asyncio
import json
import logging
from typing import Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class DistributedActorCoordinator:
    """
    分布式 Actor 协调器

    使用 Redis 实现分布式锁和实例注册
    """

    def __init__(self, redis_url: str, instance_id: str):
        """
        初始化协调器

        Args:
            redis_url: Redis 连接 URL
            instance_id: 当前实例 ID
        """
        self.redis_url = redis_url
        self.instance_id = instance_id
        self._locks: Dict[str, str] = {}
        self._lock_ttl = 3600  # 锁默认 TTL 1 小时
        self._redis_client = None

    def _get_redis_client(self):
        """获取 Redis 客户端"""
        if self._redis_client is None:
            try:
                import redis.asyncio as redis
                self._redis_client = redis.from_url(self.redis_url)
                logger.info(f"Redis client connected: {self.redis_url}")
            except ImportError:
                logger.warning("redis package not available, distributed coordination disabled")
                self._redis_client = None
        return self._redis_client

    def _get_lock_key(self, requirement_id: str) -> str:
        """获取锁键"""
        return f"lock:actor:{requirement_id}"

    def _get_instance_key(self, requirement_id: str) -> str:
        """获取实例键"""
        return f"instance:actor:{requirement_id}"

    def _get_instances_key(self) -> str:
        """获取集群实例列表键"""
        return "instances:actors"

    async def is_available(self) -> bool:
        """
        检查 Redis 是否可用

        Returns:
            True 如果可用，False 否则
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return False

        try:
            await redis_client.ping()
            return True
        except Exception as e:
            logger.warning(f"Redis not available: {e}")
            return False

    async def acquire_lock(self, requirement_id: str, ttl: Optional[int] = None) -> bool:
        """
        获取分布式锁

        Args:
            requirement_id: 需求 ID
            ttl: 锁超时时间（秒），默认使用实例配置

        Returns:
            True 如果获取成功，False 否则
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            # Redis 不可用，降级为本地锁（总是成功）
            logger.debug(f"Redis unavailable, allowing local lock for: {requirement_id}")
            self._locks[requirement_id] = self.instance_id
            return True

        lock_ttl = ttl or self._lock_ttl
        lock_key = self._get_lock_key(requirement_id)
        instance_key = self._get_instance_key(requirement_id)

        try:
            lock_value = f"{self.instance_id}:{asyncio.get_event_loop().time()}"

            # 尝试获取锁
            acquired = await redis_client.set(lock_key, lock_value, nx=True, ex=lock_ttl)

            if acquired:
                # 注册实例
                await redis_client.set(instance_key, self.instance_id, ex=lock_ttl)
                self._locks[requirement_id] = lock_value
                logger.info(f"Lock acquired: {requirement_id} by {self.instance_id}")
                return True
            else:
                # 检查持有者
                holder = await redis_client.get(instance_key)
                logger.debug(f"Lock held by: {holder}")
                return False

        except Exception as e:
            logger.error(f"Error acquiring lock for {requirement_id}: {e}")
            return False

    async def release_lock(self, requirement_id: str):
        """
        释放分布式锁

        Args:
            requirement_id: 需求 ID
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            # Redis 不可用，清理本地锁
            self._locks.pop(requirement_id, None)
            return

        lock_key = self._get_lock_key(requirement_id)
        instance_key = self._get_instance_key(requirement_id)
        lock_value = self._locks.get(requirement_id)

        try:
            if lock_value:
                # Lua 脚本确保原子性：只有持有者才能释放
                script = """
                if redis.call("GET", KEYS[1]) == ARGV[1] then
                    redis.call("DEL", KEYS[1])
                    redis.call("DEL", KEYS[2])
                    return 1
                else
                    return 0
                end
                """
                await redis_client.eval(script, 2, lock_key, instance_key, lock_value)

            del self._locks[requirement_id]
            logger.info(f"Lock released: {requirement_id}")

        except Exception as e:
            logger.error(f"Error releasing lock for {requirement_id}: {e}")

    async def forward_request(self, requirement_id: str, command: Dict) -> Optional[Dict]:
        """
        转发请求到持有锁的节点

        Args:
            requirement_id: 需求 ID
            command: 命令数据

        Returns:
            转发结果，或 None（转发失败）
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return None

        instance_key = self._get_instance_key(requirement_id)

        try:
            holder = await redis_client.get(instance_key)
            if not holder:
                return None

            # TODO: 实现节点间 RPC 通信
            # 这里需要实现节点间通信机制，如：
            # - HTTP RPC 调用
            # - Redis Pub/Sub 通信
            # - gRPC 通信
            logger.warning(
                f"Request forwarding not implemented: {requirement_id} -> {holder}. "
                f"Consider implementing node-to-node RPC."
            )
            return None

        except Exception as e:
            logger.error(f"Error forwarding request: {e}")
            return None

    async def register_instance(self, metadata: Optional[Dict] = None):
        """
        注册当前实例到集群

        Args:
            metadata: 实例元数据（可选）
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return

        try:
            instance_info = {
                "instance_id": self.instance_id,
                "registered_at": datetime.utcnow().isoformat(),
                "metadata": metadata or {}
            }

            await redis_client.hset(
                self._get_instances_key(),
                self.instance_id,
                json.dumps(instance_info, ensure_ascii=False)
            )
            logger.info(f"Instance registered: {self.instance_id}")

        except Exception as e:
            logger.error(f"Error registering instance: {e}")

    async def unregister_instance(self):
        """从集群注销当前实例"""
        redis_client = self._get_redis_client()
        if redis_client is None:
            return

        try:
            await redis_client.hdel(self._get_instances_key(), self.instance_id)
            logger.info(f"Instance unregistered: {self.instance_id}")

        except Exception as e:
            logger.error(f"Error unregistering instance: {e}")

    async def get_cluster_instances(self) -> Dict[str, Dict]:
        """
        获取集群所有实例

        Returns:
            实例 ID 到实例信息的映射
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return {}

        try:
            instances = await redis_client.hgetall(self._get_instances_key())
            return {
                k.decode() if isinstance(k, bytes) else k: json.loads(v)
                for k, v in instances.items()
            }
        except Exception as e:
            logger.error(f"Error getting cluster instances: {e}")
            return {}

    async def get_lock_holder(self, requirement_id: str) -> Optional[str]:
        """
        获取锁持有者

        Args:
            requirement_id: 需求 ID

        Returns:
            持有锁的实例 ID，或 None
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return None

        instance_key = self._get_instance_key(requirement_id)

        try:
            holder = await redis_client.get(instance_key)
            if holder:
                return holder.decode() if isinstance(holder, bytes) else holder
            return None
        except Exception as e:
            logger.error(f"Error getting lock holder: {e}")
            return None

    async def heartbeat(self, interval: float = 30.0):
        """
        心跳维持锁

        Args:
            interval: 心跳间隔（秒）
        """
        redis_client = self._get_redis_client()
        if redis_client is None:
            return

        logger.info(f"Starting heartbeat, interval={interval}s")

        while True:
            try:
                # 更新实例注册
                await self.register_instance()

                # 刷新所有持有的锁
                for req_id in list(self._locks.keys()):
                    await self._renew_lock(req_id)

            except Exception as e:
                logger.error(f"Error in heartbeat: {e}")

            await asyncio.sleep(interval)

    async def _renew_lock(self, requirement_id: str):
        """续期锁"""
        redis_client = self._get_redis_client()
        if redis_client is None:
            return

        lock_key = self._get_lock_key(requirement_id)
        instance_key = self._get_instance_key(requirement_id)
        lock_value = self._locks.get(requirement_id)

        if not lock_value:
            return

        try:
            # 更新实例键的 TTL
            await redis_client.expire(instance_key, self._lock_ttl)
            # 键的 TTL 会在下次续期时更新
        except Exception as e:
            logger.error(f"Error renewing lock for {requirement_id}: {e}")

    async def cleanup(self):
        """清理资源"""
        # 释放所有锁
        for req_id in list(self._locks.keys()):
            await self.release_lock(req_id)

        # 注销实例
        await self.unregister_instance()

        # 关闭 Redis 连接
        if self._redis_client:
            await self._redis_client.close()
            logger.info("Redis client closed")
