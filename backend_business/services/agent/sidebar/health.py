"""
健康检查 - Worker 健康状态监控
"""

import asyncio
import logging
from datetime import datetime
from typing import Dict, Optional

logger = logging.getLogger(__name__)


class HealthChecker:
    """健康检查器"""

    def __init__(self):
        # worker_id -> health_check_url
        self._health_urls: Dict[str, str] = {}
        # worker_id -> last_check_time
        self._last_check: Dict[str, datetime] = {}
        # worker_id -> is_healthy
        self._health_status: Dict[str, bool] = {}
        # worker_id -> consecutive_failures
        self._failures: Dict[str, int] = {}
        # health_check_timeout (seconds)
        self._timeout = 5.0

    def register(self, worker_id: str, health_check_url: str):
        """
        注册 Worker 健康检查 URL

        Args:
            worker_id: Worker 标识符
            health_check_url: 健康检查 URL
        """
        self._health_urls[worker_id] = health_check_url
        self._health_status[worker_id] = True
        self._failures[worker_id] = 0
        logger.debug(f"Registered health check: worker={worker_id}, url={health_check_url}")

    def unregister(self, worker_id: str):
        """
        注销 Worker 健康检查

        Args:
            worker_id: Worker 标识符
        """
        self._health_urls.pop(worker_id, None)
        self._last_check.pop(worker_id, None)
        self._health_status.pop(worker_id, None)
        self._failures.pop(worker_id, None)
        logger.debug(f"Unregistered health check: worker={worker_id}")

    async def check(self, worker_id: str) -> bool:
        """
        检查 Worker 健康状态

        Args:
            worker_id: Worker 标识符

        Returns:
            是否健康
        """
        if worker_id not in self._health_urls:
            # 未注册健康检查，默认健康
            return True

        url = self._health_urls[worker_id]
        try:
            import aiohttp
            timeout = aiohttp.ClientTimeout(total=self._timeout)
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=timeout) as resp:
                    is_healthy = resp.status == 200
                    self._update_health_status(worker_id, is_healthy)
                    return is_healthy
        except asyncio.TimeoutError:
            self._update_health_status(worker_id, False)
            logger.warning(f"Health check timeout: {worker_id}")
            return False
        except Exception as e:
            self._update_health_status(worker_id, False)
            logger.warning(f"Health check failed: {worker_id}, {e}")
            return False

    def _update_health_status(self, worker_id: str, is_healthy: bool):
        """更新健康状态"""
        self._health_status[worker_id] = is_healthy
        self._last_check[worker_id] = datetime.utcnow()

        if is_healthy:
            self._failures[worker_id] = 0
        else:
            self._failures[worker_id] = self._failures.get(worker_id, 0) + 1

    def is_healthy(self, worker_id: str) -> bool:
        """
        获取 Worker 健康状态（异步检查结果）

        Args:
            worker_id: Worker 标识符

        Returns:
            是否健康
        """
        return self._health_status.get(worker_id, True)

    def last_check_time(self, worker_id: str) -> Optional[datetime]:
        """
        获取上次检查时间

        Args:
            worker_id: Worker 标识符

        Returns:
            上次检查时间，或 None
        """
        return self._last_check.get(worker_id)

    async def check_all(self) -> Dict[str, bool]:
        """
        检查所有已注册 Worker

        Returns:
            Worker ID 到健康状态的映射
        """
        results = {}
        tasks = []

        for worker_id in self._health_urls:
            tasks.append(self._safe_check_worker(worker_id))

        if tasks:
            results_list = await asyncio.gather(*tasks, return_exceptions=True)
            for i, result in enumerate(results_list):
                worker_id = list(self._health_urls.keys())[i]
                if isinstance(result, Exception):
                    results[worker_id] = False
                else:
                    results[worker_id] = result

        return results

    async def _safe_check_worker(self, worker_id: str) -> bool:
        """安全检查单个 Worker"""
        try:
            return await self.check(worker_id)
        except Exception:
            return False

    async def continuous_check(self, interval: float = 60.0):
        """
        持续健康检查

        Args:
            interval: 检查间隔（秒）
        """
        logger.info(f"Starting continuous health check, interval={interval}s")
        while True:
            try:
                await self.check_all()
            except Exception as e:
                logger.error(f"Error in continuous health check: {e}")
            await asyncio.sleep(interval)

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_workers": len(self._health_urls),
            "healthy_workers": sum(1 for v in self._health_status.values() if v),
            "unhealthy_workers": sum(1 for v in self._health_status.values() if not v),
            "workers": {
                worker_id: {
                    "healthy": self._health_status.get(worker_id, True),
                    "url": url,
                    "last_check": self._last_check.get(worker_id),
                    "consecutive_failures": self._failures.get(worker_id, 0)
                }
                for worker_id, url in self._health_urls.items()
            }
        }
