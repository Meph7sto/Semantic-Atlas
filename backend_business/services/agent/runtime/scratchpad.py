"""Scratchpad — container-level persistent working memory for cross-subgraph context distillation.

Design reference: docs/Agent方案_updated(1).md §上下文管理 (lines 324-348).

Scratchpad sits at the container level.  All subgraphs within the same
container can read and write to it, but it is invisible across containers.

Three entry types:
  - note          — free-form observations written by the LLM via scratchpad_write tool
  - tool_excerpt  — selective excerpts of tool-call results (marked readonly)
  - stage_output  — structured output auto-appended when a subgraph completes
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass
class ScratchpadEntry:
    """A single Scratchpad entry."""

    entry_type: str  # "note" | "tool_excerpt" | "stage_output"
    content: Any
    source_subgraph: str | None = None
    readonly: bool = False
    created_at: str = field(default_factory=_utc_now_iso)

    def to_dict(self) -> dict[str, Any]:
        return {
            "entry_type": self.entry_type,
            "content": self.content,
            "source_subgraph": self.source_subgraph,
            "readonly": self.readonly,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ScratchpadEntry":
        return cls(
            entry_type=data.get("entry_type", "note"),
            content=data.get("content"),
            source_subgraph=data.get("source_subgraph"),
            readonly=data.get("readonly", False),
            created_at=data.get("created_at") or _utc_now_iso(),
        )


class Scratchpad:
    """Container-level persistent working memory.

    Usage:
        pad = Scratchpad()
        pad.write("note", "user wants to modify login page", source_subgraph="analysis")
        pad.write("tool_excerpt", {"req_id": "R-1", "title": "Login"}, source_subgraph="fetch", readonly=True)
        entries = pad.read()                      # all entries
        entries = pad.read(filter_type="note")     # only notes
    """

    def __init__(self, *, initial_entries: list[ScratchpadEntry] | None = None) -> None:
        self._entries: list[ScratchpadEntry] = list(initial_entries or [])

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
        self._entries.append(
            ScratchpadEntry(
                entry_type=entry_type,
                content=content,
                source_subgraph=source_subgraph,
                readonly=readonly,
            )
        )

    def append_stage_output(self, subgraph_key: str, output: Any) -> None:
        """Auto-append structured output when a subgraph completes (called by runtime)."""
        self._entries.append(
            ScratchpadEntry(
                entry_type="stage_output",
                content=output,
                source_subgraph=subgraph_key,
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
        entries = list(self._entries)

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
        """Serialize all entries for persistence (e.g. into graph meta_json)."""
        return [entry.to_dict() for entry in self._entries]

    @classmethod
    def from_snapshot(cls, data: list[dict[str, Any]]) -> "Scratchpad":
        """Restore from serialized snapshot."""
        entries = [ScratchpadEntry.from_dict(item) for item in (data or [])]
        return cls(initial_entries=entries)

    def format_for_prompt(self) -> str:
        """Format current entries as human-readable text for LLM system prompt injection."""
        if not self._entries:
            return ""
        lines = ["[Scratchpad — 跨阶段工作记忆]"]
        for i, entry in enumerate(self._entries, 1):
            source = f" (from: {entry.source_subgraph})" if entry.source_subgraph else ""
            tag = entry.entry_type.upper()
            content = entry.content
            if isinstance(content, dict):
                import json
                content = json.dumps(content, ensure_ascii=False, indent=None)
            lines.append(f"  [{i}] [{tag}]{source}: {content}")
        return "\n".join(lines)

    def __len__(self) -> int:
        return len(self._entries)

    def __bool__(self) -> bool:
        return bool(self._entries)
