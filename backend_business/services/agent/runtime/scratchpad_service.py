"""Persistence helpers for runtime Scratchpad state."""

from __future__ import annotations

from typing import Any

from .scratchpad import Scratchpad


class ScratchpadService:
    """Loads and saves Scratchpad snapshots from execution-graph metadata."""

    META_KEY = "scratchpad_snapshot"
    ENTRY_COUNT_KEY = "scratchpad_entry_count"

    def __init__(self, *, execution_graph_service: Any) -> None:
        self._service = execution_graph_service

    def load(self, graph_id: str) -> Scratchpad:
        """Load the current Scratchpad for a runtime graph."""
        graph = self._get_graph(graph_id)
        meta = dict((graph or {}).get("meta_json") or {})
        return Scratchpad.from_snapshot(meta.get(self.META_KEY) or [])

    def save(
        self,
        graph_id: str,
        scratchpad: Scratchpad,
        *,
        updated_by: str,
    ) -> dict[str, Any]:
        """Persist the full Scratchpad snapshot into graph metadata."""
        return self.save_snapshot(
            graph_id,
            scratchpad.snapshot(),
            updated_by=updated_by,
        )

    def save_snapshot(
        self,
        graph_id: str,
        snapshot: list[dict[str, Any]] | None,
        *,
        updated_by: str,
    ) -> dict[str, Any]:
        normalized_snapshot = list(snapshot or [])
        return self._service.patch_graph_meta(
            graph_id,
            {
                self.META_KEY: normalized_snapshot,
                self.ENTRY_COUNT_KEY: len(normalized_snapshot),
            },
            updated_by=updated_by,
        )

    def _get_graph(self, graph_id: str) -> dict[str, Any] | None:
        get_execution_graph = getattr(self._service, "get_execution_graph", None)
        if callable(get_execution_graph):
            graph = get_execution_graph(graph_id)
            if graph:
                return graph

        get_graph_detail = getattr(self._service, "get_graph_detail", None)
        if callable(get_graph_detail):
            detail = get_graph_detail(graph_id)
            if isinstance(detail, dict):
                return detail.get("graph")

        return None
