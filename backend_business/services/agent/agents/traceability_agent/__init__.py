"""Requirement traceability agent package with lazy runtime exports."""

from __future__ import annotations

from typing import Any

__all__ = ["TraceabilityAgentService", "traceability_agent_service"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .service import TraceabilityAgentService, traceability_agent_service

        return {
            "TraceabilityAgentService": TraceabilityAgentService,
            "traceability_agent_service": traceability_agent_service,
        }[name]
    raise AttributeError(name)
