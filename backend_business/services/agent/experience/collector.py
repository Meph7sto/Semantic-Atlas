"""Runtime material collection for experience skill writeback."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .targets import ExperienceTarget


@dataclass(frozen=True, slots=True)
class ExperienceMaterial:
    """Normalized execution material passed into the compiler pipeline."""

    experience_target: ExperienceTarget
    graph_id: str
    container_key: str
    subgraph_key: str
    user_message: str
    task_description: str
    tool_call_trace: list[dict[str, Any]]
    phase_conclusions: list[str]
    scratchpad_summary: list[str]
    final_conclusion: str
    runtime_status: str
    final_error: str | None
    source_node_keys: tuple[str, ...]


class ExperienceCollector:
    """Collect execution material from graph traces and scratchpad snapshots."""

    def collect(
        self,
        *,
        target: ExperienceTarget,
        graph_id: str,
        graph_service: Any | None,
        recorder: Any | None,
        scratchpad_snapshot: list[dict[str, Any]] | None,
        container_key: str | None = None,
        subgraph_key: str | None = None,
        user_message: str = "",
        task_description: str = "",
        final_conclusion: Any = None,
        runtime_status: str = "succeeded",
        final_error: str | None = None,
        node_key: str | None = None,
    ) -> ExperienceMaterial:
        resolved_user_message = str(user_message or "").strip()
        task_context = getattr(recorder, "_task_context", None)
        if not resolved_user_message and isinstance(task_context, dict):
            resolved_user_message = str(task_context.get("user_message") or "").strip()

        detail = self._load_graph_detail(graph_service=graph_service, graph_id=graph_id)
        nodes = list(detail.get("nodes") or [])
        subgraphs = list(detail.get("subgraphs") or [])
        containers = list(detail.get("containers") or [])

        resolved_task_description = str(task_description or "").strip()
        if not resolved_task_description and subgraph_key:
            for subgraph in subgraphs:
                if str(subgraph.get("subgraph_key") or "").strip() == subgraph_key:
                    resolved_task_description = str(
                        subgraph.get("task_description") or ""
                    ).strip()
                    break

        filtered_nodes = self._filter_nodes(
            nodes=nodes,
            containers=containers,
            target_container_key=container_key or target.container_key,
            target_subgraph_key=subgraph_key,
            target_node_key=node_key,
        )
        tool_call_trace = self._collect_tool_call_trace(filtered_nodes)
        phase_conclusions = self._collect_phase_conclusions(filtered_nodes)
        scratchpad_summary = self._collect_scratchpad_summary(
            snapshot=scratchpad_snapshot or [],
            container_key=container_key or target.container_key,
            subgraph_key=subgraph_key,
        )

        resolved_final_conclusion = str(final_conclusion or "").strip()
        if not resolved_final_conclusion and phase_conclusions:
            resolved_final_conclusion = phase_conclusions[-1]

        return ExperienceMaterial(
            experience_target=target,
            graph_id=str(graph_id or "").strip(),
            container_key=str(container_key or target.container_key or "").strip(),
            subgraph_key=str(subgraph_key or "").strip(),
            user_message=resolved_user_message,
            task_description=resolved_task_description,
            tool_call_trace=tool_call_trace,
            phase_conclusions=phase_conclusions,
            scratchpad_summary=scratchpad_summary,
            final_conclusion=resolved_final_conclusion,
            runtime_status=str(runtime_status or "").strip() or "unknown",
            final_error=str(final_error or "").strip() or None,
            source_node_keys=tuple(
                str(node.get("node_key") or "").strip()
                for node in filtered_nodes
                if str(node.get("node_key") or "").strip()
            ),
        )

    @staticmethod
    def _load_graph_detail(*, graph_service: Any | None, graph_id: str) -> dict[str, Any]:
        if graph_service is None or not graph_id:
            return {}
        get_graph_detail = getattr(graph_service, "get_graph_detail", None)
        if not callable(get_graph_detail):
            return {}
        try:
            detail = get_graph_detail(graph_id)
        except Exception:
            return {}
        return detail if isinstance(detail, dict) else {}

    @staticmethod
    def _filter_nodes(
        *,
        nodes: list[dict[str, Any]],
        containers: list[dict[str, Any]],
        target_container_key: str,
        target_subgraph_key: str | None,
        target_node_key: str | None,
    ) -> list[dict[str, Any]]:
        container_ids = {
            str(container.get("container_id") or "").strip()
            for container in containers
            if str(container.get("container_key") or "").strip() == target_container_key
        }

        if target_node_key:
            filtered = [
                node
                for node in nodes
                if str(node.get("node_key") or "").strip() == target_node_key
            ]
        elif target_subgraph_key:
            filtered = [
                node
                for node in nodes
                if str(node.get("node_key") or "").strip().find(target_subgraph_key) >= 0
                or str((node.get("config_json") or {}).get("subgraph_key") or "").strip()
                == target_subgraph_key
            ]
        elif container_ids:
            filtered = [
                node
                for node in nodes
                if str(node.get("container_id") or "").strip() in container_ids
            ]
        else:
            filtered = list(nodes)

        return sorted(
            filtered,
            key=lambda item: (
                int(item.get("order_index") or 0),
                str(item.get("created_at") or ""),
                str(item.get("node_key") or ""),
            ),
        )

    @staticmethod
    def _collect_tool_call_trace(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        trace: list[dict[str, Any]] = []
        for node in nodes:
            config = node.get("config_json") or {}
            for entry in config.get("tool_call_results") or []:
                if not isinstance(entry, dict):
                    continue
                trace.append(
                    {
                        "node_key": str(node.get("node_key") or "").strip(),
                        "tool_name": str(entry.get("tool_name") or "").strip(),
                        "request": entry.get("request"),
                        "result": entry.get("result"),
                    }
                )
        return trace

    @staticmethod
    def _collect_phase_conclusions(nodes: list[dict[str, Any]]) -> list[str]:
        conclusions: list[str] = []
        for node in nodes:
            config = node.get("config_json") or {}
            output_summary = config.get("output_summary")
            text = ExperienceCollector._summarize_output(output_summary)
            if text:
                conclusions.append(text)
        return conclusions

    @staticmethod
    def _collect_scratchpad_summary(
        *,
        snapshot: list[dict[str, Any]],
        container_key: str,
        subgraph_key: str | None,
    ) -> list[str]:
        summaries: list[str] = []
        for entry in snapshot:
            if not isinstance(entry, dict):
                continue
            entry_container_key = str(entry.get("container_key") or "").strip()
            entry_subgraph_key = str(entry.get("source_subgraph") or "").strip()
            if container_key and entry_container_key and entry_container_key != container_key:
                continue
            if subgraph_key and entry_subgraph_key and entry_subgraph_key != subgraph_key:
                continue
            content = str(entry.get("content") or "").strip()
            if not content:
                continue
            summaries.append(content)
        return summaries[-8:]

    @staticmethod
    def _summarize_output(output_summary: Any) -> str:
        if isinstance(output_summary, str):
            return output_summary.strip()
        if isinstance(output_summary, dict):
            for key in ("conclusion", "content", "tool_loop_reply", "output"):
                value = str(output_summary.get(key) or "").strip()
                if value:
                    return value
            return str(output_summary).strip()
        if output_summary is None:
            return ""
        return str(output_summary).strip()
