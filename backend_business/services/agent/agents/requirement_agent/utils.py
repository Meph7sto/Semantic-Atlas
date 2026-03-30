"""Common helpers for requirement agent runtime."""

from __future__ import annotations

import json
import os
import socket
from datetime import datetime, timezone
from typing import Any

from backend_business.config import settings


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def inference_url() -> str:
    return settings.INFERENCE_BASE_URL.rstrip("/")


def safe_json(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def actor_instance_id() -> str:
    configured = settings.ACTOR_INSTANCE_ID
    if configured:
        return configured
    host = os.environ.get("HOSTNAME") or socket.gethostname() or "unknown-host"
    return f"{host}:{os.getpid()}"


def coerce_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if raw_arguments is None:
        return {}
    if isinstance(raw_arguments, dict):
        return dict(raw_arguments)
    if isinstance(raw_arguments, str):
        text = raw_arguments.strip()
        if not text:
            return {}
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("tool arguments 必须是对象")
        return parsed
    raise ValueError("tool arguments 格式无效")

