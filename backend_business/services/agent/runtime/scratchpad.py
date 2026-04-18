"""Scratchpad — container-scoped persistent working memory for cross-subgraph context distillation.

Design reference: docs/Agent方案_updated(1).md §上下文管理 (lines 324-348).

Each container owns its own scratchpad view. All subgraphs within the same
container can read and write to it, but it is invisible across containers.

Three entry types:
  - note          — free-form observations written by the LLM via scratchpad_write tool
  - tool_excerpt  — selective excerpts of tool-call results (marked readonly)
  - stage_output  — structured output auto-appended when a subgraph completes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import threading
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class ScratchpadEntry:
    """A single Scratchpad entry."""

    entry_type: str  # "note" | "tool_excerpt" | "stage_output"
    content: Any
    source_subgraph: str | None = None
    container_key: str | None = None
    readonly: bool = False
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_type": self.entry_type,
            "content": self.content,
            "source_subgraph": self.source_subgraph,
            "container_key": self.container_key,
            "readonly": self.readonly,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScratchpadEntry":
        return cls(
            entry_type=data.get("entry_type", "note"),
            content=data.get("content"),
            source_subgraph=data.get("source_subgraph"),
            container_key=data.get("container_key"),
            readonly=data.get("readonly", False),
            created_at=data.get("created_at") or _utc_now_iso(),
        )


@dataclass
class _ScratchpadState:
    entries: list[ScratchpadEntry] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)
    legacy_shared_visible: bool = False


class Scratchpad:
    """Container-scoped persistent working memory.

    Usage:
        pad = Scratchpad()
        pad.write("note", "user wants to modify login page", source_subgraph="analysis")
        pad.write("tool_excerpt", {"req_id": "R-1", "title": "Login"}, source_subgraph="fetch", readonly=True)
        entries = pad.read()                      # all entries
        entries = pad.read(filter_type="note")     # only notes
    """

    def __init__(
        self,
        *,
        initial_entries: list[ScratchpadEntry] | None = None,
        _state: _ScratchpadState | None = None,
        _bound_container_key: str | None = None,
    ) -> None:
        self._state = _state or _ScratchpadState(entries=list(initial_entries or []))
        self._bound_container_key = _bound_container_key

    @property
    def bound_container_key(self) -> str | None:
        return self._bound_container_key

    def for_container(self, container_key: str | None) -> "Scratchpad":
        """Return a container-bound view that shares the same underlying storage."""
        return Scratchpad(
            _state=self._state,
            _bound_container_key=container_key,
        )

    def _has_bound_entries(self) -> bool:
        if self._bound_container_key is None:
            return False
        return any(
            entry.container_key == self._bound_container_key
            for entry in self._state.entries
        )

    def _visible_entries_unlocked(self) -> list[ScratchpadEntry]:
        if self._bound_container_key is None:
            return [
                entry
                for entry in self._state.entries
                if entry.container_key is None
            ]

        scoped_entries = [
            entry
            for entry in self._state.entries
            if entry.container_key == self._bound_container_key
        ]
        if scoped_entries:
            return scoped_entries

        if self._state.legacy_shared_visible:
            return [
                entry
                for entry in self._state.entries
                if entry.container_key is None
            ]
        return []

    def _materialize_legacy_scope_for_write_unlocked(self) -> None:
        if self._bound_container_key is None:
            return
        if not self._state.legacy_shared_visible:
            return
        if self._has_bound_entries():
            return

        legacy_entries = [
            entry
            for entry in self._state.entries
            if entry.container_key is None
        ]
        if not legacy_entries:
            return

        self._state.entries.extend(
            ScratchpadEntry(
                entry_type=entry.entry_type,
                content=entry.content,
                source_subgraph=entry.source_subgraph,
                container_key=self._bound_container_key,
                readonly=entry.readonly,
                created_at=entry.created_at,
            )
            for entry in legacy_entries
        )

    # ---- write ----

    def write(
        self,
        entry_type: str,
        content: Any,
        *,
        source_subgraph: str | None = None,
        readonly: bool = False,
    ) -> None:
        """Write a new entry.  tool_excerpt entries are always readonly."""
        if entry_type == "tool_excerpt":
            readonly = True
        with self._state.lock:
            self._materialize_legacy_scope_for_write_unlocked()
            self._state.entries.append(
                ScratchpadEntry(
                    entry_type=entry_type,
                    content=content,
                    source_subgraph=source_subgraph,
                    container_key=self._bound_container_key,
                    readonly=readonly,
                )
            )

    def append_stage_output(self, subgraph_key: str, output: Any) -> None:
        """Auto-append structured output when a subgraph completes (called by runtime)."""
        with self._state.lock:
            self._materialize_legacy_scope_for_write_unlocked()
            self._state.entries.append(
                ScratchpadEntry(
                    entry_type="stage_output",
                    content=output,
                    source_subgraph=subgraph_key,
                    container_key=self._bound_container_key,
                    readonly=True,
                )
            )

    # ---- read ----

    def read(
        self,
        *,
        filter_type: str | None = None,
        after_subgraph: str | None = None,
    ) -> list[ScratchpadEntry]:
        """Read all entries, optionally filtered.

        Args:
            filter_type: Only return entries of this type.
            after_subgraph: Only return entries created after the last entry
                            whose source_subgraph matches this key.
        """
        with self._state.lock:
            entries = list(self._visible_entries_unlocked())

        if after_subgraph is not None:
            cutoff_index = -1
            for i, entry in enumerate(entries):
                if entry.source_subgraph == after_subgraph:
                    cutoff_index = i
            if cutoff_index >= 0:
                entries = entries[cutoff_index + 1:]

        if filter_type is not None:
            entries = [e for e in entries if e.entry_type == filter_type]

        return entries

    # ---- serialization ----

    def snapshot(self) -> list[dict[str, Any]]:
        """Serialize entries visible to the current container-bound view."""
        with self._state.lock:
            return [entry.to_dict() for entry in self._visible_entries_unlocked()]

    def snapshot_all(self) -> list[dict[str, Any]]:
        """Serialize every container's entries for graph-level persistence."""
        with self._state.lock:
            return [entry.to_dict() for entry in self._state.entries]

    @classmethod
    def from_snapshot(cls, data: list[dict[str, Any]]) -> "Scratchpad":
        """Restore a single scratchpad view from serialized entries."""
        entries = [ScratchpadEntry.from_dict(item) for item in (data or [])]
        return cls(initial_entries=entries)

    @classmethod
    def from_store_snapshot(cls, data: list[dict[str, Any]]) -> "Scratchpad":
        """Restore a graph-level scratchpad store from serialized entries."""
        entries = [ScratchpadEntry.from_dict(item) for item in (data or [])]
        legacy_shared_visible = bool(entries) and not any(
            entry.container_key is not None
            for entry in entries
        )
        return cls(
            _state=_ScratchpadState(
                entries=entries,
                legacy_shared_visible=legacy_shared_visible,
            )
        )

    def format_for_prompt(self) -> str:
        """Format current entries as human-readable text for LLM system prompt injection."""
        with self._state.lock:
            entries = list(self._visible_entries_unlocked())
        if not entries:
            return ""
        lines = ["[Scratchpad — 跨阶段工作记忆]"]
        for i, entry in enumerate(entries, 1):
            source = f" (from: {entry.source_subgraph})" if entry.source_subgraph else ""
            tag = entry.entry_type.upper()
            content = entry.content
            if isinstance(content, dict):
                import json
                content = json.dumps(content, ensure_ascii=False, indent=None)
            lines.append(f"  [{i}] [{tag}]{source}: {content}")
        return "\n".join(lines)

    def __len__(self) -> int:
        with self._state.lock:
            return len(self._visible_entries_unlocked())

    def __bool__(self) -> bool:
        with self._state.lock:
            return bool(self._visible_entries_unlocked())
