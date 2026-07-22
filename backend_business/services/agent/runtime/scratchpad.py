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

import hashlib
import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from .memory_compiler import (
    MemoryCompilation,
    PromptMemoryPolicy,
    ScratchpadMemoryCompiler,
)


def _utc_now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


def _new_entry_id() -> str:
    return uuid.uuid4().hex


def _legacy_entry_id(data: dict[str, Any]) -> str:
    payload = json.dumps(
        data,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return "legacy-" + hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]


def _normalize_importance(value: Any, *, entry_type: str) -> float:
    defaults = {
        "note": 0.65,
        "tool_excerpt": 0.55,
        "stage_output": 0.8,
    }
    try:
        normalized = float(value)
    except (TypeError, ValueError):
        normalized = defaults.get(entry_type, 0.5)
    return min(1.0, max(0.0, normalized))


def _normalize_task_refs(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    raw_items = [value] if isinstance(value, str) else value
    try:
        normalized: list[str] = []
        seen: set[str] = set()
        for item in raw_items:
            task_ref = str(item).strip()[:128]
            if not task_ref or task_ref in seen:
                continue
            normalized.append(task_ref)
            seen.add(task_ref)
            if len(normalized) >= 16:
                break
        return tuple(normalized)
    except TypeError:
        normalized = str(value).strip()[:128]
        return (normalized,) if normalized else ()


@dataclass
class ScratchpadEntry:
    """A single Scratchpad entry."""

    entry_type: str  # "note" | "tool_excerpt" | "stage_output"
    content: Any
    source_subgraph: str | None = None
    container_key: str | None = None
    readonly: bool = False
    created_at: str = field(default_factory=_utc_now_iso)
    entry_id: str = field(default_factory=_new_entry_id)
    importance: float = 0.5
    task_refs: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_type": self.entry_type,
            "content": self.content,
            "source_subgraph": self.source_subgraph,
            "container_key": self.container_key,
            "readonly": self.readonly,
            "created_at": self.created_at,
            "entry_id": self.entry_id,
            "importance": self.importance,
            "task_refs": list(self.task_refs),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ScratchpadEntry:
        entry_type = str(data.get("entry_type") or "note")
        return cls(
            entry_type=entry_type,
            content=data.get("content"),
            source_subgraph=data.get("source_subgraph"),
            container_key=data.get("container_key"),
            readonly=data.get("readonly", False),
            created_at=data.get("created_at") or _utc_now_iso(),
            entry_id=str(data.get("entry_id") or _legacy_entry_id(data)),
            importance=_normalize_importance(
                data.get("importance"),
                entry_type=entry_type,
            ),
            task_refs=_normalize_task_refs(data.get("task_refs")),
        )


@dataclass
class _ScratchpadState:
    entries: list[ScratchpadEntry] = field(default_factory=list)
    lock: threading.RLock = field(default_factory=threading.RLock)
    unscoped_snapshot_visible_to_empty_container: bool = False
    compilation_history: list[dict[str, Any]] = field(default_factory=list)


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

    def for_container(self, container_key: str | None) -> Scratchpad:
        """Return a container-bound view that shares the same underlying storage."""
        return Scratchpad(
            _state=self._state,
            _bound_container_key=container_key,
        )

    def _has_bound_entries(self) -> bool:
        if self._bound_container_key is None:
            return False
        return any(
            entry.container_key == self._bound_container_key for entry in self._state.entries
        )

    def _visible_entries_unlocked(self) -> list[ScratchpadEntry]:
        if self._bound_container_key is None:
            return [entry for entry in self._state.entries if entry.container_key is None]

        scoped_entries = [
            entry
            for entry in self._state.entries
            if entry.container_key == self._bound_container_key
        ]
        if scoped_entries:
            return scoped_entries

        if self._state.unscoped_snapshot_visible_to_empty_container:
            return [entry for entry in self._state.entries if entry.container_key is None]
        return []

    def _materialize_unscoped_snapshot_for_write_unlocked(self) -> None:
        if self._bound_container_key is None:
            return
        if not self._state.unscoped_snapshot_visible_to_empty_container:
            return
        if self._has_bound_entries():
            return

        unscoped_entries = [entry for entry in self._state.entries if entry.container_key is None]
        if not unscoped_entries:
            return

        self._state.entries.extend(
            ScratchpadEntry(
                entry_type=entry.entry_type,
                content=entry.content,
                source_subgraph=entry.source_subgraph,
                container_key=self._bound_container_key,
                readonly=entry.readonly,
                created_at=entry.created_at,
                importance=entry.importance,
                task_refs=entry.task_refs,
            )
            for entry in unscoped_entries
        )

    # ---- write ----

    def write(
        self,
        entry_type: str,
        content: Any,
        *,
        source_subgraph: str | None = None,
        readonly: bool = False,
        importance: float | None = None,
        task_refs: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        """Write a new entry.  tool_excerpt entries are always readonly."""
        if entry_type == "tool_excerpt":
            readonly = True
        with self._state.lock:
            self._materialize_unscoped_snapshot_for_write_unlocked()
            self._state.entries.append(
                ScratchpadEntry(
                    entry_type=entry_type,
                    content=content,
                    source_subgraph=source_subgraph,
                    container_key=self._bound_container_key,
                    readonly=readonly,
                    importance=_normalize_importance(
                        importance,
                        entry_type=entry_type,
                    ),
                    task_refs=_normalize_task_refs(task_refs),
                )
            )

    def append_stage_output(
        self,
        subgraph_key: str,
        output: Any,
        *,
        importance: float | None = None,
        task_refs: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        """Auto-append structured output when a subgraph completes (called by runtime)."""
        with self._state.lock:
            self._materialize_unscoped_snapshot_for_write_unlocked()
            self._state.entries.append(
                ScratchpadEntry(
                    entry_type="stage_output",
                    content=output,
                    source_subgraph=subgraph_key,
                    container_key=self._bound_container_key,
                    readonly=True,
                    importance=_normalize_importance(
                        importance,
                        entry_type="stage_output",
                    ),
                    task_refs=_normalize_task_refs(task_refs),
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
                entries = entries[cutoff_index + 1 :]

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
    def from_snapshot(cls, data: list[dict[str, Any]]) -> Scratchpad:
        """Restore a single scratchpad view from serialized entries."""
        entries = [ScratchpadEntry.from_dict(item) for item in (data or [])]
        return cls(initial_entries=entries)

    @classmethod
    def from_store_snapshot(cls, data: list[dict[str, Any]]) -> Scratchpad:
        """Restore a graph-level scratchpad store from serialized entries.

        Snapshots written before container scoping have no container_key. They
        remain visible to an empty container view until that container writes
        its first scoped entry, at which point the unscoped entries are copied
        into that container scope.
        """
        entries = [ScratchpadEntry.from_dict(item) for item in (data or [])]
        unscoped_snapshot_visible = bool(entries) and not any(
            entry.container_key is not None for entry in entries
        )
        return cls(
            _state=_ScratchpadState(
                entries=entries,
                unscoped_snapshot_visible_to_empty_container=unscoped_snapshot_visible,
            )
        )

    def compile_for_prompt(
        self,
        *,
        task: str | None = None,
        policy: PromptMemoryPolicy | None = None,
        observation_key: str | None = None,
    ) -> MemoryCompilation:
        """Compile a bounded prompt view while retaining the complete raw trace."""

        with self._state.lock:
            entries = list(self._visible_entries_unlocked())
        compilation = ScratchpadMemoryCompiler(policy).compile(
            entries,
            container_key=self._bound_container_key,
            task=task,
            observation_key=observation_key,
        )
        with self._state.lock:
            self._state.compilation_history.append(compilation.to_metrics())
            del self._state.compilation_history[:-64]
        return compilation

    def format_for_prompt(
        self,
        *,
        task: str | None = None,
        policy: PromptMemoryPolicy | None = None,
        observation_key: str | None = None,
    ) -> str:
        """Return the bounded, relevance-ranked Scratchpad prompt view."""

        return self.compile_for_prompt(
            task=task,
            policy=policy,
            observation_key=observation_key,
        ).text

    def restore_compilation_history(
        self,
        history: list[dict[str, Any]] | None,
    ) -> None:
        """Restore bounded compilation telemetry persisted with the graph."""

        with self._state.lock:
            self._state.compilation_history = [
                dict(item) for item in (history or []) if isinstance(item, dict)
            ][-64:]

    def latest_compilation_metrics(
        self,
        *,
        any_container: bool = False,
    ) -> dict[str, Any] | None:
        """Return the latest prompt compilation telemetry for this view."""

        with self._state.lock:
            for metrics in reversed(self._state.compilation_history):
                if any_container or metrics.get("container_key") == self._bound_container_key:
                    return dict(metrics)
        return None

    def compilation_history(self) -> list[dict[str, Any]]:
        """Return bounded compilation telemetry for auditing and diagnostics."""

        with self._state.lock:
            return [dict(item) for item in self._state.compilation_history]

    def latest_compilation_metrics_by_container(self) -> dict[str, dict[str, Any]]:
        """Return the latest compilation telemetry for every observed container."""

        with self._state.lock:
            latest: dict[str, dict[str, Any]] = {}
            for metrics in reversed(self._state.compilation_history):
                container_key = str(metrics.get("container_key") or "__shared__")
                latest.setdefault(container_key, dict(metrics))
            return latest

    def __len__(self) -> int:
        with self._state.lock:
            return len(self._visible_entries_unlocked())

    def __bool__(self) -> bool:
        with self._state.lock:
            return bool(self._visible_entries_unlocked())
