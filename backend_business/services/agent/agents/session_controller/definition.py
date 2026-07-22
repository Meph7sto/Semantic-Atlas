"""Static definition for the SessionController agent."""

from __future__ import annotations

from backend_business.services.agent.runtime.agent_definition import AgentDefinition

from .prompt_builder import SessionControllerPromptBuilder

SESSION_CONTROLLER_DEFINITION = AgentDefinition(
    agent_type="session_controller",
    container_key="conductor",
    label="Session Controller",
    description="需求工程会话总控、意图判断与委托调度",
    max_tool_call_rounds=8,
    prompt_builder_factory=SessionControllerPromptBuilder,
    capability_policy={
        "policy_id": "session_controller::conductor",
        "scope": "conductor",
    },
    quota_policy={
        "policy_id": "session_controller::conductor::quota",
        "max_rounds": 8,
        "timeout_seconds": 180,
        "max_concurrent_runs": 1,
        "max_parallel_runs_per_scope": 1,
    },
    memory_policy={
        "scope": "container",
        "strict_memory_contract": True,
    },
    selectable=False,
    binding_scope="conductor",
)
