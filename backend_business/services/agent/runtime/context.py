"""Execution context primitives for agent runtime workflows."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ContextEntry:
    """A single context entry passed across runtime stages."""

    kind: str
    value: Any
    node_key: str | None = None
    recorded_at: str | None = None


class ExecutionContext:
    """Mutable context store shared by runtime stages."""

    def __init__(self, *, initial_entries: list[ContextEntry] | None = None) -> None:
        self._entries: list[ContextEntry] = list(initial_entries or [])

    def add(self, entry: ContextEntry) -> None:
        self._entries.append(entry)

    def extend(self, entries: list[ContextEntry]) -> None:
        self._entries.extend(entries)

    def snapshot(self) -> list[ContextEntry]:
        return list(self._entries)

