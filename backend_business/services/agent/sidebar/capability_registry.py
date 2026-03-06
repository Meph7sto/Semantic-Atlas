"""
能力注册表 - Worker 能力与 Worker ID 的映射
"""

import logging
import random
from enum import Enum
from typing import Dict, List, Set, Optional

logger = logging.getLogger(__name__)


class Capability(str, Enum):
    """能力枚举"""
    REQUIREMENT_WRITE = "requirement_write"
    REQUIREMENT_QUERY = "requirement_query"
    LLM_INFERENCE = "llm_inference"
    VECTOR_SEARCH = "vector_search"
    CONFLICT_ANALYSIS = "conflict_analysis"
    TRACE_ANALYSIS = "trace_analysis"
    QUALITY_CHECK = "quality_check"


class CapabilityRegistry:
    """能力注册表"""

    def __init__(self):
        # capability -> Set[worker_id]
        self._capability_to_workers: Dict[Capability, Set[str]] = {}
        # worker_id -> Set[Capability]
        self._worker_to_capabilities: Dict[str, Set[Capability]] = {}
        # worker_id -> is_healthy
        self._worker_health: Dict[str, bool] = {}
        self._lock = None

    def register(self, worker_id: str, capability: Capability):
        """
        注册 Worker 能力

        Args:
            worker_id: Worker 标识符
            capability: 能力类型
        """
        if capability not in self._capability_to_workers:
            self._capability_to_workers[capability] = set()

        if worker_id not in self._worker_to_capabilities:
            self._worker_to_capabilities[worker_id] = set()

        self._capability_to_workers[capability].add(worker_id)
        self._worker_to_capabilities[worker_id].add(capability)
        self._worker_health[worker_id] = True
        logger.debug(f"Registered: worker={worker_id}, capability={capability}")

    def unregister(self, worker_id: str, capability: Optional[Capability] = None):
        """
        注销 Worker 能力

        Args:
            worker_id: Worker 标识符
            capability: 要注销的能力，None 表示注销所有
        """
        if worker_id not in self._worker_to_capabilities:
            return

        if capability:
            self._capability_to_workers[capability].discard(worker_id)
            self._worker_to_capabilities[worker_id].discard(capability)
            if not self._worker_to_capabilities[worker_id]:
                del self._worker_to_capabilities[worker_id]
                self._worker_health.pop(worker_id, None)
        else:
            # 注销所有能力
            for cap in list(self._worker_to_capabilities[worker_id]):
                self._capability_to_workers[cap].discard(worker_id)
            del self._worker_to_capabilities[worker_id]
            self._worker_health.pop(worker_id, None)
        logger.debug(f"Unregistered: worker={worker_id}, capability={capability}")

    def update_health(self, worker_id: str, is_healthy: bool):
        """
        更新 Worker 健康状态

        Args:
            worker_id: Worker 标识符
            is_healthy: 是否健康
        """
        self._worker_health[worker_id] = is_healthy
        logger.debug(f"Health updated: worker={worker_id}, healthy={is_healthy}")

    def get_any_worker(self, capability: Capability) -> Optional[str]:
        """
        获取任意提供该能力的 Worker

        Args:
            capability: 能力类型

        Returns:
            Worker ID，或 None
        """
        workers = self._capability_to_workers.get(capability, set())
        if not workers:
            return None

        # 随机选择（简单负载均衡）
        return random.choice(list(workers))

    def get_healthy_worker(self, capability: Capability) -> Optional[str]:
        """
        获取健康的 Worker

        Args:
            capability: 能力类型

        Returns:
            健康的 Worker ID，或 None
        """
        workers = self._capability_to_workers.get(capability, set())
        if not workers:
            return None

        # 筛选健康的 worker
        healthy_workers = [
            w for w in workers if self._worker_health.get(w, True)
        ]

        if not healthy_workers:
            return None

        # 随机选择
        return random.choice(healthy_workers)

    def get_workers_for_capability(self, capability: Capability) -> List[str]:
        """
        获取提供指定能力的所有 Worker

        Args:
            capability: 能力类型

        Returns:
            Worker ID 列表
        """
        return list(self._capability_to_workers.get(capability, set()))

    def get_all_workers(self) -> List[str]:
        """
        获取所有 Worker

        Returns:
            Worker ID 列表
        """
        return list(self._worker_to_capabilities.keys())

    def get_worker_capabilities(self, worker_id: str) -> List[Capability]:
        """
        获取 Worker 的所有能力

        Args:
            worker_id: Worker 标识符

        Returns:
            能力列表
        """
        return list(self._worker_to_capabilities.get(worker_id, set()))

    def get_stats(self) -> Dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_workers": len(self._worker_to_capabilities),
            "workers": {
                worker_id: {
                    "capabilities": [c.value for c in caps],
                    "healthy": self._worker_health.get(worker_id, True)
                }
                for worker_id, caps in self._worker_to_capabilities.items()
            },
            "capabilities": {
                cap.value: {
                    "worker_count": len(workers),
                    "workers": list(workers)
                }
                for cap, workers in self._capability_to_workers.items()
            }
        }

    def clear(self):
        """清空所有注册"""
        self._capability_to_workers.clear()
        self._worker_to_capabilities.clear()
        self._worker_health.clear()
        logger.debug("Capability registry cleared")
