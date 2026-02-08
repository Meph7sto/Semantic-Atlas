"""Task executor registry - dispatches approved tasks to the right executor."""

from typing import Any, Dict, Optional

from backend_business.services.agent.tasks.executors.base import BaseTaskExecutor


class TaskExecutorRegistry:
    def __init__(self) -> None:
        self._executors: Dict[str, BaseTaskExecutor] = {}

    def register(self, executor: BaseTaskExecutor) -> None:
        self._executors[executor.task_type] = executor

    def get(self, task_type: str) -> BaseTaskExecutor:
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
        return self.get(task_type).execute(payload, actor, conn=conn)


task_executor_registry = TaskExecutorRegistry()

# ---- Register built-in executors ----
from backend_business.services.agent.tasks.executors.requirement_update import (  # noqa
    RequirementUpdateExecutor,
)

task_executor_registry.register(RequirementUpdateExecutor())
