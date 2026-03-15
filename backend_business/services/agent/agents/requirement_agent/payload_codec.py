"""Prompt payload format normalization and serialization helpers."""

from __future__ import annotations

import json
import re
from typing import Any

from .constants import (
    ALLOWED_PROMPT_PAYLOAD_FORMATS,
    DEFAULT_PROMPT_PAYLOAD_FORMAT,
    PROMPT_PAYLOAD_FORMAT_JSON,
    PROMPT_PAYLOAD_FORMAT_YAML,
)


def normalize_prompt_payload_format(
    value: Any,
    *,
    default: str = DEFAULT_PROMPT_PAYLOAD_FORMAT,
) -> str:
    if default not in ALLOWED_PROMPT_PAYLOAD_FORMATS:
        default = DEFAULT_PROMPT_PAYLOAD_FORMAT
    if not isinstance(value, str):
        return default
    normalized = value.strip().lower()
    if normalized in ALLOWED_PROMPT_PAYLOAD_FORMATS:
        return normalized
    return default


def _is_scalar(value: Any) -> bool:
    return isinstance(value, (str, int, float, bool)) or value is None


def _markdown_inline_scalar(value: Any) -> str:
    if value is None:
        return "`null`"
    if isinstance(value, bool):
        return "`true`" if value else "`false`"
    if isinstance(value, (int, float)):
        return f"`{value}`"
    text = str(value).strip()
    if not text:
        return "`\"\"`"
    if "\n" in text or len(text) > 120:
        return f"\n```\n{text}\n```"
    return f"`{text}`"


def _render_markdown_nested_lines(value: Any, *, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    if _is_scalar(value):
        return [f"{prefix}- {_markdown_inline_scalar(value)}"]

    lines: list[str] = []
    if isinstance(value, dict):
        if not value:
            return [f"{prefix}- {{}}"]
        for key, item in value.items():
            key_text = str(key)
            if _is_scalar(item):
                lines.append(f"{prefix}- **{key_text}**: {_markdown_inline_scalar(item)}")
            else:
                lines.append(f"{prefix}- **{key_text}**:")
                lines.extend(_render_markdown_nested_lines(item, indent=indent + 1))
        return lines

    if isinstance(value, list):
        if not value:
            return [f"{prefix}- []"]
        for item in value:
            if _is_scalar(item):
                lines.append(f"{prefix}- {_markdown_inline_scalar(item)}")
            else:
                lines.append(f"{prefix}-")
                lines.extend(_render_markdown_nested_lines(item, indent=indent + 1))
        return lines

    return [f"{prefix}- {_markdown_inline_scalar(str(value))}"]


def _render_markdown_payload(payload: Any, *, title: str) -> str:
    lines = [f"## {title}"]
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key)
            if _is_scalar(value):
                lines.append(f"- **{key_text}**: {_markdown_inline_scalar(value)}")
            else:
                lines.append(f"### {key_text}")
                lines.extend(_render_markdown_nested_lines(value))
        return "\n".join(lines).strip()

    lines.extend(_render_markdown_nested_lines(payload))
    return "\n".join(lines).strip()


def _yaml_key(value: Any) -> str:
    text = str(value)
    if re.match(r"^[a-zA-Z0-9_.-]+$", text):
        return text
    return json.dumps(text, ensure_ascii=False)


def _yaml_scalar(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    lowered = text.lower()
    if not text:
        return '""'
    if "\n" in text or text != text.strip():
        return json.dumps(text, ensure_ascii=False)
    if any(char in text for char in (":", "#", "{", "}", "[", "]", ",")):
        return json.dumps(text, ensure_ascii=False)
    if lowered in {"null", "true", "false", "yes", "no", "on", "off"}:
        return json.dumps(text, ensure_ascii=False)
    return text


def _render_yaml_lines(value: Any, *, indent: int = 0) -> list[str]:
    prefix = "  " * indent
    if _is_scalar(value):
        return [f"{prefix}{_yaml_scalar(value)}"]

    lines: list[str] = []
    if isinstance(value, dict):
        if not value:
            return [f"{prefix}{{}}"]
        for key, item in value.items():
            key_text = _yaml_key(key)
            if _is_scalar(item):
                lines.append(f"{prefix}{key_text}: {_yaml_scalar(item)}")
            else:
                lines.append(f"{prefix}{key_text}:")
                lines.extend(_render_yaml_lines(item, indent=indent + 1))
        return lines

    if isinstance(value, list):
        if not value:
            return [f"{prefix}[]"]
        for item in value:
            if _is_scalar(item):
                lines.append(f"{prefix}- {_yaml_scalar(item)}")
            else:
                lines.append(f"{prefix}-")
                lines.extend(_render_yaml_lines(item, indent=indent + 1))
        return lines

    return [f"{prefix}{_yaml_scalar(str(value))}"]


def serialize_prompt_payload(
    payload: Any,
    *,
    prompt_payload_format: str,
    markdown_title: str,
) -> str:
    normalized_format = normalize_prompt_payload_format(prompt_payload_format)
    if normalized_format == PROMPT_PAYLOAD_FORMAT_JSON:
        return json.dumps(payload, ensure_ascii=False)
    if normalized_format == PROMPT_PAYLOAD_FORMAT_YAML:
        return "\n".join(_render_yaml_lines(payload)).strip()
    return _render_markdown_payload(payload, title=markdown_title)

