"""Topology-to-execution skeleton instantiator.

Pure data transformation: reads a topology template graph and creates a
runtime execution graph skeleton where every subgraph starts as ``pending``.

This module defines:
- Immutable runtime data classes (RuntimeContainer, RuntimeSubgraph, etc.)
- RuntimeGraphSkeleton with convenience query methods
- TopologyInstantiator.instantiate()
- InstantiationError
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence


# ---------------------------------------------------------------------------
# Business node types eligible for subgraph mapping
# ---------------------------------------------------------------------------

_BUSINESS_NODE_TYPES = frozenset({"llm", "invoke", "handoff"})


# ---------------------------------------------------------------------------
# Immutable runtime data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuntimeContainer:
    """A runtime container cloned from a topology template container."""

    container_id: str
    container_key: str
    label: str
    role_type: str
    order_index: int
    source_container_id: str  # original template container ID


@dataclass(frozen=True)
class RuntimeSubgraph:
    """A runtime subgraph mapped from a topology business node."""

    subgraph_id: str
    container_id: str
    subgraph_key: str
    label: str
    task_description: str
    status: str  # always 'pending' after instantiation
    order_index: int
    node_type: str  # original topology node_type (llm / invoke / handoff)
    config_json: Dict[str, Any] | None
    source_node_id: str  # original template node ID


@dataclass(frozen=True)
class RuntimeNode:
    """A runtime node (start / end) auto-injected into a subgraph."""

    node_id: str
    graph_id: str
    container_id: str
    subgraph_id: str
    node_key: str
    label: str
    node_type: str  # 'start' or 'end'
    role_type: str
    order_index: int


@dataclass(frozen=True)
class RuntimeEdge:
    """A runtime edge cloned from a topology template edge."""

    edge_id: str
    source_node_id: str
    target_node_id: str
    edge_type: str
    label: str | None
    condition_expr: str | None
    config_json: Dict[str, Any] | None
    order_index: int


@dataclass(frozen=True)
class RuntimeGraphSkeleton:
    """Complete runtime execution graph skeleton — all subgraphs pending."""

    graph_id: str
    containers: tuple[RuntimeContainer, ...] = field(default_factory=tuple)
    subgraphs: tuple[RuntimeSubgraph, ...] = field(default_factory=tuple)
    nodes: tuple[RuntimeNode, ...] = field(default_factory=tuple)
    edges: tuple[RuntimeEdge, ...] = field(default_factory=tuple)

    # -- convenience queries --------------------------------------------------

    def get_entry_container(self) -> RuntimeContainer:
        """Return the container with the smallest ``order_index``."""
        if not self.containers:
            raise ValueError("Skeleton has no containers")
        return min(self.containers, key=lambda c: c.order_index)

    def get_subgraphs_for_container(
        self, container_id: str
    ) -> list[RuntimeSubgraph]:
        """Return subgraphs belonging to *container_id*, sorted by order."""
        return sorted(
            (sg for sg in self.subgraphs if sg.container_id == container_id),
            key=lambda sg: sg.order_index,
        )

    def get_outgoing_edges(self, subgraph_id: str) -> list[RuntimeEdge]:
        """Return edges whose source node belongs to *subgraph_id*."""
        subgraph_node_ids = frozenset(
            n.node_id for n in self.nodes if n.subgraph_id == subgraph_id
        )
        return [e for e in self.edges if e.source_node_id in subgraph_node_ids]


# ---------------------------------------------------------------------------
# Instantiation error
# ---------------------------------------------------------------------------


class InstantiationError(Exception):
    """Raised when topology template validation or instantiation fails."""

    def __init__(self, template_graph_id: str, message: str) -> None:
        self.template_graph_id = template_graph_id
        super().__init__(f"Instantiation failed for template {template_graph_id}: {message}")


# ---------------------------------------------------------------------------
# TopologyInstantiator
# ---------------------------------------------------------------------------


class TopologyInstantiator:
    """Creates a runtime execution graph skeleton from a topology template.

    The instantiator is a pure-logic service — it does **not** hold any DB
    connection.  The caller injects an ``ExecutionGraphService`` instance for
    all persistence operations.
    """

    def instantiate(
        self,
        *,
        template_graph_id: str,
        project_id: str,
        graph_service: Any,
        created_by: str = "",
        runtime_graph_id: str | None = None,
    ) -> RuntimeGraphSkeleton:
        """Instantiate a runtime execution graph from *template_graph_id*.

        Parameters
        ----------
        template_graph_id:
            ID of the topology template graph to instantiate.
        project_id:
            Project the new runtime graph belongs to.
        graph_service:
            An ``ExecutionGraphService`` instance (or compatible duck-type).
        created_by:
            Actor identifier for audit fields.
        runtime_graph_id:
            Optional existing runtime graph ID. When provided, the
            skeleton is instantiated into that graph instead of creating
            a new runtime graph record.

        Returns
        -------
        RuntimeGraphSkeleton
            A fully-persisted, immutable skeleton with all subgraphs in
            ``pending`` status.

        Raises
        ------
        InstantiationError
            If the template does not exist, has no containers, or is not a
            valid topology template.
        """
        # 1. Load template detail ------------------------------------------------
        template_detail = graph_service.get_graph_detail(template_graph_id)
        template_graph = template_detail.get("graph")

        if not template_graph:
            raise InstantiationError(template_graph_id, "模板不存在或已删除")

        if template_graph.get("graph_type") != "execution_topology_template":
            raise InstantiationError(
                template_graph_id,
                f"graph_type 必须是 'execution_topology_template'，实际为 '{template_graph.get('graph_type')}'",
            )

        tpl_containers: list[dict] = template_detail.get("containers") or []
        tpl_nodes: list[dict] = template_detail.get("nodes") or []
        tpl_edges: list[dict] = template_detail.get("edges") or []

        if not tpl_containers:
            raise InstantiationError(template_graph_id, "模板不包含任何 container")

        # Filter to business nodes only
        business_nodes = [n for n in tpl_nodes if n.get("node_type") in _BUSINESS_NODE_TYPES]
        if not business_nodes:
            raise InstantiationError(template_graph_id, "模板不包含任何业务节点（llm / invoke / handoff）")

        # 2. Create or load runtime graph -----------------------------------------
        reuse_existing_graph = runtime_graph_id is not None
        runtime_graph = self._load_or_create_runtime_graph(
            graph_service=graph_service,
            runtime_graph_id=runtime_graph_id,
            project_id=project_id,
            template_graph_id=template_graph_id,
            template_graph=template_graph,
            created_by=created_by,
        )
        runtime_graph_id = runtime_graph["graph_id"]

        # 3. Clone containers (or reuse existing) ---------------------------------
        existing_containers = _load_existing_containers(
            graph_service, runtime_graph_id, reuse_existing_graph,
        )
        container_id_map: dict[str, str] = {}  # template container_id → runtime container_id
        rt_containers: list[RuntimeContainer] = []

        for tpl_c in tpl_containers:
            matched = _match_existing_container(
                tpl_c, existing_containers, tpl_containers,
            )
            if matched is not None:
                # Reuse the pre-existing container
                container_id_map[tpl_c["container_id"]] = matched["container_id"]
                rt_containers.append(
                    RuntimeContainer(
                        container_id=matched["container_id"],
                        container_key=matched["container_key"],
                        label=matched.get("label", matched["container_key"]),
                        role_type=matched.get("role_type", tpl_c["role_type"]),
                        order_index=matched.get("order_index", 0),
                        source_container_id=tpl_c["container_id"],
                    )
                )
            else:
                # No match — create a new container
                rt_c = graph_service.create_container(
                    graph_id=runtime_graph_id,
                    container_key=tpl_c["container_key"],
                    label=tpl_c.get("label", tpl_c["container_key"]),
                    role_type=tpl_c["role_type"],
                    config_json=tpl_c.get("config_json"),
                    order_index=tpl_c.get("order_index", 0),
                    created_by=created_by,
                )
                container_id_map[tpl_c["container_id"]] = rt_c["container_id"]
                rt_containers.append(
                    RuntimeContainer(
                        container_id=rt_c["container_id"],
                        container_key=rt_c["container_key"],
                        label=rt_c["label"],
                        role_type=rt_c["role_type"],
                        order_index=rt_c.get("order_index", 0),
                        source_container_id=tpl_c["container_id"],
                    )
                )

        # 4. Map business nodes → subgraphs + inject start/end nodes ---------------
        node_id_to_subgraph_start: dict[str, str] = {}  # template node_id → runtime start node_id
        node_id_to_subgraph_end: dict[str, str] = {}    # template node_id → runtime end node_id
        rt_subgraphs: list[RuntimeSubgraph] = []
        rt_nodes: list[RuntimeNode] = []

        for idx, tpl_node in enumerate(business_nodes):
            tpl_container_id = tpl_node.get("container_id")
            if not tpl_container_id or tpl_container_id not in container_id_map:
                raise InstantiationError(
                    template_graph_id,
                    f"节点 '{tpl_node.get('node_key')}' 的 container_id 无效",
                )

            rt_container_id = container_id_map[tpl_container_id]

            # Build subgraph config from topology node metadata
            sg_config = _build_subgraph_config(tpl_node)

            # Create subgraph
            rt_sg = graph_service.create_subgraph(
                graph_id=runtime_graph_id,
                container_id=rt_container_id,
                subgraph_key=f"sg_{tpl_node['node_key']}",
                label=tpl_node.get("phase_label") or tpl_node.get("label", tpl_node["node_key"]),
                task_description=tpl_node.get("task_prompt") or "",
                order_index=tpl_node.get("order_index", idx),
                config_json=sg_config,
                created_by=created_by,
            )
            subgraph_id = rt_sg["subgraph_id"]

            rt_subgraphs.append(
                RuntimeSubgraph(
                    subgraph_id=subgraph_id,
                    container_id=rt_container_id,
                    subgraph_key=rt_sg["subgraph_key"],
                    label=rt_sg["label"],
                    task_description=rt_sg.get("task_description", ""),
                    status="pending",
                    order_index=rt_sg.get("order_index", idx),
                    node_type=tpl_node["node_type"],
                    config_json=sg_config,
                    source_node_id=tpl_node["node_id"],
                )
            )

            # Inject start node
            start_node = graph_service.create_node(
                graph_id=runtime_graph_id,
                node_key=f"{tpl_node['node_key']}_start",
                label=f"Start – {tpl_node.get('label', tpl_node['node_key'])}",
                node_type="start",
                role_type=tpl_node.get("role_type", "agent"),
                container_id=rt_container_id,
                subgraph_id=subgraph_id,
                order_index=0,
                created_by=created_by,
            )
            node_id_to_subgraph_start[tpl_node["node_id"]] = start_node["node_id"]
            rt_nodes.append(
                RuntimeNode(
                    node_id=start_node["node_id"],
                    graph_id=runtime_graph_id,
                    container_id=rt_container_id,
                    subgraph_id=subgraph_id,
                    node_key=start_node["node_key"],
                    label=start_node["label"],
                    node_type="start",
                    role_type=start_node["role_type"],
                    order_index=0,
                )
            )

            # Inject end node
            end_node = graph_service.create_node(
                graph_id=runtime_graph_id,
                node_key=f"{tpl_node['node_key']}_end",
                label=f"End – {tpl_node.get('label', tpl_node['node_key'])}",
                node_type="end",
                role_type=tpl_node.get("role_type", "agent"),
                container_id=rt_container_id,
                subgraph_id=subgraph_id,
                order_index=1,
                created_by=created_by,
            )
            node_id_to_subgraph_end[tpl_node["node_id"]] = end_node["node_id"]
            rt_nodes.append(
                RuntimeNode(
                    node_id=end_node["node_id"],
                    graph_id=runtime_graph_id,
                    container_id=rt_container_id,
                    subgraph_id=subgraph_id,
                    node_key=end_node["node_key"],
                    label=end_node["label"],
                    node_type="end",
                    role_type=end_node["role_type"],
                    order_index=1,
                )
            )

        # 5. Clone edges (re-map node IDs) -----------------------------------------
        rt_edges: list[RuntimeEdge] = []

        for tpl_edge in tpl_edges:
            src_tpl_id = tpl_edge["source_node_id"]
            tgt_tpl_id = tpl_edge["target_node_id"]

            # Source → use the end node of the source subgraph
            rt_source_id = node_id_to_subgraph_end.get(src_tpl_id)
            # Target → use the start node of the target subgraph
            rt_target_id = node_id_to_subgraph_start.get(tgt_tpl_id)

            if not rt_source_id or not rt_target_id:
                # Skip edges that connect to non-business nodes (e.g. start/end
                # nodes in the template itself, if any).
                continue

            rt_edge = graph_service.create_edge(
                graph_id=runtime_graph_id,
                source_node_id=rt_source_id,
                target_node_id=rt_target_id,
                edge_type=tpl_edge["edge_type"],
                label=tpl_edge.get("label"),
                condition_expr=tpl_edge.get("condition_expr"),
                config_json=tpl_edge.get("config_json"),
                order_index=tpl_edge.get("order_index", 0),
                created_by=created_by,
            )
            rt_edges.append(
                RuntimeEdge(
                    edge_id=rt_edge["edge_id"],
                    source_node_id=rt_edge["source_node_id"],
                    target_node_id=rt_edge["target_node_id"],
                    edge_type=rt_edge["edge_type"],
                    label=rt_edge.get("label"),
                    condition_expr=rt_edge.get("condition_expr"),
                    config_json=rt_edge.get("config_json"),
                    order_index=rt_edge.get("order_index", 0),
                )
            )

        # 6. Assemble skeleton and return ------------------------------------------
        return RuntimeGraphSkeleton(
            graph_id=runtime_graph_id,
            containers=tuple(rt_containers),
            subgraphs=tuple(rt_subgraphs),
            nodes=tuple(rt_nodes),
            edges=tuple(rt_edges),
        )

    def _load_or_create_runtime_graph(
        self,
        *,
        graph_service: Any,
        runtime_graph_id: str | None,
        project_id: str,
        template_graph_id: str,
        template_graph: dict[str, Any],
        created_by: str,
    ) -> dict[str, Any]:
        if runtime_graph_id:
            detail = graph_service.get_graph_detail(runtime_graph_id)
            runtime_graph = detail.get("graph")
            if not runtime_graph:
                raise InstantiationError(runtime_graph_id, "目标运行时图不存在或已删除")
            if runtime_graph.get("project_id") != project_id:
                raise InstantiationError(runtime_graph_id, "目标运行时图不属于当前项目")
            patch_graph_meta = getattr(graph_service, "patch_graph_meta", None)
            if callable(patch_graph_meta):
                try:
                    runtime_graph = patch_graph_meta(
                        runtime_graph_id,
                        {"source_template_id": template_graph_id},
                        status="running",
                        updated_by=created_by,
                    )
                except Exception:
                    pass
            return runtime_graph

        return graph_service.create_runtime_graph(
            project_id=project_id,
            name=f"runtime_{template_graph.get('name', 'unnamed')}",
            description=f"Runtime execution instantiated from template {template_graph_id}",
            created_by=created_by,
            status="running",
            meta_json={"source_template_id": template_graph_id},
        )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_subgraph_config(tpl_node: dict) -> dict[str, Any] | None:
    """Build the ``config_json`` dict for a runtime subgraph.

    Stores the original node_type and conditional_edges so that the
    SubgraphRunner can later use them for routing decisions.
    """
    config: dict[str, Any] = dict(tpl_node.get("config_json") or {})
    config["node_type"] = tpl_node["node_type"]
    config["source_node_id"] = tpl_node["node_id"]

    conditional_edges = tpl_node.get("conditional_edges")
    if conditional_edges:
        config["conditional_edges"] = conditional_edges

    return config


def _load_existing_containers(
    graph_service: Any,
    runtime_graph_id: str,
    reuse_existing_graph: bool,
) -> list[dict[str, Any]]:
    """Load containers already present in the runtime graph.

    Returns an empty list when the graph was freshly created (no
    pre-existing containers to reuse).
    """
    if not reuse_existing_graph:
        return []
    try:
        detail = graph_service.get_graph_detail(runtime_graph_id)
        return list(detail.get("containers") or [])
    except Exception:
        return []


def _match_existing_container(
    tpl_container: dict[str, Any],
    existing_containers: list[dict[str, Any]],
    all_template_containers: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Try to match a template container to a pre-existing runtime container.

    Matching strategy:
    1. Exact ``container_key`` match.
    2. If both sides have exactly one container, map them regardless of key.
    3. Otherwise return ``None`` (no match → caller will create a new one).
    """
    if not existing_containers:
        return None

    tpl_key = tpl_container.get("container_key", "")
    for ec in existing_containers:
        if ec.get("container_key") == tpl_key:
            return ec

    # Single-container fallback
    if len(all_template_containers) == 1 and len(existing_containers) == 1:
        return existing_containers[0]

    return None
