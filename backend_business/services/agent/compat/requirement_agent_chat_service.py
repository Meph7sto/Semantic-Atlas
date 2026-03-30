"""Compatibility wrapper for requirement agent chat service.

Main implementation:
backend_business.services.agent.agents.requirement_agent
"""

from backend_business.services.agent.agents.requirement_agent import (
    ALLOWED_PROMPT_PAYLOAD_FORMATS,
    DEFAULT_PROMPT_PAYLOAD_FORMAT,
    PROMPT_PAYLOAD_FORMAT_JSON,
    PROMPT_PAYLOAD_FORMAT_MARKDOWN,
    PROMPT_PAYLOAD_FORMAT_YAML,
    RequirementAgentChatService,
    _RuntimeGraphRecorder,
    normalize_prompt_payload_format,
    requirement_agent_chat_service,
    serialize_prompt_payload,
)

_normalize_prompt_payload_format = normalize_prompt_payload_format
_serialize_prompt_payload = serialize_prompt_payload

__all__ = [
    "ALLOWED_PROMPT_PAYLOAD_FORMATS",
    "DEFAULT_PROMPT_PAYLOAD_FORMAT",
    "PROMPT_PAYLOAD_FORMAT_JSON",
    "PROMPT_PAYLOAD_FORMAT_MARKDOWN",
    "PROMPT_PAYLOAD_FORMAT_YAML",
    "_normalize_prompt_payload_format",
    "_serialize_prompt_payload",
    "_RuntimeGraphRecorder",
    "RequirementAgentChatService",
    "requirement_agent_chat_service",
]

