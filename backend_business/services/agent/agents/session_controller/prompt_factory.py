"""Prompt-builder factory for SessionController graph subgraphs."""

from __future__ import annotations

from typing import Any

from backend_business.services.agent.execution.prompt_interface import (
    PromptBuilderProtocol,
)
from backend_business.services.agent.runtime.agent_registry import (
    BUILTIN_AGENT_REGISTRY,
    AgentRegistry,
)

from .graph_prompt_builders import (
    SessionControllerDecisionGraphPromptBuilder,
    SessionControllerReplyGraphPromptBuilder,
)


def create_session_controller_prompt_builder(
    *,
    prompt_builder_kind: str,
    subgraph: Any,
    scratchpad: Any,
    context: dict[str, Any],
    agent_registry: AgentRegistry | None = None,
) -> PromptBuilderProtocol | None:
    """Resolve SessionController-specific graph prompt builders.

    The generic SubgraphRunner calls this optional factory without needing
    to import or understand SessionController prompt-builder names.
    """
    _ = subgraph, scratchpad, context
    registry = agent_registry or BUILTIN_AGENT_REGISTRY
    if prompt_builder_kind == "session_controller_decision":
        return SessionControllerDecisionGraphPromptBuilder(agent_registry=registry)
    if prompt_builder_kind == "session_controller_final_reply":
        return SessionControllerReplyGraphPromptBuilder(reply_kind="final")
    if prompt_builder_kind == "session_controller_suspend_reply":
        return SessionControllerReplyGraphPromptBuilder(reply_kind="suspend")
    for definition in registry.delegated_definitions():
        delegation = definition.delegation
        if (
            delegation is not None
            and delegation.prompt_builder_kind == prompt_builder_kind
            and definition.delegated_prompt_builder_factory is not None
        ):
            return definition.delegated_prompt_builder_factory()
    return None
