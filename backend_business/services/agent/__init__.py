"""Agent framework package.

Use `bootstrap()` to ensure all registries are populated exactly once.
"""

_bootstrapped = False


def bootstrap() -> None:
    """Load built-in executors/tools/agents in the required order."""
    global _bootstrapped
    if _bootstrapped:
        return

    # 1. Register task executors (no DB deps for registration itself)
    from backend_business.services.agent.tasks import executor as _  # noqa

    # 2. Register tools
    from backend_business.services.agent.tools import requirement_tools as _  # noqa
    from backend_business.services.agent.tools import messaging_tools as _  # noqa

    # 3. Register agent definitions
    from backend_business.services.agent.agents import requirements_agent as _  # noqa
    from backend_business.services.agent.agents import conductor_agent as _  # noqa

    _bootstrapped = True


# Preserve current behavior: auto-bootstrap when imported.
bootstrap()

# Exported services (may be None if no DB configured)
from backend_business.services.agent.runner import agent_runner  # noqa
from backend_business.services.agent.tasks.queue import agent_task_queue  # noqa
