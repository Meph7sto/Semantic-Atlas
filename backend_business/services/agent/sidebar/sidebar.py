"""
Sidebar SDK - 基于能力的通信路由

封装 MessageBus，添加健康检查、熔断、重试等非功能性能力
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from backend_business.services.agent.messaging.bus import MessageBus
from backend_business.services.agent.sidebar.capability_registry import (
    Capability, CapabilityRegistry
)
from backend_business.services.agent.sidebar.health import HealthChecker
from backend_business.services.agent.sidebar.middleware import CircuitBreaker, RetryPolicy

logger = logging.getLogger(__name__)


@dataclass
class RouteRequest:
    """路由请求"""
    capability: Capability
    payload: Dict
    timeout: float = 30.0
    require_healthy: bool = True
    metadata: Optional[Dict] = None


@dataclass
class RouteResponse:
    """路由响应"""
    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Optional[Dict] = None


class Sidebar:
    """Sidebar SDK - 能力路由主类"""

    def __init__(self, message_bus: MessageBus):
        self.message_bus = message_bus
        self.capability_registry = CapabilityRegistry()
        self.health_checker = HealthChecker()
        self.circuit_breakers: Dict[str, CircuitBreaker] = {}

        # 初始化熔断器
        self._init_circuit_breakers()

    def _init_circuit_breakers(self):
        """初始化各能力的熔断器"""
        for capability in Capability:
            self.circuit_breakers[capability.value] = CircuitBreaker(
                failure_threshold=5,
                recovery_timeout=60,
                success_threshold=2
            )
            logger.debug(f"Circuit breaker initialized for: {capability.value}")

    def register_worker(self, worker_id: str, capabilities: List[Capability],
                     health_check_url: Optional[str] = None):
        """
        注册 Worker 及其能力

        Args:
            worker_id: Worker 标识符
            capabilities: 能力列表
            health_check_url: 健康检查 URL（可选）
        """
        for capability in capabilities:
            self.capability_registry.register(worker_id, capability)

        if health_check_url:
            self.health_checker.register(worker_id, health_check_url)

        logger.info(f"Worker registered: {worker_id}, capabilities={[c.value for c in capabilities]}")

    def unregister_worker(self, worker_id: str):
        """
        注销 Worker

        Args:
            worker_id: Worker 标识符
        """
        self.capability_registry.unregister(worker_id)
        self.health_checker.unregister(worker_id)
        logger.info(f"Worker unregistered: {worker_id}")

    async def send(self, request: RouteRequest) -> RouteResponse:
        """
        发送能力请求

        Args:
            request: 路由请求

        Returns:
            路由响应
        """
        capability = request.capability

        # 检查熔断器
        breaker = self.circuit_breakers[capability.value]
        if breaker.is_open():
            logger.warning(f"Circuit breaker OPEN for: {capability}")
            return RouteResponse(
                success=False,
                error=f"服务 {capability} 熔断中",
                metadata={"circuit_state": breaker.get_state()}
            )

        # 查找可用 Worker
        if request.require_healthy:
            worker_id = self.capability_registry.get_healthy_worker(capability)
        else:
            worker_id = self.capability_registry.get_any_worker(capability)

        if not worker_id:
            return RouteResponse(
                success=False,
                error=f"无可用 Worker 提供能力: {capability}",
                metadata={"available_workers": self.capability_registry.get_workers_for_capability(capability)}
            )

        try:
            # 发送消息
            response = await self._send_with_retry(
                worker_id, request.payload, request.timeout
            )

            # 成功，重置熔断器
            breaker.record_success()

            return RouteResponse(
                success=True,
                data=response,
                metadata={"worker_id": worker_id}
            )

        except asyncio.TimeoutError as e:
            # 超时，记录失败到熔断器
            breaker.record_failure()
            logger.error(f"Timeout sending to {worker_id}: {e}")
            return RouteResponse(
                success=False,
                error=f"请求超时: {str(e)}",
                metadata={"worker_id": worker_id, "circuit_state": breaker.get_state()}
            )
        except Exception as e:
            # 失败，记录到熔断器
            breaker.record_failure()
            logger.error(f"Send failed: {capability}, worker={worker_id}, {e}")
            return RouteResponse(
                success=False,
                error=str(e),
                metadata={"worker_id": worker_id, "circuit_state": breaker.get_state()}
            )

    async def _send_with_retry(self, worker_id: str, payload: Dict,
                             timeout: float, retry_policy: Optional[RetryPolicy] = None) -> Dict:
        """
        带重试的消息发送

        Args:
            worker_id: Worker ID
            payload: 消息内容
            timeout: 超时时间
            retry_policy: 重试策略

        Returns:
            响应数据
        """
        if retry_policy is None:
            retry_policy = RetryPolicy(max_attempts=3, backoff_base=2.0)

        for attempt in range(retry_policy.max_attempts):
            try:
                # 通过 MessageBus 发送
                response = await asyncio.wait_for(
                    self.message_bus.request_and_wait(
                        recipient=worker_id,
                        payload=payload
                    ),
                    timeout=timeout
                )
                return response.content if hasattr(response, 'content') else response

            except asyncio.TimeoutError:
                if attempt < retry_policy.max_attempts - 1:
                    wait_time = retry_policy.get_backoff(attempt)
                    logger.warning(f"Timeout attempt {attempt + 1}, retrying in {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                else:
                    raise

            except Exception as e:
                if attempt < retry_policy.max_attempts - 1:
                    wait_time = retry_policy.get_backoff(attempt)
                    logger.warning(f"Error attempt {attempt + 1}: {e}, retrying in {wait_time:.2f}s")
                    await asyncio.sleep(wait_time)
                else:
                    raise

    async def health_check(self, capability: Optional[Capability] = None) -> Dict:
        """
        健康检查

        Args:
            capability: 指定能力，None 表示检查所有

        Returns:
            健康状态字典
        """
        if capability:
            workers = self.capability_registry.get_workers_for_capability(capability)
        else:
            workers = self.capability_registry.get_all_workers()

        health_status = {}
        for worker_id in workers:
            is_healthy = await self.health_checker.check(worker_id)
            health_status[worker_id] = {
                "healthy": is_healthy,
                "last_check": self.health_checker.last_check_time(worker_id)
            }

            # 更新能力注册表的健康状态
            self.capability_registry.update_health(worker_id, is_healthy)

        return health_status

    async def health_check_all(self) -> Dict[str, Dict]:
        """
        并行检查所有 Worker 健康状态

        Returns:
            所有 Worker 的健康状态
        """
        return await self.health_checker.check_all()

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "capability_registry": self.capability_registry.get_stats(),
            "health_checker": self.health_checker.get_stats(),
            "circuit_breakers": {
                cap: breaker.get_stats()
                for cap, breaker in self.circuit_breakers.items()
            }
        }

    async def reset_circuit_breaker(self, capability: Optional[Capability] = None):
        """
        重置熔断器

        Args:
            capability: 指定能力，None 表示重置所有
        """
        if capability:
            self.circuit_breakers[capability.value].reset()
            logger.info(f"Circuit breaker reset for: {capability}")
        else:
            for breaker in self.circuit_breakers.values():
                breaker.reset()
            logger.info("All circuit breakers reset")

    def reset_all(self):
        """重置所有状态"""
        self.capability_registry.clear()
        self.health_checker._health_urls.clear()
        self.health_checker._health_status.clear()
        self.health_checker._last_check.clear()
        for breaker in self.circuit_breakers.values():
            breaker.reset()
        logger.info("Sidebar reset complete")
