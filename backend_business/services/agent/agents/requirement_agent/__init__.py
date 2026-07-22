"""Requirement agent package with lazy runtime exports."""

from __future__ import annotations

from typing import Any

__all__ = [
    "ALLOWED_PROMPT_PAYLOAD_FORMATS",
    "DEFAULT_PROMPT_PAYLOAD_FORMAT",
    "PROMPT_PAYLOAD_FORMAT_JSON",
    "PROMPT_PAYLOAD_FORMAT_MARKDOWN",
    "PROMPT_PAYLOAD_FORMAT_YAML",
    "normalize_prompt_payload_format",
    "serialize_prompt_payload",
    "_RuntimeGraphRecorder",
    "RequirementAgentChatService",
    "requirement_agent_chat_service",
]


def __getattr__(name: str) -> Any:
    if name in {
        "ALLOWED_PROMPT_PAYLOAD_FORMATS",
        "DEFAULT_PROMPT_PAYLOAD_FORMAT",
        "PROMPT_PAYLOAD_FORMAT_JSON",
        "PROMPT_PAYLOAD_FORMAT_MARKDOWN",
        "PROMPT_PAYLOAD_FORMAT_YAML",
    }:
        from . import constants

        return getattr(constants, name)
    if name in {"normalize_prompt_payload_format", "serialize_prompt_payload"}:
        from . import payload_codec

        return getattr(payload_codec, name)
    if name == "_RuntimeGraphRecorder":
        from .runtime_graph_recorder import _RuntimeGraphRecorder

        return _RuntimeGraphRecorder
    if name in {"RequirementAgentChatService", "requirement_agent_chat_service"}:
        from .service import RequirementAgentChatService, requirement_agent_chat_service

        return {
            "RequirementAgentChatService": RequirementAgentChatService,
            "requirement_agent_chat_service": requirement_agent_chat_service,
        }[name]
    raise AttributeError(name)
