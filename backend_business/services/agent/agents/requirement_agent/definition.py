"""Static definition for the requirement-management agent."""

from __future__ import annotations

from backend_business.services.agent.runtime.agent_definition import AgentDefinition

from .prompt_builder import RequirementAgentPromptBuilder


REQUIREMENT_AGENT_DEFINITION = AgentDefinition(
    agent_type="requirement_agent",
    container_key="requirement_agent",
    label="Requirement Agent",
    description="需求检索、需求分析、需求修改",
    max_tool_call_rounds=6,
    prompt_builder_factory=RequirementAgentPromptBuilder,
    capability_policy={
        "policy_id": "session_controller::requirement_agent",
        "scope": "delegated_requirement",
    },
    quota_policy={
        "policy_id": "session_controller::requirement_agent::quota",
        "timeout_seconds": 180,
        "max_concurrent_runs": 4,
        "max_parallel_runs_per_scope": 1,
    },
    memory_policy={
        "scope": "container",
        "strict_memory_contract": True,
    },
    selectable_description="需求检索、需求分析、需求修改",
    binding_scope="delegated_requirement",
    node_key_prefix="requirement_agent",
)
