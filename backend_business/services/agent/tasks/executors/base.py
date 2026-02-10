"""Base class for task executors.
任务执行器的基类。
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class BaseTaskExecutor(ABC):
    """Subclasses must define `task_type` and implement `execute`.
    子类必须定义 `task_type` 并实现 `execute`。
    """

    task_type: str  # The type of task this executor handles; 此执行器处理的任务类型

    @abstractmethod
    def execute(
        self,
        payload: Dict[str, Any],
        actor: str,
        conn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        """Execute the task and return the result dict.
        执行任务并返回结果字典。
        """
        ...

    def confirmation_message(self, task: Dict[str, Any], result: Dict[str, Any]) -> str:
        """Build the chat confirmation message shown after approval.
        构建批准后显示的聊天确认消息。

        Override in subclasses for richer messages.
        在子类中重写以提供更丰富的消息。
        """
        return f"✅ **任务已批准并执行成功**\n\n**任务:** {task.get('title', '')}"
