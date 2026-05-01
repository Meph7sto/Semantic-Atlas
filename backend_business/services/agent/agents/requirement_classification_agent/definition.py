"""Static definition for the requirement-classification agent."""

from __future__ import annotations

from backend_business.services.agent.runtime.agent_definition import AgentDefinition

from .prompt_builder import RequirementClassificationPromptBuilder


REQUIREMENT_CLASSIFICATION_AGENT_DEFINITION = AgentDefinition(
    agent_type="requirement_classification_agent",
    container_key="requirement_classification_agent",
    label="Requirement Classification Agent",
    description="需求分类、标签归类、类别判断",
    max_tool_call_rounds=6,
    prompt_builder_factory=RequirementClassificationPromptBuilder,
    capability_policy={
        "policy_id": "session_controller::requirement_classification_agent",
        "scope": "delegated_classification",
    },
    quota_policy={
        "policy_id": "session_controller::requirement_classification_agent::quota",
        "timeout_seconds": 180,
        "max_concurrent_runs": 4,
        "max_parallel_runs_per_scope": 1,
    },
    memory_policy={
        "scope": "container",
        "strict_memory_contract": True,
    },
    selectable_description="需求分类、标签归类、类别判断",
    binding_scope="delegated_classification",
    node_key_prefix="requirement_classification_agent",
)
