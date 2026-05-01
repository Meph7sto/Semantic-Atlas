"""Registry for static agent definitions and runtime binding specs."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from backend_business.services.agent.runtime.agent_definition import AgentDefinition

from .binding_bootstrap import extract_tool_names


def _create_requirement_prompt_builder() -> Any:
    from backend_business.services.agent.agents.requirement_agent.prompt_builder import (
        RequirementAgentPromptBuilder,
    )

    return RequirementAgentPromptBuilder()


def _create_conflict_prompt_builder() -> Any:
    from backend_business.services.agent.agents.conflict_detection_agent.prompt_builder import (
        ConflictDetectionPromptBuilder,
    )

    return ConflictDetectionPromptBuilder()


def _create_classification_prompt_builder() -> Any:
    from backend_business.services.agent.agents.requirement_classification_agent.prompt_builder import (
        RequirementClassificationPromptBuilder,
    )

    return RequirementClassificationPromptBuilder()


SESSION_CONTROLLER_DEFINITION = AgentDefinition(
    agent_type="session_controller",
    container_key="conductor",
    label="Session Controller",
    description="需求工程会话总控、意图判断与委托调度",
    max_tool_call_rounds=8,
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
    node_key_prefix="session_controller",
)

REQUIREMENT_AGENT_DEFINITION = AgentDefinition(
    agent_type="requirement_agent",
    container_key="requirement_agent",
    label="Requirement Agent",
    description="需求检索、需求分析、需求修改",
    max_tool_call_rounds=6,
    prompt_builder_factory=_create_requirement_prompt_builder,
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

CONFLICT_DETECTION_AGENT_DEFINITION = AgentDefinition(
    agent_type="conflict_detection",
    container_key="conflict_detection",
    label="Conflict Detection Agent",
    description="需求冲突检测与冲突解释",
    max_tool_call_rounds=6,
    prompt_builder_factory=_create_conflict_prompt_builder,
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

REQUIREMENT_CLASSIFICATION_AGENT_DEFINITION = AgentDefinition(
    agent_type="requirement_classification_agent",
    container_key="requirement_classification_agent",
    label="Requirement Classification Agent",
    description="需求分类、标签归类、类别判断",
    max_tool_call_rounds=6,
    prompt_builder_factory=_create_classification_prompt_builder,
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

STANDALONE_CONFLICT_DETECTION_AGENT_DEFINITION = AgentDefinition(
    agent_type="conflict_detection_agent",
    container_key="conflict_detection_agent",
    label="Conflict Detection Agent",
    description="冲突检测 Agent 独立 API runtime",
    max_tool_call_rounds=6,
    prompt_builder_factory=_create_conflict_prompt_builder,
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


class AgentRegistry:
    """Lookup and binding-spec generation for graph-first agents."""

    def __init__(self, definitions: Iterable[AgentDefinition] = ()) -> None:
        self._definitions_by_agent_type: dict[str, AgentDefinition] = {}
        self._definitions_by_container_key: dict[str, AgentDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: AgentDefinition) -> None:
        self._definitions_by_agent_type[definition.agent_type] = definition
        self._definitions_by_container_key[definition.container_key] = definition

    def get_by_agent_type(self, agent_type: str) -> AgentDefinition | None:
        return self._definitions_by_agent_type.get(agent_type)

    def get_by_container_key(self, container_key: str) -> AgentDefinition | None:
        return self._definitions_by_container_key.get(container_key)

    def require_by_container_key(self, container_key: str) -> AgentDefinition:
        definition = self.get_by_container_key(container_key)
        if definition is None:
            raise KeyError(f"unknown agent container_key: {container_key}")
        return definition

    def all_definitions(self) -> list[AgentDefinition]:
        return list(self._definitions_by_container_key.values())

    def selectable_definitions(self) -> list[AgentDefinition]:
        return [
            definition
            for definition in self.all_definitions()
            if definition.selectable
        ]

    def selectable_containers(self) -> list[dict[str, Any]]:
        return [
            {
                "container_key": definition.container_key,
                "label": definition.label,
                "description": (
                    definition.selectable_description
                    or definition.description
                    or definition.label
                ),
            }
            for definition in self.selectable_definitions()
        ]

    def build_runtime_binding_specs(
        self,
        *,
        tool_executor_resolver: Callable[[AgentDefinition], Any],
        definitions: Iterable[AgentDefinition] | None = None,
    ) -> list[dict[str, Any]]:
        selected_definitions = (
            list(definitions) if definitions is not None else self.all_definitions()
        )
        specs: list[dict[str, Any]] = []
        for definition in selected_definitions:
            tool_executor = tool_executor_resolver(definition)
            capability_policy = self._with_policy_defaults(
                definition.capability_policy,
                policy_id=f"{definition.agent_type}::{definition.container_key}",
                scope=definition.binding_scope or definition.container_key,
            )
            capability_policy["tool_names"] = extract_tool_names(tool_executor)

            quota_policy = self._with_policy_defaults(
                definition.quota_policy,
                policy_id=f"{definition.agent_type}::{definition.container_key}::quota",
            )
            quota_policy.setdefault("max_rounds", definition.max_tool_call_rounds)

            memory_policy = dict(definition.memory_policy or {})
            memory_policy.setdefault("scope", "container")
            memory_policy.setdefault("strict_memory_contract", True)

            specs.append(
                {
                    "container_key": definition.container_key,
                    "agent_type": definition.agent_type,
                    "runtime_profile": definition.runtime_profile,
                    "implementation_type": definition.implementation_type,
                    "capability_policy_json": capability_policy,
                    "quota_policy_json": quota_policy,
                    "memory_policy_json": memory_policy,
                }
            )
        return specs

    @staticmethod
    def _with_policy_defaults(
        policy: dict[str, Any] | None,
        *,
        policy_id: str,
        scope: str | None = None,
    ) -> dict[str, Any]:
        normalized = dict(policy or {})
        normalized.setdefault("policy_id", policy_id)
        if scope is not None:
            normalized.setdefault("scope", scope)
        return normalized


def create_builtin_agent_registry() -> AgentRegistry:
    return AgentRegistry(
        (
            SESSION_CONTROLLER_DEFINITION,
            REQUIREMENT_AGENT_DEFINITION,
            CONFLICT_DETECTION_AGENT_DEFINITION,
            REQUIREMENT_CLASSIFICATION_AGENT_DEFINITION,
            STANDALONE_CONFLICT_DETECTION_AGENT_DEFINITION,
        )
    )


BUILTIN_AGENT_REGISTRY = create_builtin_agent_registry()
