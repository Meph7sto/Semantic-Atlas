"""Static definition for the conflict-detection agent."""

from __future__ import annotations

from backend_business.services.agent.runtime.agent_definition import AgentDefinition

from .prompt_builder import ConflictDetectionPromptBuilder


CONFLICT_DETECTION_AGENT_DEFINITION = AgentDefinition(
    agent_type="conflict_detection",
    container_key="conflict_detection",
    label="Conflict Detection Agent",
    description="需求冲突检测与冲突解释",
    max_tool_call_rounds=6,
    prompt_builder_factory=ConflictDetectionPromptBuilder,
    capability_policy={
        "policy_id": "session_controller::conflict_detection",
        "scope": "delegated_conflict",
    },
    quota_policy={
        "policy_id": "session_controller::conflict_detection::quota",
        "timeout_seconds": 180,
        "max_concurrent_runs": 4,
        "max_parallel_runs_per_scope": 1,
    },
    memory_policy={
        "scope": "container",
        "strict_memory_contract": True,
    },
    selectable_description="需求冲突检测与冲突解释",
    binding_scope="delegated_conflict",
    node_key_prefix="conflict_agent",
)


STANDALONE_CONFLICT_DETECTION_AGENT_DEFINITION = AgentDefinition(
    agent_type="conflict_detection_agent",
    container_key="conflict_detection_agent",
    label="Conflict Detection Agent",
    description="冲突检测 Agent 独立 API runtime",
    max_tool_call_rounds=6,
    prompt_builder_factory=ConflictDetectionPromptBuilder,
    capability_policy={
        "policy_id": "conflict_detection::runtime",
        "scope": "conflict_detection_agent",
    },
    quota_policy={
        "policy_id": "conflict_detection::runtime::quota",
        "max_rounds": 6,
        "timeout_seconds": 180,
        "max_concurrent_runs": 2,
        "max_parallel_runs_per_scope": 1,
    },
    memory_policy={
        "scope": "container",
        "strict_memory_contract": True,
    },
    selectable=False,
    binding_scope="conflict_detection_agent",
    node_key_prefix="conflict_agent",
)
