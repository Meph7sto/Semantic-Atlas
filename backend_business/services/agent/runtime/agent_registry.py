"""Single catalog for agent definitions, delegation, and runtime bindings."""

from __future__ import annotations

import inspect
from collections.abc import Callable, Iterable, Mapping
from typing import Any

from backend_business.services.agent.agents.conflict_detection_agent.definition import (
    CONFLICT_DETECTION_AGENT_DEFINITION,
    STANDALONE_CONFLICT_DETECTION_AGENT_DEFINITION,
)
from backend_business.services.agent.agents.requirement_agent.definition import (
    REQUIREMENT_AGENT_DEFINITION,
)
from backend_business.services.agent.agents.requirement_classification_agent.definition import (
    REQUIREMENT_CLASSIFICATION_AGENT_DEFINITION,
)
from backend_business.services.agent.agents.session_controller.definition import (
    SESSION_CONTROLLER_DEFINITION,
)
from backend_business.services.agent.agents.traceability_agent.definition import (
    TRACEABILITY_AGENT_DEFINITION,
)
from backend_business.services.agent.runtime.agent_definition import AgentDefinition

from .binding_bootstrap import extract_tool_names

class AgentRegistry:
    """Lookup and binding-spec generation for graph-first agents."""

    def __init__(self, definitions: Iterable[AgentDefinition] = ()) -> None:
        self._definitions_by_agent_type: dict[str, AgentDefinition] = {}
        self._definitions_by_container_key: dict[str, AgentDefinition] = {}
        self._definitions_by_delegation_tool: dict[str, AgentDefinition] = {}
        self._definitions_by_route_key: dict[str, AgentDefinition] = {}
        self._definitions_by_decision_mode: dict[str, AgentDefinition] = {}
        self._definitions_by_result_contract: dict[str, AgentDefinition] = {}
        for definition in definitions:
            self.register(definition)

    def register(self, definition: AgentDefinition) -> None:
        if definition.agent_type in self._definitions_by_agent_type:
            raise ValueError(f"duplicate agent_type: {definition.agent_type}")
        if definition.container_key in self._definitions_by_container_key:
            raise ValueError(f"duplicate container_key: {definition.container_key}")
        delegation = definition.delegation
        if delegation is not None:
            if delegation.tool_name in self._definitions_by_delegation_tool:
                raise ValueError(f"duplicate delegation tool: {delegation.tool_name}")
            if delegation.route_key in self._definitions_by_route_key:
                raise ValueError(f"duplicate delegation route: {delegation.route_key}")
            if delegation.decision_mode in self._definitions_by_decision_mode:
                raise ValueError(
                    f"duplicate delegation decision mode: {delegation.decision_mode}"
                )
            if delegation.result_contract in self._definitions_by_result_contract:
                raise ValueError(
                    f"duplicate delegation result contract: {delegation.result_contract}"
                )
        self._definitions_by_agent_type[definition.agent_type] = definition
        self._definitions_by_container_key[definition.container_key] = definition
        if delegation is not None:
            self._definitions_by_delegation_tool[delegation.tool_name] = definition
            self._definitions_by_route_key[delegation.route_key] = definition
            self._definitions_by_decision_mode[delegation.decision_mode] = definition
            self._definitions_by_result_contract[delegation.result_contract] = definition

    def get_by_agent_type(self, agent_type: str) -> AgentDefinition | None:
        return self._definitions_by_agent_type.get(agent_type)

    def get_by_container_key(self, container_key: str) -> AgentDefinition | None:
        return self._definitions_by_container_key.get(container_key)

    def require_by_container_key(self, container_key: str) -> AgentDefinition:
        definition = self.get_by_container_key(container_key)
        if definition is None:
            raise KeyError(f"unknown agent container_key: {container_key}")
        return definition

    def get_by_delegation_tool(self, tool_name: str) -> AgentDefinition | None:
        return self._definitions_by_delegation_tool.get(tool_name)

    def get_by_route_key(self, route_key: str) -> AgentDefinition | None:
        return self._definitions_by_route_key.get(route_key)

    def get_by_decision_mode(self, decision_mode: str) -> AgentDefinition | None:
        return self._definitions_by_decision_mode.get(decision_mode)

    def get_by_result_contract(self, result_contract: str) -> AgentDefinition | None:
        return self._definitions_by_result_contract.get(result_contract)

    def all_definitions(self) -> list[AgentDefinition]:
        return list(self._definitions_by_container_key.values())

    def selectable_definitions(self) -> list[AgentDefinition]:
        return [
            definition
            for definition in self.all_definitions()
            if definition.selectable
        ]

    def delegated_definitions(self) -> list[AgentDefinition]:
        return [
            definition
            for definition in self.selectable_definitions()
            if definition.delegation is not None
        ]

    def delegation_tool_definitions(self) -> list[dict[str, Any]]:
        return [
            definition.delegation.tool_definition()
            for definition in self.delegated_definitions()
            if definition.delegation is not None
        ]

    def delegation_tool_to_agent(self) -> dict[str, str]:
        return {
            definition.delegation.tool_name: definition.container_key
            for definition in self.delegated_definitions()
            if definition.delegation is not None
        }

    def delegation_tool_to_mode(self) -> dict[str, str]:
        return {
            definition.delegation.tool_name: definition.delegation.decision_mode
            for definition in self.delegated_definitions()
            if definition.delegation is not None
        }

    def build_application_services(self) -> dict[str, Any]:
        services: dict[str, Any] = {}
        for definition in self.delegated_definitions():
            factory = definition.application_service_factory
            if factory is not None:
                services[definition.container_key] = factory()
        return services

    def resolve_tool_executor(
        self,
        *,
        container_key: str,
        services: Mapping[str, Any] | None = None,
        fallback: Any = None,
    ) -> Any:
        definition = self.get_by_container_key(container_key)
        if definition is None:
            return fallback
        available_services = services or {}
        service = available_services.get(container_key) or available_services.get(
            definition.agent_type
        )
        factory = definition.tool_executor_factory
        if factory is not None:
            signature = inspect.signature(factory)
            kwargs: dict[str, Any] = {}
            if "definition" in signature.parameters:
                kwargs["definition"] = definition
            if "service" in signature.parameters:
                kwargs["service"] = service
            if kwargs or not signature.parameters:
                executor = factory(**kwargs)
                if executor is not None:
                    return executor
        if service is not None:
            return getattr(service, "tools", service)
        return fallback

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
        tool_executor_resolver: Callable[[AgentDefinition], Any] | None = None,
        services: Mapping[str, Any] | None = None,
        definitions: Iterable[AgentDefinition] | None = None,
    ) -> list[dict[str, Any]]:
        selected_definitions = (
            list(definitions) if definitions is not None else self.all_definitions()
        )
        specs: list[dict[str, Any]] = []
        for definition in selected_definitions:
            tool_executor = (
                tool_executor_resolver(definition)
                if tool_executor_resolver is not None
                else self.resolve_tool_executor(
                    container_key=definition.container_key,
                    services=services,
                )
            )
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
            TRACEABILITY_AGENT_DEFINITION,
            STANDALONE_CONFLICT_DETECTION_AGENT_DEFINITION,
        )
    )


BUILTIN_AGENT_REGISTRY = create_builtin_agent_registry()

# Catalog is the preferred name for the single extension boundary. Registry
# aliases remain for compatibility with existing imports.
AgentCatalog = AgentRegistry
BUILTIN_AGENT_CATALOG = BUILTIN_AGENT_REGISTRY


def create_builtin_agent_catalog() -> AgentCatalog:
    return create_builtin_agent_registry()
