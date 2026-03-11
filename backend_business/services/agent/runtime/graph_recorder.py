"""Generic runtime execution graph recorder."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend_business.services.agent.execution_graph_service import ExecutionGraphService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _safe_json(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    if isinstance(value, set):
        return sorted(value)
    return str(value)


@dataclass(frozen=True)
class ContainerConfig:
    container_key: str
    label: str
    role_type: str
    config_json: dict[str, Any] | None = None


@dataclass(frozen=True)
class StageNode:
    node_id: str
    node_key: str
    label: str
    node_type: str
    role_type: str
    container_id: str


class RuntimeGraphRecorder:
    """Records stage execution and tool call traces into execution graph tables."""

    def __init__(
        self,
        *,
        execution_graph_service: ExecutionGraphService,
        container_configs: list[ContainerConfig],
        project_id: str,
        user_id: str,
        session_id: str,
        user_message: str,
        graph_id: str | None = None,
        graph_name: str | None = None,
        graph_description: str = "Agent 运行轨迹",
        initial_graph_meta: dict[str, Any] | None = None,
        task_context: dict[str, Any] | None = None,
    ) -> None:
        if not container_configs:
            raise ValueError("container_configs 不能为空")

        self._service = execution_graph_service
        self._container_configs = list(container_configs)
        self._container_config_map = {cfg.container_key: cfg for cfg in container_configs}
        self._containers: dict[str, str] = {}
        self._nodes: dict[str, StageNode] = {}
        self._seed_context_entries: list[dict[str, Any]] = []
        self._historical_node_context: list[dict[str, Any]] = []
        self._last_node_id: str | None = None
        self._last_node_key: str | None = None
        self._node_order = 0
        self._edge_order = 0
        self._graph = self._load_or_create_graph(
            graph_id=graph_id,
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            graph_name=graph_name,
            graph_description=graph_description,
            initial_graph_meta=initial_graph_meta,
        )
        self.graph_id = self._graph["graph_id"]
        self.turn_index = self._resolve_turn_index()
        self._task_context = {
            "session_id": session_id,
            "project_id": project_id,
            "user_id": user_id,
            "user_message": user_message,
            "turn_index": self.turn_index,
            "historical_node_count": len(self._historical_node_context),
            **(task_context or {}),
        }
        self._context_entries: list[dict[str, Any]] = list(self._seed_context_entries)
        self._ensure_containers(user_id)

    def _load_or_create_graph(
        self,
        *,
        graph_id: str | None,
        project_id: str,
        user_id: str,
        session_id: str,
        user_message: str,
        graph_name: str | None,
        graph_description: str,
        initial_graph_meta: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if graph_id:
            detail = self._service.get_graph_detail(graph_id)
            graph = detail.get("graph")
            if not graph:
                raise ValueError("会话绑定的执行图不存在或已删除")
            self._hydrate_existing_graph(detail)
            return graph

        normalized_meta = {
            "session_id": session_id,
            "user_id": user_id,
            "project_id": project_id,
            "current_node_key": None,
            "final_reply": None,
            "user_message": user_message,
            "created_at": _utc_now_iso(),
            "turn_count": 0,
        }
        normalized_meta.update(initial_graph_meta or {})
        normalized_name = graph_name or f"Agent Run {datetime.now(timezone.utc).strftime('%H:%M:%S')}"

        return self._service.create_runtime_graph(
            project_id=project_id,
            name=normalized_name,
            description=graph_description,
            created_by=user_id,
            meta_json=normalized_meta,
            status="running",
        )

    def _hydrate_existing_graph(self, detail: dict[str, Any]) -> None:
        containers = sorted(
            detail.get("containers") or [],
            key=lambda item: (item.get("order_index") or 0, item.get("created_at") or ""),
        )
        for container in containers:
            container_key = container.get("container_key")
            container_id = container.get("container_id")
            if container_key and container_id:
                self._containers[container_key] = container_id

        nodes = sorted(
            detail.get("nodes") or [],
            key=lambda item: (item.get("order_index") or 0, item.get("created_at") or ""),
        )
        self._historical_node_context = self._summarize_existing_nodes(nodes)
        self._seed_context_entries = self._build_existing_context_entries(nodes)
        if nodes:
            last_node = nodes[-1]
            self._last_node_id = last_node.get("node_id")
            self._last_node_key = last_node.get("node_key")
            self._node_order = max((item.get("order_index") or 0) for item in nodes) + 1

        edges = detail.get("edges") or []
        if edges:
            self._edge_order = max((item.get("order_index") or 0) for item in edges) + 1

    def _resolve_turn_index(self) -> int:
        meta = self._graph.get("meta_json") or {}
        raw_turn_count = meta.get("turn_count")
        try:
            normalized_turn_count = int(raw_turn_count)
        except (TypeError, ValueError):
            normalized_turn_count = 0
        if normalized_turn_count > 0:
            return normalized_turn_count + 1
        return self._infer_turn_index_from_node_order()

    def _infer_turn_index_from_node_order(self) -> int:
        highest_turn = 0
        pattern = re.compile(r"^turn_(\d+)__")
        detail = self._service.get_graph_detail(self.graph_id)
        for node in detail.get("nodes") or []:
            node_key = str(node.get("node_key") or "")
            match = pattern.match(node_key)
            if not match:
                continue
            highest_turn = max(highest_turn, int(match.group(1)))
        return highest_turn + 1 if highest_turn else 1

    def stage_node_key(self, base_key: str) -> str:
        return f"turn_{self.turn_index}__{base_key}"

    def stage_label(self, base_label: str) -> str:
        return f"{base_label} (Turn {self.turn_index})"

    @property
    def historical_node_context(self) -> list[dict[str, Any]]:
        return list(self._historical_node_context)

    @property
    def last_node_key(self) -> str | None:
        return self._last_node_key

    def _ensure_containers(self, user_id: str) -> None:
        for order_index, container_config in enumerate(self._container_configs):
            container_key = container_config.container_key
            if container_key in self._containers:
                continue
            container = self._service.create_container(
                graph_id=self.graph_id,
                container_key=container_key,
                label=container_config.label,
                role_type=container_config.role_type,
                config_json=container_config.config_json or {"runtime": True},
                order_index=order_index,
                created_by=user_id,
            )
            self._containers[container_key] = container["container_id"]

    @staticmethod
    def _summarize_existing_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for node in nodes:
            config = node.get("config_json") or {}
            tool_results = config.get("tool_call_results") or []
            summaries.append(
                {
                    "node_key": node.get("node_key"),
                    "label": node.get("label"),
                    "node_type": node.get("node_type"),
                    "role_type": node.get("role_type"),
                    "run_status": config.get("run_status"),
                    "output_summary": config.get("output_summary"),
                    "tool_call_results": [
                        {
                            "tool_name": entry.get("tool_name"),
                            "request": entry.get("request"),
                            "result": entry.get("result"),
                        }
                        for entry in tool_results
                    ],
                }
            )
        return summaries

    @staticmethod
    def _build_existing_context_entries(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for node in nodes:
            config = node.get("config_json") or {}
            node_key = str(node.get("node_key") or "")
            if "output_summary" in config:
                entries.append(
                    {
                        "kind": "historical_stage_output",
                        "node_key": node_key,
                        "value": _safe_json(config.get("output_summary")),
                        "recorded_at": _utc_now_iso(),
                    }
                )
            for tool_result in config.get("tool_call_results") or []:
                entries.append(
                    {
                        "kind": "historical_tool_call_result",
                        "node_key": node_key,
                        "value": _safe_json(tool_result),
                        "recorded_at": _utc_now_iso(),
                    }
                )
        return entries

    def _build_stage_input(self, *, node_key: str, input_summary: Any) -> list[dict[str, Any]]:
        return [
            {"kind": "task", "value": _safe_json(self._task_context)},
            *self._context_entries,
            {
                "kind": "stage_input",
                "node_key": node_key,
                "value": _safe_json(input_summary),
            },
        ]

    def _append_context_entry(self, *, kind: str, node_key: str, value: Any) -> None:
        self._context_entries.append(
            {
                "kind": kind,
                "node_key": node_key,
                "value": _safe_json(value),
                "recorded_at": _utc_now_iso(),
            }
        )

    def _update_stage_config(
        self,
        *,
        stage_node: StageNode,
        created_by: str,
        mutate: Any,
    ) -> dict[str, Any]:
        node = self._service.get_node(stage_node.node_id)
        config = dict(node.get("config_json") or {})
        mutate(config)
        self._service.update_node(
            node_id=stage_node.node_id,
            config_json=config,
            updated_by=created_by,
        )
        return config

    def start_stage(
        self,
        *,
        node_key: str,
        label: str,
        node_type: str,
        role_type: str,
        container_key: str,
        created_by: str,
        input_summary: Any,
        edge_type_from_previous: str | None = "call",
    ) -> StageNode:
        if container_key not in self._containers:
            raise KeyError(f"container_key 未配置: {container_key}")

        stage_node = self._nodes.get(node_key)
        if stage_node is None:
            node = self._service.create_node(
                graph_id=self.graph_id,
                container_id=self._containers[container_key],
                node_key=node_key,
                label=label,
                node_type=node_type,
                role_type=role_type,
                config_json={
                    "runtime": True,
                    "run_status": "pending",
                    "input": self._build_stage_input(node_key=node_key, input_summary=input_summary),
                    "input_summary": _safe_json(input_summary),
                    "output": None,
                    "output_summary": None,
                    "tool_call_results": [],
                    "started_at": None,
                    "finished_at": None,
                    "error": None,
                },
                order_index=self._node_order,
                created_by=created_by,
            )
            self._node_order += 1
            stage_node = StageNode(
                node_id=node["node_id"],
                node_key=node_key,
                label=label,
                node_type=node_type,
                role_type=role_type,
                container_id=self._containers[container_key],
            )
            self._nodes[node_key] = stage_node

            if self._last_node_id and edge_type_from_previous:
                self._service.create_edge(
                    graph_id=self.graph_id,
                    source_node_id=self._last_node_id,
                    target_node_id=stage_node.node_id,
                    edge_type=edge_type_from_previous,
                    label=edge_type_from_previous,
                    config_json={"runtime": True},
                    order_index=self._edge_order,
                    created_by=created_by,
                )
                self._edge_order += 1

        self._update_stage_config(
            stage_node=stage_node,
            created_by=created_by,
            mutate=lambda config: config.update(
                {
                    "run_status": "running",
                    "input": self._build_stage_input(node_key=node_key, input_summary=input_summary),
                    "input_summary": _safe_json(input_summary),
                    "tool_call_results": list(config.get("tool_call_results") or []),
                    "started_at": config.get("started_at") or _utc_now_iso(),
                    "error": None,
                }
            ),
        )
        self._service.patch_graph_meta(
            self.graph_id,
            {"current_node_key": node_key},
            status="running",
            updated_by=created_by,
        )
        self._last_node_id = stage_node.node_id
        self._last_node_key = node_key
        return stage_node

    def record_tool_call_result(
        self,
        node_key: str,
        *,
        created_by: str,
        tool_name: str,
        request_payload: Any,
        result_payload: Any,
    ) -> None:
        stage_node = self._nodes[node_key]
        tool_result_entry = {
            "tool_name": tool_name,
            "request": _safe_json(request_payload),
            "result": _safe_json(result_payload),
            "recorded_at": _utc_now_iso(),
        }
        self._update_stage_config(
            stage_node=stage_node,
            created_by=created_by,
            mutate=lambda config: config.update(
                {
                    "tool_call_results": [
                        *(config.get("tool_call_results") or []),
                        tool_result_entry,
                    ]
                }
            ),
        )
        self._append_context_entry(
            kind="tool_call_result",
            node_key=node_key,
            value=tool_result_entry,
        )

    def complete_stage(
        self,
        node_key: str,
        *,
        created_by: str,
        output_summary: Any,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        stage_node = self._nodes[node_key]
        normalized_output = _safe_json(output_summary)
        self._update_stage_config(
            stage_node=stage_node,
            created_by=created_by,
            mutate=lambda config: config.update(
                {
                    "run_status": "succeeded" if success else "failed",
                    "output": normalized_output,
                    "output_summary": normalized_output,
                    "finished_at": _utc_now_iso(),
                    "error": error,
                }
            ),
        )
        self._append_context_entry(
            kind="stage_output",
            node_key=node_key,
            value={
                "success": success,
                "output": normalized_output,
                "error": error,
            },
        )

    def fail_graph(self, *, created_by: str, error: str, final_reply: str | None = None) -> None:
        self._service.patch_graph_meta(
            self.graph_id,
            {"error": error, "final_reply": final_reply},
            status="failed",
            updated_by=created_by,
        )

    def succeed_graph(self, *, created_by: str, final_reply: str, meta_patch: dict[str, Any] | None = None) -> None:
        patch = {"final_reply": final_reply, "error": None}
        patch.update(meta_patch or {})
        self._service.patch_graph_meta(
            self.graph_id,
            patch,
            status="succeeded",
            updated_by=created_by,
        )

    def suspend_graph(self, *, created_by: str, final_reply: str, meta_patch: dict[str, Any] | None = None) -> None:
        patch = {"final_reply": final_reply}
        patch.update(meta_patch or {})
        self._service.patch_graph_meta(
            self.graph_id,
            patch,
            status="suspended",
            updated_by=created_by,
        )

