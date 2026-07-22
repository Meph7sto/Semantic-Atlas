"""Execution context primitives for agent runtime workflows.

Supports two-level context strategy:
  Level 1 — Subgraph-internal incremental accumulation
  Level 2 — Cross-subgraph Scratchpad distillation
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from .scratchpad import Scratchpad


@dataclass(frozen=True)
class ContextEntry:
    """A single context entry passed across runtime stages."""

    kind: str
    value: Any
    node_key: str | None = None
    recorded_at: str | None = None
    subgraph_key: str | None = None


class ExecutionContext:
    """Mutable context store shared by runtime stages.

    When used without subgraph management, behaves as a simple append-only
    context list for single-stage runtime flows.

    When used WITH subgraph management:
      - begin_subgraph(key): clears subgraph-local entries, injects Scratchpad content
      - end_subgraph(key, output): auto-appends stage output to Scratchpad
      - subgraph_entries(): returns only entries belonging to current subgraph
    """

    def __init__(
        self,
        *,
        initial_entries: list[ContextEntry] | None = None,
        scratchpad: Scratchpad | None = None,
    ) -> None:
        self._entries: list[ContextEntry] = list(initial_entries or [])
        self._scratchpad = scratchpad if scratchpad is not None else Scratchpad()
        self._current_subgraph: str | None = None
        self._global_entries: list[ContextEntry] = []  # entries injected from Scratchpad

    @property
    def scratchpad(self) -> Scratchpad:
        return self._scratchpad

    @property
    def current_subgraph(self) -> str | None:
        return self._current_subgraph

    # ---- basic append-only operations ----

    def add(self, entry: ContextEntry) -> None:
        tagged = ContextEntry(
            kind=entry.kind,
            value=entry.value,
            node_key=entry.node_key,
            recorded_at=entry.recorded_at,
            subgraph_key=self._current_subgraph,
        )
        self._entries.append(tagged)

    def extend(self, entries: list[ContextEntry]) -> None:
        for entry in entries:
            self.add(entry)

    def snapshot(self) -> list[ContextEntry]:
        return list(self._entries)

    # ---- subgraph lifecycle ----

    def begin_subgraph(
        self,
        subgraph_key: str,
        *,
        task: str | None = None,
    ) -> None:
        """Start a new subgraph stage.

        Starts a new local context scope and injects current Scratchpad
        content as the initial cross-subgraph context for this subgraph.
        """
        self._current_subgraph = subgraph_key
        self._global_entries = []
        # Inject Scratchpad content as global entries for this subgraph
        scratchpad_text = self._scratchpad.format_for_prompt(
            task=task,
            observation_key=f"execution_context:{subgraph_key}",
        )
        if scratchpad_text:
            self._global_entries.append(
                ContextEntry(
                    kind="scratchpad_snapshot",
                    value=scratchpad_text,
                    subgraph_key=subgraph_key,
                )
            )

    def end_subgraph(self, subgraph_key: str, output: Any = None) -> None:
        """End a subgraph stage.

        Auto-appends the subgraph's structured output to Scratchpad.
        """
        if output is not None:
            self._scratchpad.append_stage_output(
                subgraph_key,
                output,
                task_refs=["flow-context"],
            )
        if self._current_subgraph == subgraph_key:
            self._current_subgraph = None

    def local_entries(self, subgraph_key: str | None = None) -> list[ContextEntry]:
        """Get only local entries produced inside a specific subgraph."""
        target = subgraph_key or self._current_subgraph
        if target is None:
            return list(self._entries)
        return [e for e in self._entries if e.subgraph_key == target]

    def subgraph_entries(self, subgraph_key: str | None = None) -> list[ContextEntry]:
        """Get global+local context entries for a specific subgraph (or current)."""
        target = subgraph_key or self._current_subgraph
        if target is None:
            return list(self._entries)
        local_entries = [e for e in self._entries if e.subgraph_key == target]
        global_entries = [e for e in self._global_entries if e.subgraph_key == target]
        return [*global_entries, *local_entries]

    def format_local_for_prompt(self, subgraph_key: str | None = None) -> str:
        """Format local in-subgraph entries for prompt injection."""
        entries = self.local_entries(subgraph_key)
        if not entries:
            return ""

        lines = ["[Subgraph Context — 当前子图连续上下文]"]
        for index, entry in enumerate(entries, 1):
            value = entry.value
            if isinstance(value, (dict, list)):
                value = json.dumps(value, ensure_ascii=False, indent=None)
            lines.append(f"  [{index}] [{entry.kind}] {value}")
        return "\n".join(lines)
