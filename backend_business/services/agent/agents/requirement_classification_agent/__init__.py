"""Requirement classification agent package with lazy runtime exports."""

from __future__ import annotations

from typing import Any

__all__ = [
    "RequirementClassificationGraphRecorder",
    "RequirementClassificationAgentService",
    "requirement_classification_agent_service",
]


def __getattr__(name: str) -> Any:
    if name == "RequirementClassificationGraphRecorder":
        from .runtime_graph_recorder import RequirementClassificationGraphRecorder

        return RequirementClassificationGraphRecorder
    if name in {"RequirementClassificationAgentService", "requirement_classification_agent_service"}:
        from .service import (
            RequirementClassificationAgentService,
            requirement_classification_agent_service,
        )

        return {
            "RequirementClassificationAgentService": RequirementClassificationAgentService,
            "requirement_classification_agent_service": requirement_classification_agent_service,
        }[name]
    raise AttributeError(name)
