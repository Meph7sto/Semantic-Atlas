"""
中间件 - 熔断器、重试策略
"""

import logging
import time
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class RetryPolicy:
    """重试策略"""
    max_attempts: int = 3
    backoff_base: float = 2.0
    max_backoff: float = 60.0
    jitter: bool = True  # 添加随机抖动避免惊群效应

    def get_backoff(self, attempt: int) -> float:
        """
        获取退避时间

        Args:
            attempt: 尝试次数（从 0 开始）

        Returns:
            退避时间（秒）
        """
        if attempt == 0:
            return 0

        base = min(self.backoff_base ** attempt, self.max_backoff)

        if self.jitter:
            import random
            # 添加 +/- 20% 的随机抖动
            jitter_factor = 0.8 + (random.random() * 0.4)
            return base * jitter_factor

        return base


class CircuitBreaker:
    """熔断器

    状态机:
    - CLOSED: 正常状态，允许请求通过
    - OPEN: 熔断状态，直接拒绝请求
    - HALF_OPEN: 半开状态，允许部分请求测试是否恢复
    """

    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0,
                 success_threshold: int = 2, rolling_window: int = 100):
        """
        初始化熔断器

        Args:
            failure_threshold: 失败阈值，连续失败多少次后熔断
            recovery_timeout: 恢复超时时间（秒），OPEN 状态等待多久进入 HALF_OPEN
            success_threshold: 成功阈值，HALF_OPEN 状态需要连续成功多少次才能进入 CLOSED
            rolling_window: 滑动窗口大小，用于计算失败率
        """
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.success_threshold = success_threshold

        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: Optional[float] = None
        self._last_success_time: Optional[float] = None
        self._state = "closed"  # closed, open, half_open

        self._total_requests = 0
        self._total_failures = 0

    def record_success(self):
        """记录成功"""
        self._success_count += 1
        self._total_requests += 1
        self._last_success_time = time.time()

        if self._state == "half_open":
            if self._success_count >= self.success_threshold:
                self._state = "closed"
                self._failure_count = 0
                logger.info(f"Circuit breaker CLOSED after {self._success_count} consecutive successes")
        else:
            self._failure_count = 0

    def record_failure(self):
        """记录失败"""
        self._failure_count += 1
        self._total_failures += 1
        self._total_requests += 1
        self._last_failure_time = time.time()

        if self._state == "half_open":
            # 半开状态下失败，重新打开熔断器
            self._state = "open"
            self._success_count = 0
            logger.info("Circuit breaker OPEN after failure in HALF_OPEN state")
        elif self._failure_count >= self.failure_threshold:
            self._state = "open"
            logger.warning(f"Circuit breaker OPEN after {self._failure_count} consecutive failures")

    def is_open(self) -> bool:
        """
        检查熔断器是否打开

        Returns:
            True 如果熔断器打开或半开，False 否则
        """
        if self._state == "closed":
            return False

        if self._state == "open":
            # 检查是否可以进入半开状态
            if self._last_failure_time and time.time() - self._last_failure_time > self.recovery_timeout:
                self._state = "half_open"
                self._success_count = 0
                logger.info("Circuit breaker HALF_OPEN, testing for recovery")
                return False
            return True

        return False  # half_open

    def get_state(self) -> str:
        """
        获取当前状态

        Returns:
            状态字符串
        """
        return self._state

    def get_stats(self) -> dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        failure_rate = 0.0
        if self._total_requests > 0:
            failure_rate = self._total_failures / self._total_requests

        return {
            "state": self._state,
            "consecutive_failures": self._failure_count,
            "consecutive_successes": self._success_count,
            "total_requests": self._total_requests,
            "total_failures": self._total_failures,
            "failure_rate": failure_rate,
            "last_failure_time": self._last_failure_time,
            "last_success_time": self._last_success_time
        }

    def reset(self):
        """重置熔断器"""
        self._failure_count = 0
        self._success_count = 0
        self._state = "closed"
        self._total_requests = 0
        self._total_failures = 0
        logger.info("Circuit breaker reset")


class RateLimiter:
    """速率限制器 - 令牌桶算法"""

    def __init__(self, rate: float = 10.0, capacity: int = 10):
        """
        初始化速率限制器

        Args:
            rate: 令牌生成速率（个/秒）
            capacity: 桶容量
        """
        self.rate = rate
        self.capacity = capacity
        self._tokens = capacity
        self._last_update = time.time()

    def acquire(self, tokens: int = 1) -> bool:
        """
        获取令牌

        Args:
            tokens: 需要的令牌数量

        Returns:
            True 如果获取成功，False 否则
        """
        # 补充令牌
        now = time.time()
        elapsed = now - self._last_update
        self._tokens = min(self.capacity, self._tokens + elapsed * self.rate)
        self._last_update = now

        # 检查是否有足够令牌
        if self._tokens >= tokens:
            self._tokens -= tokens
            return True
        return False

    def get_wait_time(self, tokens: int = 1) -> float:
        """
        获取需要等待的时间

        Args:
            tokens: 需要的令牌数量

        Returns:
            等待时间（秒）
        """
        now = time.time()
        elapsed = now - self._last_update
        current_tokens = min(self.capacity, self._tokens + elapsed * self.rate)

        if current_tokens >= tokens:
            return 0.0

        return (tokens - current_tokens) / self.rate
