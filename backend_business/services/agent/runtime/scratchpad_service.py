"""Persistence helpers for runtime Scratchpad state."""

from __future__ import annotations

import hashlib
from typing import Any

from .memory_compiler import (
    MemoryCompilation,
    PromptMemoryPolicy,
    ScratchpadMemoryCompiler,
    compact_memory_content,
)
from .scratchpad import Scratchpad, ScratchpadEntry
from .state_contract import with_runtime_state_contract

_DEFAULT_INHERITANCE_POLICY = PromptMemoryPolicy(
    max_tokens=640,
    max_entries=8,
    max_entry_tokens=120,
    summary_tokens=96,
)


class ScratchpadService:
    """Loads and saves Scratchpad snapshots from the container state store.

    The state store is the canonical runtime location. The graph meta snapshot
    is retained as a readable mirror and, for previously stored graphs, as an
    import source during the first load.
    """

    META_KEY = "scratchpad_snapshot"
    ENTRY_COUNT_KEY = "scratchpad_entry_count"
    COMPILATION_METRICS_KEY = "scratchpad_memory_compilation"
    COMPILATION_HISTORY_KEY = "scratchpad_memory_compilation_history"
    LINEAGE_KEY = "scratchpad_memory_lineage"
    STATE_KEY = "scratchpad_snapshot"
    _SHARED_CONTAINER_KEY = "__shared__"
    _MAX_LINEAGE_DEPTH = 16

    def __init__(self, *, execution_graph_service: Any) -> None:
        self._service = execution_graph_service

    def load(self, graph_id: str, container_key: str | None = None) -> Scratchpad:
        """Load the current Scratchpad for a runtime graph."""
        graph = self._get_graph(graph_id)
        supports_state_store = callable(getattr(self._service, "list_container_states", None))
        state_snapshot = self._load_state_snapshot(graph_id) if supports_state_store else []
        if supports_state_store and not state_snapshot:
            migrated_snapshot = self._import_meta_snapshot_to_state_store(
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
        meta = dict((graph or {}).get("meta_json") or {})
        pad.restore_compilation_history(meta.get(self.COMPILATION_HISTORY_KEY) or [])
        return pad.for_container(container_key) if container_key else pad

    def save(
        self,
        graph_id: str,
        scratchpad: Scratchpad,
        *,
        updated_by: str,
    ) -> dict[str, Any]:
        """Persist the full Scratchpad snapshot into runtime state and graph meta."""
        compilation_metrics = scratchpad.latest_compilation_metrics(any_container=True)
        if compilation_metrics:
            compilation_metrics["by_container"] = (
                scratchpad.latest_compilation_metrics_by_container()
            )
        return self.save_snapshot(
            graph_id,
            scratchpad.snapshot_all(),
            updated_by=updated_by,
            compilation_metrics=compilation_metrics,
            compilation_history=scratchpad.compilation_history(),
        )

    def inherit_relevant_snapshot(
        self,
        graph_id: str,
        *,
        previous_graph_id: str,
        task: str,
        updated_by: str,
        policy: PromptMemoryPolicy | None = None,
    ) -> dict[str, Any]:
        """Carry a bounded relevant view forward while retaining raw history by lineage."""

        effective_policy = policy or _DEFAULT_INHERITANCE_POLICY
        (
            lineage_entries,
            lineage_graph_ids,
            scanned_entry_count,
            lineage_truncated,
            lineage_cycle_detected,
            lineage_depth,
        ) = self._collect_lineage_entries(previous_graph_id)
        previous_entries = [entry for _, entry in lineage_entries]
        source_graph_by_entry_id = {
            entry.entry_id: source_graph_id
            for source_graph_id, entry in lineage_entries
        }
        observation_key = f"cross_round_inheritance:{previous_graph_id}"
        compilation = ScratchpadMemoryCompiler(effective_policy).compile(
            previous_entries,
            container_key=None,
            task=task,
            observation_key=observation_key,
            include_flow_context=False,
        )

        entries_by_id: dict[str, ScratchpadEntry] = {}
        for entry in previous_entries:
            entries_by_id.setdefault(entry.entry_id, entry)
        selected_entries = [
            entries_by_id[entry_id]
            for entry_id in compilation.selected_entry_ids
            if entry_id in entries_by_id
        ]
        proposed_inheritance = [
            (
                self._compact_inherited_entry(
                    entry,
                    previous_graph_id=source_graph_by_entry_id.get(
                        entry.entry_id,
                        previous_graph_id,
                    ),
                    max_content_tokens=max(8, effective_policy.max_entry_tokens - 48),
                ),
                entry.entry_id,
                source_graph_by_entry_id.get(entry.entry_id, previous_graph_id),
            )
            for entry in selected_entries
        ]
        inherited_snapshot, inheritance_compilation = self._bound_inherited_snapshot(
            proposed_inheritance,
            task=task,
            policy=effective_policy,
            observation_key=observation_key,
        )
        inherited_entry_ids = {
            str(item.get("entry_id") or "") for item in inherited_snapshot
        }
        actual_selected_entry_ids = [
            original_entry_id
            for inherited_entry, original_entry_id, _ in proposed_inheritance
            if str(inherited_entry.get("entry_id") or "") in inherited_entry_ids
        ]
        selected_entry_origins = [
            {
                "entry_id": original_entry_id,
                "source_graph_id": source_graph_id,
            }
            for inherited_entry, original_entry_id, source_graph_id in proposed_inheritance
            if str(inherited_entry.get("entry_id") or "") in inherited_entry_ids
        ]
        lineage = {
            "previous_graph_id": previous_graph_id,
            "raw_trace_graph_id": previous_graph_id,
            "raw_trace_graph_ids": lineage_graph_ids,
            "lineage_graph_ids": lineage_graph_ids,
            "lineage_depth": lineage_depth,
            "lineage_graph_count": len(lineage_graph_ids),
            "lineage_truncated": lineage_truncated,
            "lineage_cycle_detected": lineage_cycle_detected,
            "scanned_entry_count": scanned_entry_count,
            "deduplicated_entry_count": len(previous_entries),
            "raw_entry_count": len(previous_entries),
            "raw_history_digest": compilation.raw_history_digest,
            "inherited_entry_count": len(inherited_snapshot),
            "selected_entry_ids": actual_selected_entry_ids,
            "selected_entry_origins": selected_entry_origins,
            "inherited_entry_ids": [
                str(item.get("entry_id") or "") for item in inherited_snapshot
            ],
            "inherited_estimated_tokens": inheritance_compilation.estimated_tokens,
            "task_fingerprint": compilation.task_fingerprint,
            "observation_key": observation_key,
            "compiled_at": compilation.compiled_at,
            "selection_policy": {
                "max_tokens": effective_policy.max_tokens,
                "max_entries": effective_policy.max_entries,
                "max_entry_tokens": effective_policy.max_entry_tokens,
            },
        }
        metrics = compilation.to_metrics()
        metrics["cross_round_inheritance"] = True
        metrics["lineage_graph_ids"] = lineage_graph_ids
        metrics["scanned_entry_count"] = scanned_entry_count
        metrics["deduplicated_entry_count"] = len(previous_entries)
        metrics["actual_inherited_entry_count"] = len(inherited_snapshot)
        metrics["inherited_estimated_tokens"] = inheritance_compilation.estimated_tokens
        self.save_snapshot(
            graph_id,
            inherited_snapshot,
            updated_by=updated_by,
            compilation_metrics=metrics,
            compilation_history=[metrics],
            lineage=lineage,
        )
        return lineage

    def _collect_lineage_entries(
        self,
        previous_graph_id: str,
    ) -> tuple[list[tuple[str, ScratchpadEntry]], list[str], int, bool, bool, int]:
        """Read a bounded lineage and collapse inherited copies to raw origins."""

        pending: list[tuple[str, int, frozenset[str]]] = [
            (previous_graph_id, 0, frozenset())
        ]
        visited: set[str] = set()
        graph_snapshots: list[tuple[str, list[dict[str, Any]]]] = []
        lineage_truncated = False
        lineage_cycle_detected = False
        max_scanned_depth = 0

        while pending:
            graph_id, depth, ancestors = pending.pop(0)
            if graph_id in visited:
                continue
            if (
                depth >= self._MAX_LINEAGE_DEPTH
                or len(visited) >= self._MAX_LINEAGE_DEPTH
            ):
                lineage_truncated = True
                continue
            visited.add(graph_id)
            max_scanned_depth = max(max_scanned_depth, depth + 1)

            graph = self._get_graph(graph_id)
            snapshot = self._read_snapshot_without_migration(graph_id, graph=graph)
            graph_snapshots.append((graph_id, snapshot))

            meta = dict((graph or {}).get("meta_json") or {})
            parent_lineage = meta.get(self.LINEAGE_KEY)
            if not isinstance(parent_lineage, dict):
                continue
            parent_graph_ids: list[str] = []
            for key in ("previous_graph_id", "raw_trace_graph_id"):
                parent_graph_id = str(parent_lineage.get(key) or "").strip()
                if parent_graph_id and parent_graph_id not in parent_graph_ids:
                    parent_graph_ids.append(parent_graph_id)
            for parent_graph_id in parent_graph_ids:
                if parent_graph_id == graph_id or parent_graph_id in ancestors:
                    lineage_cycle_detected = True
                elif parent_graph_id in visited:
                    continue
                else:
                    pending.append(
                        (
                            parent_graph_id,
                            depth + 1,
                            ancestors | {graph_id},
                        )
                    )

        scanned_entry_count = sum(len(snapshot) for _, snapshot in graph_snapshots)
        raw_entries: list[tuple[str, ScratchpadEntry]] = []
        for graph_id, snapshot in graph_snapshots:
            raw_entries.extend(
                (graph_id, ScratchpadEntry.from_dict(item))
                for item in snapshot
                if isinstance(item, dict)
            )

        inherited_parent_by_id = {
            entry.entry_id: inherited_parent_id
            for _, entry in raw_entries
            if (inherited_parent_id := self._inherited_parent_entry_id(entry))
        }

        def canonical_entry_id(entry_id: str) -> str:
            current = entry_id
            seen: list[str] = []
            while current in inherited_parent_by_id:
                if current in seen:
                    return min([*seen, current])
                seen.append(current)
                current = inherited_parent_by_id[current]
            return current

        representative_by_origin: dict[str, tuple[str, ScratchpadEntry]] = {}
        # Oldest first ensures raw originals win over their compact inherited copies.
        for graph_id, snapshot in reversed(graph_snapshots):
            for item in snapshot:
                if not isinstance(item, dict):
                    continue
                entry = ScratchpadEntry.from_dict(item)
                origin_id = canonical_entry_id(entry.entry_id)
                existing = representative_by_origin.get(origin_id)
                if existing is None or (
                    self._inherited_parent_entry_id(existing[1]) is not None
                    and self._inherited_parent_entry_id(entry) is None
                ):
                    representative_by_origin[origin_id] = (graph_id, entry)

        return (
            list(representative_by_origin.values()),
            [graph_id for graph_id, _ in graph_snapshots],
            scanned_entry_count,
            lineage_truncated,
            lineage_cycle_detected,
            max_scanned_depth,
        )

    def _read_snapshot_without_migration(
        self,
        graph_id: str,
        *,
        graph: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        """Read lineage history without rewriting an ancestor's audit state."""

        state_snapshot = self._load_state_snapshot(graph_id)
        if state_snapshot:
            snapshot = state_snapshot
        else:
            meta = dict((graph or {}).get("meta_json") or {})
            snapshot = list(meta.get(self.META_KEY) or [])
        return Scratchpad.from_store_snapshot(snapshot).snapshot_all()

    @staticmethod
    def _inherited_parent_entry_id(entry: ScratchpadEntry) -> str | None:
        content = entry.content
        if not isinstance(content, dict):
            return None
        if not content.get("inherited_from_graph_id"):
            return None
        parent_entry_id = str(content.get("inherited_entry_id") or "").strip()
        return parent_entry_id or None

    @staticmethod
    def _bound_inherited_snapshot(
        proposed_inheritance: list[tuple[dict[str, Any], str, str]],
        *,
        task: str,
        policy: PromptMemoryPolicy,
        observation_key: str,
    ) -> tuple[list[dict[str, Any]], MemoryCompilation]:
        """Ensure the persisted inherited view also fits the prompt policy."""

        snapshot = [dict(item) for item, _, _ in proposed_inheritance]
        compiler = ScratchpadMemoryCompiler(policy)
        while True:
            entries = [ScratchpadEntry.from_dict(item) for item in snapshot]
            compilation = compiler.compile(
                entries,
                container_key=None,
                task=task,
                observation_key=observation_key,
                include_flow_context=False,
            )
            selected_ids = set(compilation.selected_entry_ids)
            if len(selected_ids) == len(snapshot):
                return snapshot, compilation
            bounded_snapshot = [
                item
                for item in snapshot
                if str(item.get("entry_id") or "") in selected_ids
            ]
            if len(bounded_snapshot) == len(snapshot):
                return snapshot, compilation
            snapshot = bounded_snapshot

    def save_snapshot(
        self,
        graph_id: str,
        snapshot: list[dict[str, Any]] | None,
        *,
        updated_by: str,
        compilation_metrics: dict[str, Any] | None = None,
        compilation_history: list[dict[str, Any]] | None = None,
        lineage: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_snapshot = list(snapshot or [])
        self._save_container_state_snapshot(
            graph_id=graph_id,
            snapshot=normalized_snapshot,
            updated_by=updated_by,
        )
        meta_patch: dict[str, Any] = {
            self.META_KEY: normalized_snapshot,
            self.ENTRY_COUNT_KEY: len(normalized_snapshot),
        }
        if compilation_metrics:
            meta_patch[self.COMPILATION_METRICS_KEY] = dict(compilation_metrics)
        if compilation_history is not None:
            meta_patch[self.COMPILATION_HISTORY_KEY] = [
                dict(item) for item in compilation_history[-64:]
            ]
        if lineage is not None:
            meta_patch[self.LINEAGE_KEY] = dict(lineage)
        return self._service.patch_graph_meta(
            graph_id,
            with_runtime_state_contract(meta_patch),
            updated_by=updated_by,
        )

    @staticmethod
    def _compact_inherited_entry(
        entry: ScratchpadEntry,
        *,
        previous_graph_id: str,
        max_content_tokens: int,
    ) -> dict[str, Any]:
        inherited_entry_id = "inherited-" + hashlib.sha256(
            f"{previous_graph_id}:{entry.entry_id}".encode()
        ).hexdigest()[:24]
        return ScratchpadEntry(
            entry_type=entry.entry_type,
            content={
                "inherited_from_graph_id": previous_graph_id,
                "inherited_entry_id": entry.entry_id,
                "excerpt": compact_memory_content(
                    entry.content,
                    max_tokens=max_content_tokens,
                ),
            },
            source_subgraph=entry.source_subgraph,
            container_key=entry.container_key,
            readonly=True,
            created_at=entry.created_at,
            entry_id=inherited_entry_id,
            importance=entry.importance,
            task_refs=tuple(
                task_ref
                for task_ref in entry.task_refs
                if task_ref.strip().lower() != "flow-context"
            ),
        ).to_dict()

    def _import_meta_snapshot_to_state_store(
        self,
        graph_id: str,
        *,
        graph: dict[str, Any] | None,
    ) -> list[dict[str, Any]]:
        meta = dict((graph or {}).get("meta_json") or {})
        meta_snapshot = list(meta.get(self.META_KEY) or [])
        if not meta_snapshot:
            self._stamp_runtime_state_contract(graph_id)
            return []

        normalized_snapshot = Scratchpad.from_store_snapshot(meta_snapshot).snapshot_all()
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
