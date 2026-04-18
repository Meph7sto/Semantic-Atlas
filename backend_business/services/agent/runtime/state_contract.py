"""Shared runtime-state metadata contract helpers."""

from __future__ import annotations

from typing import Any


SCRATCHPAD_STATE_VERSION = 3
SCRATCHPAD_STATE_BACKEND = "container_state_store"
RUN_STATE_VERSION = 2
RUN_STATE_SOURCE_OF_TRUTH = "agent_runs"


def with_runtime_state_contract(
    meta_json: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stamp runtime graphs with explicit state-contract metadata."""
    merged = dict(meta_json or {})
    merged.setdefault("scratchpad_state_version", SCRATCHPAD_STATE_VERSION)
    merged.setdefault("scratchpad_state_backend", SCRATCHPAD_STATE_BACKEND)
    merged.setdefault("run_state_version", RUN_STATE_VERSION)
    merged.setdefault("run_state_source_of_truth", RUN_STATE_SOURCE_OF_TRUTH)
    return merged
