"""Helpers for bootstrapping runtime bindings with explicit tool allowlists."""

from __future__ import annotations

import inspect
from typing import Any


def extract_tool_names(tool_executor: Any) -> list[str]:
    """Return a stable list of tool names exposed by a tool executor."""
    if tool_executor is None:
        return []

    get_tools_list = getattr(tool_executor, "get_tools_list", None)
    if not callable(get_tools_list):
        return []

    try:
        signature = inspect.signature(get_tools_list)
    except (TypeError, ValueError):
        signature = None

    if signature is not None and "context" in signature.parameters:
        raw_tools = get_tools_list(context={}) or []
    else:
        raw_tools = get_tools_list() or []

    tool_names: list[str] = []
    seen: set[str] = set()
    for entry in raw_tools:
        function_payload = entry.get("function") if isinstance(entry, dict) else {}
        tool_name = str((function_payload or {}).get("name") or "").strip()
        if not tool_name or tool_name in seen:
            continue
        seen.add(tool_name)
        tool_names.append(tool_name)
    return tool_names


def ensure_runtime_bindings(
    execution_graph_service: Any,
    binding_specs: list[dict[str, Any]],
) -> None:
    """Persist binding specs idempotently when the graph service supports it."""
    ensure_binding = getattr(
        execution_graph_service,
        "ensure_agent_runtime_binding",
        None,
    )
    if callable(ensure_binding):
        for spec in binding_specs:
            ensure_binding(**spec)
        return

    list_bindings = getattr(
        execution_graph_service,
        "list_agent_runtime_bindings",
        None,
    )
    create_binding = getattr(
        execution_graph_service,
        "create_agent_runtime_binding",
        None,
    )
    if not callable(list_bindings) or not callable(create_binding):
        return

    for spec in binding_specs:
        existing = list_bindings(
            container_key=spec.get("container_key"),
            agent_type=spec.get("agent_type"),
            runtime_profile=spec.get("runtime_profile"),
            enabled_only=False,
        )
        if existing:
            continue
        create_binding(**spec)
