"""Persistence helpers for runtime Scratchpad state."""

from __future__ import annotations

from typing import Any

from .scratchpad import Scratchpad
from .state_contract import (
    SCRATCHPAD_STATE_VERSION,
    with_runtime_state_contract,
)


class ScratchpadService:
    """Loads and saves Scratchpad snapshots from container state store."""

    META_KEY = "scratchpad_snapshot"
    ENTRY_COUNT_KEY = "scratchpad_entry_count"
    STATE_KEY = "scratchpad_snapshot"
    _SHARED_CONTAINER_KEY = "__shared__"

    def __init__(self, *, execution_graph_service: Any) -> None:
        self._service = execution_graph_service

    def load(self, graph_id: str, container_key: str | None = None) -> Scratchpad:
        """Load the current Scratchpad for a runtime graph."""
        graph = self._get_graph(graph_id)
        supports_state_store = callable(
            getattr(self._service, "list_container_states", None)
        )
        state_snapshot = self._load_state_snapshot(graph_id) if supports_state_store else []
        if supports_state_store and not state_snapshot:
            migrated_snapshot = self._migrate_legacy_snapshot_to_state_store(
                graph_id,
                graph=graph,
            )
            if migrated_snapshot:
                state_snapshot = self._load_state_snapshot(graph_id)
        if state_snapshot:
            pad = Scratchpad.from_store_snapshot(state_snapshot)
        elif not supports_state_store:
            meta = dict((graph or {}).get("meta_json") or {})
            pad = Scratchpad.from_store_snapshot(meta.get(self.META_KEY) or [])
        else:
            pad = Scratchpad()
        return pad.for_container(container_key) if container_key else pad

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
            scratchpad.snapshot_all(),
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
        self._save_container_state_snapshot(
            graph_id=graph_id,
            snapshot=normalized_snapshot,
            updated_by=updated_by,
        )
        return self._service.patch_graph_meta(
            graph_id,
            with_runtime_state_contract(
                {
                    self.META_KEY: normalized_snapshot,
                    self.ENTRY_COUNT_KEY: len(normalized_snapshot),
                }
            ),
            updated_by=updated_by,
        )

    def _migrate_legacy_snapshot_to_state_store(
        self,
        graph_id: str,
        *,
        graph: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        meta = dict((graph or {}).get("meta_json") or {})
        legacy_snapshot = list(meta.get(self.META_KEY) or [])
        if not legacy_snapshot:
            self._stamp_runtime_state_contract(graph_id)
            return []

        normalized_snapshot = Scratchpad.from_store_snapshot(legacy_snapshot).snapshot_all()
        self._save_container_state_snapshot(
            graph_id=graph_id,
            snapshot=normalized_snapshot,
            updated_by="scratchpad-migration",
        )
        self._stamp_runtime_state_contract(
            graph_id,
            snapshot=normalized_snapshot,
        )
        return normalized_snapshot

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

    def _stamp_runtime_state_contract(
        self,
        graph_id: str,
        *,
        snapshot: list[dict[str, Any]] | None = None,
    ) -> None:
        patch_graph_meta = getattr(self._service, "patch_graph_meta", None)
        if not callable(patch_graph_meta):
            return
        patch_graph_meta(
            graph_id,
            with_runtime_state_contract(
                {
                    self.META_KEY: list(snapshot or []),
                    self.ENTRY_COUNT_KEY: len(snapshot or []),
                }
            ),
            updated_by="scratchpad-migration",
        )

    def _load_state_snapshot(self, graph_id: str) -> list[dict[str, Any]]:
        list_container_states = getattr(self._service, "list_container_states", None)
        if not callable(list_container_states):
            return []

        rows = list_container_states(graph_id)
        snapshots: list[dict[str, Any]] = []
        for row in rows or []:
            state_json = dict(row.get("state_json") or {})
            container_key = row.get("container_key")
            for entry in state_json.get(self.STATE_KEY) or []:
                normalized_entry = dict(entry)
                if container_key == self._SHARED_CONTAINER_KEY:
                    normalized_entry["container_key"] = None
                elif normalized_entry.get("container_key") is None:
                    normalized_entry["container_key"] = container_key
                snapshots.append(normalized_entry)
        return snapshots

    def _save_container_state_snapshot(
        self,
        *,
        graph_id: str,
        snapshot: list[dict[str, Any]],
        updated_by: str,
    ) -> None:
        upsert_container_state = getattr(self._service, "upsert_container_state", None)
        if not callable(upsert_container_state):
            return

        grouped_entries: dict[str, list[dict[str, Any]]] = {}
        for entry in snapshot:
            normalized_entry = dict(entry)
            raw_container_key = normalized_entry.get("container_key")
            if raw_container_key is None:
                container_key = self._SHARED_CONTAINER_KEY
                normalized_entry["container_key"] = None
            else:
                container_key = str(raw_container_key)
            grouped_entries.setdefault(container_key, []).append(normalized_entry)

        existing_container_keys = {
            str(row.get("container_key"))
            for row in (self._load_container_state_rows(graph_id) or [])
            if row.get("container_key") is not None
        }
        for stale_container_key in existing_container_keys - set(grouped_entries):
            grouped_entries[stale_container_key] = []

        for container_key, entries in grouped_entries.items():
            upsert_container_state(
                graph_id=graph_id,
                container_key=container_key,
                state_json={
                    self.STATE_KEY: entries,
                    self.ENTRY_COUNT_KEY: len(entries),
                },
                updated_by=updated_by,
            )

    def _load_container_state_rows(self, graph_id: str) -> list[dict[str, Any]]:
        list_container_states = getattr(self._service, "list_container_states", None)
        if not callable(list_container_states):
            return []
        return list(list_container_states(graph_id) or [])
