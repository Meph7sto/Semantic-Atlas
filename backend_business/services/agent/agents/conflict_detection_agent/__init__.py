"""Conflict detection agent package with side-effect-free definition imports."""

from __future__ import annotations

from typing import Any

__all__ = ["ConflictDetectionAgentService", "conflict_detection_agent_service"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .service import ConflictDetectionAgentService, conflict_detection_agent_service

        return {
            "ConflictDetectionAgentService": ConflictDetectionAgentService,
            "conflict_detection_agent_service": conflict_detection_agent_service,
        }[name]
    raise AttributeError(name)
