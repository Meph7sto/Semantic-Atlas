"""Agent framework package.
Agent 框架包。

Use `bootstrap()` to ensure all registries are populated exactly once.
使用 `bootstrap()` 确保所有注册表被准确填充一次。
"""

_bootstrapped = False


def bootstrap() -> None:
    """Load built-in executors/tools/agents in the required order.
    按所需顺序加载内置的执行器/工具/Agent。
    """
    global _bootstrapped
    if _bootstrapped:
        return

    # 1. Register task executors (no DB deps for registration itself)
    # 1. 注册任务执行器（注册本身不需要 DB 依赖）
    from backend_business.services.agent.tasks import executor as _  # noqa

    # 2. Register tools
    # 2. 注册工具
    from backend_business.services.agent.tools import requirement_tools as _  # noqa
    from backend_business.services.agent.tools import messaging_tools as _  # noqa

    # 3. Register agent definitions
    # 3. 注册 Agent 定义
    from backend_business.services.agent.agents import requirements_agent as _  # noqa
    from backend_business.services.agent.agents import conductor_agent as _  # noqa

    _bootstrapped = True


# Preserve current behavior: auto-bootstrap when imported.
# 保留当前行为：导入时自动引导。
bootstrap()

# Exported services (may be None if no DB configured)
# 导出的服务（如果未配置 DB 可能为 None）
from backend_business.services.agent.runner import agent_runner  # noqa
from backend_business.services.agent.tasks.queue import agent_task_queue  # noqa
