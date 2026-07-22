"""Session controller agent package with lazy runtime exports."""

from __future__ import annotations

from typing import Any

__all__ = ["SessionControllerService", "session_controller_service"]


def __getattr__(name: str) -> Any:
    if name in __all__:
        from .service import SessionControllerService, session_controller_service

        return {
            "SessionControllerService": SessionControllerService,
            "session_controller_service": session_controller_service,
        }[name]
    raise AttributeError(name)
