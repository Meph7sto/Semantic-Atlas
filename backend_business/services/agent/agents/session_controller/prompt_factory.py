"""Prompt-builder factory for SessionController graph subgraphs."""

from __future__ import annotations

from typing import Any

from backend_business.services.agent.execution.prompt_interface import (
    PromptBuilderProtocol,
)

from .graph_prompt_builders import (
    SessionControllerClassificationDelegatePromptBuilder,
    SessionControllerConflictDelegatePromptBuilder,
    SessionControllerDecisionGraphPromptBuilder,
    SessionControllerReplyGraphPromptBuilder,
    SessionControllerRequirementDelegatePromptBuilder,
)


def create_session_controller_prompt_builder(
    *,
    prompt_builder_kind: str,
    subgraph: Any,
    scratchpad: Any,
    context: dict[str, Any],
) -> PromptBuilderProtocol | None:
    """Resolve SessionController-specific graph prompt builders.

    The generic SubgraphRunner calls this optional factory without needing
    to import or understand SessionController prompt-builder names.
    """
    _ = subgraph, scratchpad, context
    if prompt_builder_kind == "session_controller_decision":
        return SessionControllerDecisionGraphPromptBuilder()
    if prompt_builder_kind == "session_controller_final_reply":
        return SessionControllerReplyGraphPromptBuilder(reply_kind="final")
    if prompt_builder_kind == "session_controller_suspend_reply":
        return SessionControllerReplyGraphPromptBuilder(reply_kind="suspend")
    if prompt_builder_kind == "session_controller_requirement_delegate":
        return SessionControllerRequirementDelegatePromptBuilder()
    if prompt_builder_kind == "session_controller_conflict_delegate":
        return SessionControllerConflictDelegatePromptBuilder()
    if prompt_builder_kind == "session_controller_classification_delegate":
        return SessionControllerClassificationDelegatePromptBuilder()
    return None
