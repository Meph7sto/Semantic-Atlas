"""Task executor registry - dispatches approved tasks to the right executor.
任务执行器注册表 - 将已批准的任务分发给正确的执行器。
"""

from typing import Any, Dict, Optional

from backend_business.services.agent.tasks.executors.base import BaseTaskExecutor


class TaskExecutorRegistry:
    """Registry for task executors.
    任务执行器注册表。
    """

    def __init__(self) -> None:
        self._executors: Dict[str, BaseTaskExecutor] = {}

    def register(self, executor: BaseTaskExecutor) -> None:
        """Register a new task executor.
        注册新的任务执行器。
        """
        self._executors[executor.task_type] = executor

    def get(self, task_type: str) -> BaseTaskExecutor:
        """Get an executor by task type.
        按任务类型获取执行器。
        """
        executor = self._executors.get(task_type)
        if not executor:
            raise ValueError(f"No executor registered for task_type: {task_type}")
        return executor

    def execute(
        self,
        task_type: str,
        payload: dict,
        actor: str,
        conn: Optional[Any] = None,
    ) -> dict:
        """Execute a task.
        执行任务。
        """
        return self.get(task_type).execute(payload, actor, conn=conn)


# Global singleton instance
# 全局单例实例
task_executor_registry = TaskExecutorRegistry()

# ---- Register built-in executors ----
# ---- 注册内置执行器 ----
from backend_business.services.agent.tasks.executors.requirement_update import (  # noqa
    RequirementUpdateExecutor,
)

task_executor_registry.register(RequirementUpdateExecutor())
