"""Base class for task executors."""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseTaskExecutor(ABC):
    """Subclasses must define `task_type` and implement `execute`."""

    task_type: str

    @abstractmethod
    def execute(
        self,
        payload: Dict[str, Any],
        actor: str,
        conn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute the task and return the result dict."""
        ...

    def confirmation_message(self, task: Dict[str, Any], result: Dict[str, Any]) -> str:
        """Build the chat confirmation message shown after approval.

        Override in subclasses for richer messages.
        """
        return f"✅ **任务已批准并执行成功**\n\n**任务:** {task.get('title', '')}"
