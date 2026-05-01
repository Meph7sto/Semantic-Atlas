"""Experience-target resolution helpers."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

from backend_business.services.agent.execution.topology_instantiator import (
    RuntimeContainer,
    RuntimeSubgraph,
)

_TOOL_LOOP_TARGET_BY_KEY: dict[str, str] = {
    "requirement_agent": "requirement_agent_tool_loop",
    "conflict_detection": "conflict_detection_tool_loop",
    "requirement_classification_agent": "requirement_classification_tool_loop",
    "requirement_classification": "requirement_classification_tool_loop",
}

_CANONICAL_CONTAINER_BY_KEY: dict[str, str] = {
    "requirement_classification": "requirement_classification_agent",
}


@dataclass(frozen=True, slots=True)
class ExperienceTarget:
    """Canonical identifier for a reusable experience skill."""

    target_id: str
    container_key: str
    prompt_builder_kind: str
    node_type: str


def resolve_experience_target_from_subgraph(
    *,
    container: RuntimeContainer,
    subgraph: RuntimeSubgraph,
) -> ExperienceTarget | None:
    """Resolve an experience target directly from runtime graph objects."""

    return resolve_experience_target(
        container_key=container.container_key,
        node_type=subgraph.node_type,
        config_json=subgraph.config_json,
    )


def resolve_experience_target(
    *,
    container_key: str | None = None,
    prompt_builder_kind: str | None = None,
    node_type: str | None = None,
    agent_type: str | None = None,
    config_json: Mapping[str, Any] | None = None,
    context: Mapping[str, Any] | None = None,
) -> ExperienceTarget | None:
    """Resolve an experience target from loosely-typed runtime context."""

    normalized_context = context if isinstance(context, Mapping) else {}
    normalized_config = config_json if isinstance(config_json, Mapping) else {}

    resolved_container_key = _normalize_key(
        container_key
        or normalized_context.get("container_key")
        or normalized_context.get("delegate_agent")
    )
    resolved_agent_type = _normalize_key(
        agent_type or normalized_context.get("agent_type")
    )
    resolved_node_type = _normalize_key(
        node_type
        or normalized_context.get("node_type")
        or normalized_context.get("role_type")
    )
    resolved_prompt_builder = _normalize_key(
        prompt_builder_kind
        or normalized_context.get("prompt_builder_kind")
        or normalized_context.get("prompt_builder")
        or normalized_config.get("prompt_builder")
    )

    canonical_container_key = _canonicalize_container_key(
        resolved_container_key or resolved_agent_type
    )
    target_id = _resolve_target_id(
        container_key=canonical_container_key,
        prompt_builder_kind=resolved_prompt_builder,
        agent_type=resolved_agent_type,
        node_type=resolved_node_type,
    )
    if not target_id:
        return None

    return ExperienceTarget(
        target_id=target_id,
        container_key=canonical_container_key,
        prompt_builder_kind=resolved_prompt_builder,
        node_type=resolved_node_type,
    )


def _resolve_target_id(
    *,
    container_key: str,
    prompt_builder_kind: str,
    agent_type: str,
    node_type: str,
) -> str:
    if prompt_builder_kind.startswith("session_controller_"):
        return prompt_builder_kind

    tool_loop_lookup_keys = [
        container_key,
        agent_type,
    ]
    for lookup_key in tool_loop_lookup_keys:
        if lookup_key in _TOOL_LOOP_TARGET_BY_KEY:
            return _TOOL_LOOP_TARGET_BY_KEY[lookup_key]

    if prompt_builder_kind and container_key:
        return f"{container_key}_{prompt_builder_kind}"

    if container_key and node_type:
        return f"{container_key}_{node_type}"

    return ""


def _canonicalize_container_key(value: str) -> str:
    if not value:
        return ""
    return _CANONICAL_CONTAINER_BY_KEY.get(value, value)


def _normalize_key(value: Any) -> str:
    return str(value or "").strip()
