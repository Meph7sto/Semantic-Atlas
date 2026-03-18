"""Template-backed topology runtime execution service."""

from __future__ import annotations

import copy
from typing import Any

from backend_business.services.agent.topology import ConditionEvaluator, GraphStructureBuilder


class TopologyExecutionService:
    """Clone a topology template into a runtime graph and execute a single path."""

    def __init__(self, *, execution_graph_service: Any):
        self._service = execution_graph_service
        self._condition_evaluator = ConditionEvaluator()
        self._structure_builder = GraphStructureBuilder()

    def execute_template(
        self,
        *,
        template_graph_id: str,
        input_payload: dict[str, Any] | None,
        actor: str,
        max_steps: int = 100,
        runtime_graph_name: str | None = None,
        runtime_graph_description: str | None = None,
    ) -> dict[str, Any]:
        template_detail = self._service.get_graph_detail(template_graph_id)
        graph = (template_detail or {}).get("graph")
        if not graph:
            raise ValueError("拓扑模板不存在或已删除")
        if graph.get("graph_type") != "execution_topology_template":
            raise ValueError("仅支持执行拓扑模板图")

        nodes = list(template_detail.get("nodes") or [])
        edges = list(template_detail.get("edges") or [])
        containers = list(template_detail.get("containers") or [])
        subgraphs = list(template_detail.get("subgraphs") or [])
        if not nodes:
            raise ValueError("拓扑模板不包含任何节点")

        structure = self._structure_builder.load_topology(
            template_graph_id,
            graph,
            nodes,
            edges,
            containers,
        )
        structure_errors = self._structure_builder.validate_topology(structure)
        if structure_errors:
            raise ValueError(f"拓扑模板结构无效: {'; '.join(structure_errors)}")

        self._validate_template_for_execution(nodes)

        runtime_graph = self._service.create_runtime_graph(
            project_id=graph["project_id"],
            name=runtime_graph_name or f"{graph.get('name') or 'Topology'} Runtime",
            description=runtime_graph_description or graph.get("description") or "拓扑模板运行时图",
            created_by=actor,
            layout_json=graph.get("layout_json") or {},
            meta_json={
                "template_graph_id": template_graph_id,
                "input_payload": copy.deepcopy(input_payload or {}),
                "execution_mode": "single_path",
                "max_steps": max_steps,
            },
            status="running",
        )

        try:
            runtime_detail = self._clone_template_to_runtime(
                runtime_graph=runtime_graph,
                containers=containers,
                subgraphs=subgraphs,
                nodes=nodes,
                edges=edges,
                actor=actor,
            )
            return self._run_runtime_graph(
                runtime_graph=runtime_graph,
                runtime_detail=runtime_detail,
                input_payload=input_payload or {},
                actor=actor,
                max_steps=max_steps,
            )
        except Exception as exc:
            if runtime_graph.get("status") != "failed":
                self._mark_runtime_graph_failed(
                    runtime_graph=runtime_graph,
                    actor=actor,
                    error=str(exc) or exc.__class__.__name__,
                )
            if isinstance(exc, ValueError):
                raise
            raise ValueError(str(exc) or exc.__class__.__name__) from exc

    def _validate_template_for_execution(self, nodes: list[dict[str, Any]]) -> None:
        start_nodes = [node for node in nodes if node.get("node_type") == "start"]
        if not start_nodes:
            raise ValueError("拓扑模板缺少 start 节点")
        if len(start_nodes) > 1:
            raise ValueError("当前执行器仅支持单一 start 节点")

    def _clone_template_to_runtime(
        self,
        *,
        runtime_graph: dict[str, Any],
        containers: list[dict[str, Any]],
        subgraphs: list[dict[str, Any]] | None = None,
        nodes: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        actor: str,
    ) -> dict[str, Any]:
        runtime_graph_id = runtime_graph["graph_id"]
        container_id_map: dict[str, str] = {}
        runtime_containers: list[dict[str, Any]] = []
        runtime_subgraphs: list[dict[str, Any]] = []
        runtime_nodes: list[dict[str, Any]] = []
        runtime_edges: list[dict[str, Any]] = []

        for container in containers:
            config = copy.deepcopy(container.get("config_json") or {})
            config["template_container_id"] = container.get("container_id")
            config["runtime"] = True
            created = self._service.create_container(
                graph_id=runtime_graph_id,
                container_key=container.get("container_key") or "container",
                label=container.get("label") or container.get("container_key") or "Container",
                role_type=container.get("role_type") or "system",
                config_json=config,
                order_index=container.get("order_index") or 0,
                created_by=actor,
            )
            container_id_map[container["container_id"]] = created["container_id"]
            runtime_containers.append(created)

        subgraph_id_map: dict[str, str] = {}
        for subgraph in sorted(subgraphs or [], key=lambda item: (item.get("order_index") or 0, item.get("subgraph_key") or "")):
            mapped_container_id = container_id_map.get(subgraph.get("container_id"))
            if not mapped_container_id:
                continue
            config = copy.deepcopy(subgraph.get("config_json") or {})
            config["template_subgraph_id"] = subgraph.get("subgraph_id")
            created = self._service.create_subgraph(
                graph_id=runtime_graph_id,
                container_id=mapped_container_id,
                subgraph_key=subgraph.get("subgraph_key") or "subgraph",
                label=subgraph.get("label") or subgraph.get("subgraph_key") or "Subgraph",
                task_description=subgraph.get("task_description") or "",
                order_index=subgraph.get("order_index") or 0,
                config_json=config,
                created_by=actor,
            )
            subgraph_id_map[subgraph["subgraph_id"]] = created["subgraph_id"]
            runtime_subgraphs.append(created)

        node_id_map: dict[str, str] = {}
        for node in sorted(nodes, key=lambda item: (item.get("order_index") or 0, item.get("node_key") or "")):
            config = copy.deepcopy(node.get("config_json") or {})
            config.update(
                {
                    "template_node_id": node.get("node_id"),
                    "runtime": True,
                    "run_status": "pending",
                }
            )
            created = self._service.create_node(
                graph_id=runtime_graph_id,
                container_id=container_id_map.get(node.get("container_id")),
                subgraph_id=subgraph_id_map.get(node.get("subgraph_id")),
                node_key=node.get("node_key") or "node",
                label=node.get("label") or node.get("node_key") or "Node",
                node_type=node.get("node_type") or "node",
                role_type=node.get("role_type") or "system",
                config_json=config,
                input_schema_json=copy.deepcopy(node.get("input_schema_json") or []),
                output_schema_json=copy.deepcopy(node.get("output_schema_json") or []),
                order_index=node.get("order_index") or 0,
                created_by=actor,
            )
            node_id_map[node["node_id"]] = created["node_id"]
            runtime_nodes.append(created)

        for edge in sorted(edges, key=lambda item: (item.get("order_index") or 0, item.get("edge_id") or "")):
            source_node_id = node_id_map.get(edge.get("source_node_id"))
            target_node_id = node_id_map.get(edge.get("target_node_id"))
            if not source_node_id or not target_node_id:
                continue
            config = copy.deepcopy(edge.get("config_json") or {})
            config["template_edge_id"] = edge.get("edge_id")
            created = self._service.create_edge(
                graph_id=runtime_graph_id,
                source_node_id=source_node_id,
                target_node_id=target_node_id,
                edge_type=edge.get("edge_type") or "call",
                label=edge.get("label"),
                condition_expr=edge.get("condition_expr"),
                config_json=config,
                order_index=edge.get("order_index") or 0,
                created_by=actor,
            )
            runtime_edges.append(created)

        return {
            "graph": runtime_graph,
            "containers": runtime_containers,
            "subgraphs": runtime_subgraphs,
            "nodes": runtime_nodes,
            "edges": runtime_edges,
        }

    def _run_runtime_graph(
        self,
        *,
        runtime_graph: dict[str, Any],
        runtime_detail: dict[str, Any],
        input_payload: dict[str, Any],
        actor: str,
        max_steps: int,
    ) -> dict[str, Any]:
        nodes = list(runtime_detail.get("nodes") or [])
        edges = list(runtime_detail.get("edges") or [])
        node_by_id = {node["node_id"]: node for node in nodes}
        start_nodes = [node for node in nodes if node.get("node_type") == "start"]

        if not start_nodes:
            raise ValueError("拓扑模板缺少 start 节点")
        if len(start_nodes) > 1:
            raise ValueError("当前执行器仅支持单一 start 节点")

        current_node = start_nodes[0]
        merged_context = copy.deepcopy(input_payload or {})
        if not isinstance(merged_context, dict):
            merged_context = {"value": merged_context}
        payload_copy = copy.deepcopy(input_payload or {})
        trace: list[dict[str, Any]] = []
        node_outputs: dict[str, Any] = {}
        final_output: dict[str, Any] | None = None
        suspended_node: dict[str, Any] | None = None
        visited_node_ids: list[str] = []

        try:
            for step_index in range(1, max_steps + 1):
                node_input = {
                    "payload": copy.deepcopy(payload_copy),
                    "context": copy.deepcopy(merged_context),
                    "last_output": copy.deepcopy(final_output if final_output is not None else merged_context),
                    "node_outputs": copy.deepcopy(node_outputs),
                    **copy.deepcopy(merged_context),
                }
                node_output = self._execute_node(current_node, node_input)
                if not isinstance(node_output, dict):
                    node_output = {"value": node_output}

                merged_context.update(copy.deepcopy(node_output))
                node_outputs[current_node.get("node_key") or current_node["node_id"]] = copy.deepcopy(node_output)
                visited_node_ids.append(current_node["node_id"])
                trace_entry = {
                    "step": step_index,
                    "node_id": current_node["node_id"],
                    "node_key": current_node.get("node_key"),
                    "node_type": current_node.get("node_type"),
                    "input": node_input,
                    "output": copy.deepcopy(node_output),
                }
                trace.append(trace_entry)

                terminal_state = self._mark_runtime_node(
                    node=current_node,
                    node_input=node_input,
                    node_output=node_output,
                    step_index=step_index,
                    actor=actor,
                )
                node_by_id[current_node["node_id"]] = terminal_state
                final_output = copy.deepcopy(node_output)

                if current_node.get("node_type") == "handoff":
                    suspended_node = current_node
                    runtime_graph = self._service.patch_graph_meta(
                        runtime_graph["graph_id"],
                        {
                            "current_node_id": current_node["node_id"],
                            "current_node_key": current_node.get("node_key"),
                            "trace": trace,
                            "final_output": final_output,
                            "visited_node_ids": visited_node_ids,
                        },
                        status="suspended",
                        updated_by=actor,
                    )
                    return {
                        "status": "suspended",
                        "runtime_graph": runtime_graph,
                        "final_output": final_output,
                        "trace": trace,
                        "suspended_node": current_node,
                    }

                if current_node.get("node_type") == "end":
                    runtime_graph = self._service.patch_graph_meta(
                        runtime_graph["graph_id"],
                        {
                            "current_node_id": current_node["node_id"],
                            "current_node_key": current_node.get("node_key"),
                            "trace": trace,
                            "final_output": final_output,
                            "visited_node_ids": visited_node_ids,
                        },
                        status="succeeded",
                        updated_by=actor,
                    )
                    return {
                        "status": "succeeded",
                        "runtime_graph": runtime_graph,
                        "final_output": final_output,
                        "trace": trace,
                        "suspended_node": None,
                    }

                next_edge = self._select_next_edge(
                    current_node=current_node,
                    edges=edges,
                    state={
                        **copy.deepcopy(merged_context),
                        **copy.deepcopy(node_output),
                        "payload": copy.deepcopy(payload_copy),
                        "last_output": copy.deepcopy(node_output),
                        "node_outputs": copy.deepcopy(node_outputs),
                    },
                )
                if not next_edge:
                    runtime_graph = self._service.patch_graph_meta(
                        runtime_graph["graph_id"],
                        {
                            "current_node_id": current_node["node_id"],
                            "current_node_key": current_node.get("node_key"),
                            "trace": trace,
                            "final_output": final_output,
                            "visited_node_ids": visited_node_ids,
                            "error": "未找到满足条件的后继边",
                        },
                        status="failed",
                        updated_by=actor,
                    )
                    return {
                        "status": "failed",
                        "runtime_graph": runtime_graph,
                        "final_output": final_output,
                        "trace": trace,
                        "suspended_node": None,
                        "error": "未找到满足条件的后继边",
                    }

                current_node = node_by_id[next_edge["target_node_id"]]
        except Exception as exc:
            self._mark_runtime_graph_failed(
                runtime_graph=runtime_graph,
                actor=actor,
                error=str(exc) or exc.__class__.__name__,
                trace=trace,
                final_output=final_output,
                current_node=current_node,
                visited_node_ids=visited_node_ids,
            )
            if isinstance(exc, ValueError):
                raise
            raise ValueError(str(exc) or exc.__class__.__name__) from exc

        runtime_graph = self._service.patch_graph_meta(
            runtime_graph["graph_id"],
            {
                "current_node_id": current_node["node_id"],
                "current_node_key": current_node.get("node_key"),
                "trace": trace,
                "final_output": final_output,
                "visited_node_ids": visited_node_ids,
                "error": f"执行步数超过上限 {max_steps}",
            },
            status="failed",
            updated_by=actor,
        )
        return {
            "status": "failed",
            "runtime_graph": runtime_graph,
            "final_output": final_output,
            "trace": trace,
            "suspended_node": suspended_node,
            "error": f"执行步数超过上限 {max_steps}",
        }

    def _mark_runtime_graph_failed(
        self,
        *,
        runtime_graph: dict[str, Any],
        actor: str,
        error: str,
        trace: list[dict[str, Any]] | None = None,
        final_output: dict[str, Any] | None = None,
        current_node: dict[str, Any] | None = None,
        visited_node_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        meta_patch: dict[str, Any] = {"error": error}
        if trace is not None:
            meta_patch["trace"] = trace
        if final_output is not None:
            meta_patch["final_output"] = final_output
        if current_node is not None:
            meta_patch["current_node_id"] = current_node.get("node_id")
            meta_patch["current_node_key"] = current_node.get("node_key")
        if visited_node_ids is not None:
            meta_patch["visited_node_ids"] = visited_node_ids
        return self._service.patch_graph_meta(
            runtime_graph["graph_id"],
            meta_patch,
            status="failed",
            updated_by=actor,
        )

    def _mark_runtime_node(
        self,
        *,
        node: dict[str, Any],
        node_input: dict[str, Any],
        node_output: dict[str, Any],
        step_index: int,
        actor: str,
    ) -> dict[str, Any]:
        config = copy.deepcopy(node.get("config_json") or {})
        config.update(
            {
                "run_status": "suspended" if node.get("node_type") == "handoff" else "succeeded",
                "run_order": step_index,
                "last_input": node_input,
                "last_output": node_output,
            }
        )
        return self._service.update_node(
            node_id=node["node_id"],
            config_json=config,
            updated_by=actor,
        )

    def _select_next_edge(
        self,
        *,
        current_node: dict[str, Any],
        edges: list[dict[str, Any]],
        state: dict[str, Any],
    ) -> dict[str, Any] | None:
        outgoing_edges = [
            edge
            for edge in edges
            if edge.get("source_node_id") == current_node.get("node_id")
        ]
        outgoing_edges.sort(key=lambda item: (item.get("order_index") or 0, item.get("edge_id") or ""))

        fallback_edge: dict[str, Any] | None = None
        for edge in outgoing_edges:
            condition_expr = edge.get("condition_expr")
            if not condition_expr:
                if fallback_edge is None:
                    fallback_edge = edge
                continue
            if self._condition_evaluator.evaluate(condition_expr, state):
                return edge
        return fallback_edge

    def _execute_node(self, node: dict[str, Any], node_input: dict[str, Any]) -> dict[str, Any]:
        node_type = node.get("node_type") or "node"
        config = copy.deepcopy(node.get("config_json") or {})
        static_output = config.get("output", config.get("static_output"))
        stage_prompt = config.get("stage_prompt")
        if isinstance(stage_prompt, str):
            stage_prompt = stage_prompt.strip()
        else:
            stage_prompt = ""

        if node_type == "start":
            base_payload = copy.deepcopy(node_input.get("payload") or {})
            if not isinstance(base_payload, dict):
                base_payload = {"value": base_payload}
            if stage_prompt and "task" not in base_payload:
                base_payload["task"] = stage_prompt
            else:
                # Backward compatibility: use subgraph task description if available.
                subgraph_id = config.get("subgraph_id") or node.get("subgraph_id")
                if subgraph_id:
                    try:
                        subgraph = self._service.get_subgraph(subgraph_id)
                        if subgraph and subgraph.get("task_description"):
                            if "task" not in base_payload:
                                base_payload["task"] = subgraph["task_description"]
                    except Exception:
                        pass
            if isinstance(static_output, dict):
                base_payload.update(copy.deepcopy(static_output))
            return base_payload

        if node_type == "handoff":
            if isinstance(static_output, dict):
                return copy.deepcopy(static_output)
            return {
                "message": config.get("message") or "需要人工介入",
                "context": copy.deepcopy(node_input.get("context") or {}),
            }

        if isinstance(static_output, dict):
            return copy.deepcopy(static_output)
        if static_output is not None:
            return {"value": copy.deepcopy(static_output)}

        if node_type == "end":
            return copy.deepcopy(node_input.get("last_output") or node_input.get("context") or {})

        return copy.deepcopy(node_input.get("context") or {})
