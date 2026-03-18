"""
执行拓扑图服务
提供图、容器、子图、节点、边的 CRUD 操作

该包通过 Mixin 继承模式将各实体的 CRUD 分散到独立模块中，
最终在此组装为单一 ``ExecutionGraphService`` 类。
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from backend_business.services.agent.execution_graph_service._base import _BaseMixin
from backend_business.services.agent.execution_graph_service._graph_repository import _GraphMixin
from backend_business.services.agent.execution_graph_service._container_repository import _ContainerMixin
from backend_business.services.agent.execution_graph_service._subgraph_repository import _SubgraphMixin
from backend_business.services.agent.execution_graph_service._node_repository import _NodeMixin
from backend_business.services.agent.execution_graph_service._edge_repository import _EdgeMixin


class ExecutionGraphService(
    _GraphMixin,
    _ContainerMixin,
    _SubgraphMixin,
    _NodeMixin,
    _EdgeMixin,
    _BaseMixin,
):
    """执行拓扑图服务 — 提供图、容器、子图、节点、边的 CRUD 操作"""

    # =======================
    # Aggregated Methods
    # =======================

    def get_graph_detail(
        self, graph_id: str, include_deleted: bool = False
    ) -> Dict[str, Any]:
        graph = self.get_execution_graph(graph_id, include_deleted)
        if not graph:
            return {"graph": None, "containers": [], "subgraphs": [], "nodes": [], "edges": []}

        containers = self.list_containers(graph_id, include_deleted)
        subgraphs = self.list_subgraphs(graph_id, include_deleted)
        nodes = self.list_nodes(graph_id, include_deleted)
        edges = self.list_edges(graph_id, include_deleted)

        return {
            "graph": graph,
            "containers": containers,
            "subgraphs": subgraphs,
            "nodes": nodes,
            "edges": edges,
        }

    def patch_graph_meta(
        self,
        graph_id: str,
        meta_patch: Dict[str, Any],
        status: str | None = None,
        updated_by: str = "",
    ) -> Dict[str, Any]:
        graph = self.get_execution_graph(graph_id)
        if not graph:
            raise ValueError("图不存在或已删除")

        merged_meta = dict(graph.get("meta_json") or {})
        merged_meta.update(meta_patch or {})
        return self.update_execution_graph(
            graph_id=graph_id,
            status=status,
            meta_json=merged_meta,
            updated_by=updated_by,
        )

    # =======================
    # Compatibility Methods
    # =======================

    def list_execution_containers(
        self, graph_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        return self.list_containers(graph_id=graph_id, include_deleted=include_deleted)

    def list_execution_nodes(
        self, graph_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        return self.list_nodes(graph_id=graph_id, include_deleted=include_deleted)

    def list_execution_edges(
        self, graph_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        return self.list_edges(graph_id=graph_id, include_deleted=include_deleted)


__all__ = ["ExecutionGraphService"]
