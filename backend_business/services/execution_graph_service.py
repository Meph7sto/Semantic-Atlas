"""
执行拓扑图服务
提供图、容器、节点、边的 CRUD 操作
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


_ALLOWED_NODE_TYPES = {"start", "node", "decision", "handoff", "end"}
_ALLOWED_EDGE_TYPES = {"call", "return", "retry"}
_ALLOWED_ROLE_TYPES = {"human", "agent", "system"}
_ALLOWED_GRAPH_STATUSES = {"draft", "active"}


class ExecutionGraphService:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(self.dsn)

    # =======================
    # Graph Methods
    # =======================

    def create_execution_graph(
        self, project_id: str, name: str, description: str = "", created_by: str = ""
    ) -> Dict[str, Any]:
        graph_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO execution_graphs(
                            graph_id, project_id, name, description,
                            graph_type, version, status, created_by, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, 'execution_topology_template', 1, 'draft', %s, NOW(), NOW())
                        RETURNING graph_id, project_id, name, description, graph_type, version, status,
                                  layout_json, meta_json, created_by, updated_by,
                                  created_at::text AS created_at
                        """,
                        (graph_id, project_id, name, description, created_by),
                    )
                    return dict(cur.fetchone())
                except IntegrityError as e:
                    if "manage_projects" in str(e):
                        raise ValueError("项目不存在")
                    raise

    def list_execution_graphs(
        self, project_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if include_deleted:
                    cur.execute(
                        """
                        SELECT graph_id, project_id, name, description, graph_type, version, status,
                               layout_json, meta_json, created_by, updated_by,
                               created_at::text AS created_at
                        FROM execution_graphs
                        WHERE project_id = %s
                        ORDER BY updated_at DESC
                        """,
                        (project_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT graph_id, project_id, name, description, graph_type, version, status,
                               layout_json, meta_json, created_by, updated_by,
                               created_at::text AS created_at
                        FROM execution_graphs
                        WHERE project_id = %s AND is_deleted = FALSE
                        ORDER BY updated_at DESC
                        """,
                        (project_id,),
                    )
                return [dict(row) for row in cur.fetchall()]

    def get_execution_graph(
        self, graph_id: str, include_deleted: bool = False
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if include_deleted:
                    cur.execute(
                        """
                        SELECT graph_id, project_id, name, description, graph_type, version, status,
                               layout_json, meta_json, created_by, updated_by,
                               created_at::text AS created_at
                        FROM execution_graphs
                        WHERE graph_id = %s
                        """,
                        (graph_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT graph_id, project_id, name, description, graph_type, version, status,
                               layout_json, meta_json, created_by, updated_by,
                               created_at::text AS created_at
                        FROM execution_graphs
                        WHERE graph_id = %s AND is_deleted = FALSE
                        """,
                        (graph_id,),
                    )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_execution_graph(
        self,
        graph_id: str,
        name: str = None,
        description: str = None,
        status: str = None,
        layout_json: Dict = None,
        meta_json: Dict = None,
        updated_by: str = "",
    ) -> Dict[str, Any]:
        fields = []
        values = []

        if name is not None:
            fields.append("name = %s")
            values.append(name)
        if description is not None:
            fields.append("description = %s")
            values.append(description)
        if status is not None:
            if status not in _ALLOWED_GRAPH_STATUSES:
                raise ValueError(f"status 必须是: {', '.join(_ALLOWED_GRAPH_STATUSES)}")
            fields.append("status = %s")
            values.append(status)
        if layout_json is not None:
            fields.append("layout_json = %s")
            values.append(json.dumps(layout_json) if layout_json else None)
        if meta_json is not None:
            fields.append("meta_json = %s")
            values.append(json.dumps(meta_json) if meta_json else None)

        if not fields:
            return self.get_execution_graph(graph_id)

        fields.append("updated_at = NOW()")
        if updated_by:
            fields.append("updated_by = %s")
            values.append(updated_by)
        values.append(graph_id)

        sql = (
            f"UPDATE execution_graphs SET {', '.join(fields)} WHERE graph_id = %s AND is_deleted = FALSE"
            " RETURNING graph_id, project_id, name, description, graph_type, version, status,"
            " layout_json, meta_json, created_by, updated_by, created_at::text AS created_at"
        )

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, values)
                row = cur.fetchone()
                if not row:
                    raise ValueError("图不存在或已删除")
                return dict(row)

    def delete_execution_graph(self, graph_id: str, updated_by: str = "") -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE execution_graphs
                    SET is_deleted = TRUE, updated_at = NOW(), updated_by = %s
                    WHERE graph_id = %s AND is_deleted = FALSE
                    RETURNING graph_id
                    """,
                    (updated_by, graph_id),
                )
                return cur.fetchone() is not None

    # =======================
    # Container Methods
    # =======================

    def create_container(
        self,
        graph_id: str,
        container_key: str,
        label: str,
        role_type: str,
        config_json: Dict = None,
        order_index: int = 0,
        created_by: str = "",
    ) -> Dict[str, Any]:
        container_id = str(uuid.uuid4())

        if role_type not in _ALLOWED_ROLE_TYPES:
            raise ValueError(f"role_type 必须是: {', '.join(_ALLOWED_ROLE_TYPES)}")

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO execution_containers(
                            container_id, graph_id, container_key, label, role_type,
                            config_json, order_index, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        RETURNING container_id, graph_id, container_key, label, role_type,
                                  config_json, order_index, created_at::text AS created_at
                        """,
                        (
                            container_id,
                            graph_id,
                            container_key,
                            label,
                            role_type,
                            json.dumps(config_json) if config_json else None,
                            order_index,
                        ),
                    )
                    return dict(cur.fetchone())
                except IntegrityError as e:
                    if "execution_graphs" in str(e):
                        raise ValueError("图不存在或已删除")
                    if "unique" in str(e).lower() and "container_key" in str(e).lower():
                        raise ValueError(f"容器 key '{container_key}' 在图中已存在")
                    raise

    def list_containers(
        self, graph_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if include_deleted:
                    cur.execute(
                        """
                        SELECT container_id, graph_id, container_key, label, role_type, config_json,
                               order_index, created_at::text AS created_at
                        FROM execution_containers
                        WHERE graph_id = %s
                        ORDER BY order_index, created_at
                        """,
                        (graph_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT container_id, graph_id, container_key, label, role_type, config_json,
                               order_index, created_at::text AS created_at
                        FROM execution_containers
                        WHERE graph_id = %s AND is_deleted = FALSE
                        ORDER BY order_index, created_at
                        """,
                        (graph_id,),
                    )
                return [dict(row) for row in cur.fetchall()]

    def get_container(
        self, container_id: str, include_deleted: bool = False
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if include_deleted:
                    cur.execute(
                        """
                        SELECT container_id, graph_id, container_key, label, role_type, config_json,
                               order_index, created_at::text AS created_at
                        FROM execution_containers
                        WHERE container_id = %s
                        """,
                        (container_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT container_id, graph_id, container_key, label, role_type, config_json,
                               order_index, created_at::text AS created_at
                        FROM execution_containers
                        WHERE container_id = %s AND is_deleted = FALSE
                        """,
                        (container_id,),
                    )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_container(
        self,
        container_id: str,
        label: str = None,
        role_type: str = None,
        config_json: Dict = None,
        order_index: int = None,
        updated_by: str = "",
    ) -> Dict[str, Any]:
        fields = []
        values = []

        if label is not None:
            fields.append("label = %s")
            values.append(label)
        if role_type is not None:
            if role_type not in _ALLOWED_ROLE_TYPES:
                raise ValueError(f"role_type 必须是: {', '.join(_ALLOWED_ROLE_TYPES)}")
            fields.append("role_type = %s")
            values.append(role_type)
        if config_json is not None:
            fields.append("config_json = %s")
            values.append(json.dumps(config_json) if config_json else None)
        if order_index is not None:
            fields.append("order_index = %s")
            values.append(order_index)

        if not fields:
            return self.get_container(container_id)

        fields.append("updated_at = NOW()")
        values.append(container_id)

        sql = (
            f"UPDATE execution_containers SET {', '.join(fields)} "
            "WHERE container_id = %s AND is_deleted = FALSE "
            "RETURNING container_id, graph_id, container_key, label, role_type, config_json, "
            "order_index, created_at::text AS created_at"
        )

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, values)
                row = cur.fetchone()
                if not row:
                    raise ValueError("容器不存在或已删除")
                return dict(row)

    def delete_container(self, container_id: str, updated_by: str = "") -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE execution_nodes
                    SET container_id = NULL, updated_at = NOW()
                    WHERE container_id = %s AND is_deleted = FALSE
                    """,
                    (container_id,),
                )
                cur.execute(
                    """
                    UPDATE execution_containers
                    SET is_deleted = TRUE, updated_at = NOW()
                    WHERE container_id = %s AND is_deleted = FALSE
                    RETURNING container_id
                    """,
                    (container_id,),
                )
                return cur.fetchone() is not None

    # =======================
    # Node Methods
    # =======================

    def create_node(
        self,
        graph_id: str,
        node_key: str,
        label: str,
        node_type: str,
        role_type: str,
        container_id: str = None,
        config_json: Dict = None,
        input_schema_json: List = None,
        output_schema_json: List = None,
        order_index: int = 0,
        created_by: str = "",
    ) -> Dict[str, Any]:
        node_id = str(uuid.uuid4())

        # Validate node_type
        if node_type not in _ALLOWED_NODE_TYPES:
            raise ValueError(f"node_type 必须是: {', '.join(_ALLOWED_NODE_TYPES)}")

        # Validate role_type
        if role_type not in _ALLOWED_ROLE_TYPES:
            raise ValueError(f"role_type 必须是: {', '.join(_ALLOWED_ROLE_TYPES)}")

        normalized_container_id = container_id or None

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if normalized_container_id:
                    cur.execute(
                        """
                        SELECT container_id
                        FROM execution_containers
                        WHERE container_id = %s AND graph_id = %s AND is_deleted = FALSE
                        """,
                        (normalized_container_id, graph_id),
                    )
                    if not cur.fetchone():
                        raise ValueError("容器不存在、已删除，或不属于当前图")
                try:
                    cur.execute(
                        """
                        INSERT INTO execution_nodes(
                            node_id, graph_id, container_id, node_key, label, node_type, role_type, config_json,
                            input_schema_json, output_schema_json, order_index,
                            created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        RETURNING node_id, graph_id, container_id, node_key, label, node_type, role_type, config_json,
                                  input_schema_json, output_schema_json, order_index,
                                  created_at::text AS created_at
                        """,
                        (
                            node_id,
                            graph_id,
                            normalized_container_id,
                            node_key,
                            label,
                            node_type,
                            role_type,
                            json.dumps(config_json) if config_json else None,
                            json.dumps(input_schema_json) if input_schema_json else None,
                            json.dumps(output_schema_json) if output_schema_json else None,
                            order_index,
                        ),
                    )
                    return dict(cur.fetchone())
                except IntegrityError as e:
                    if "execution_graphs" in str(e):
                        raise ValueError("图不存在或已删除")
                    if "execution_containers" in str(e):
                        raise ValueError("容器不存在或已删除")
                    if "unique" in str(e).lower() and "node_key" in str(e).lower():
                        raise ValueError(f"节点 key '{node_key}' 在图中已存在")
                    raise

    def list_nodes(
        self, graph_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if include_deleted:
                    cur.execute(
                        """
                        SELECT node_id, graph_id, container_id, node_key, label, node_type, role_type, config_json,
                               input_schema_json, output_schema_json, order_index,
                               created_at::text AS created_at
                        FROM execution_nodes
                        WHERE graph_id = %s
                        ORDER BY order_index, created_at
                        """,
                        (graph_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT node_id, graph_id, container_id, node_key, label, node_type, role_type, config_json,
                               input_schema_json, output_schema_json, order_index,
                               created_at::text AS created_at
                        FROM execution_nodes
                        WHERE graph_id = %s AND is_deleted = FALSE
                        ORDER BY order_index, created_at
                        """,
                        (graph_id,),
                    )
                return [dict(row) for row in cur.fetchall()]

    def get_node(self, node_id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if include_deleted:
                    cur.execute(
                        """
                        SELECT node_id, graph_id, container_id, node_key, label, node_type, role_type, config_json,
                               input_schema_json, output_schema_json, order_index,
                               created_at::text AS created_at
                        FROM execution_nodes
                        WHERE node_id = %s
                        """,
                        (node_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT node_id, graph_id, container_id, node_key, label, node_type, role_type, config_json,
                               input_schema_json, output_schema_json, order_index,
                               created_at::text AS created_at
                        FROM execution_nodes
                        WHERE node_id = %s AND is_deleted = FALSE
                        """,
                        (node_id,),
                    )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_node(
        self,
        node_id: str,
        container_id: str = None,
        label: str = None,
        node_type: str = None,
        role_type: str = None,
        config_json: Dict = None,
        input_schema_json: List = None,
        output_schema_json: List = None,
        order_index: int = None,
        updated_by: str = "",
    ) -> Dict[str, Any]:
        fields = []
        values = []

        if label is not None:
            fields.append("label = %s")
            values.append(label)
        if container_id is not None:
            fields.append("container_id = %s")
            values.append(container_id or None)
        if node_type is not None:
            if node_type not in _ALLOWED_NODE_TYPES:
                raise ValueError(f"node_type 必须是: {', '.join(_ALLOWED_NODE_TYPES)}")
            fields.append("node_type = %s")
            values.append(node_type)
        if role_type is not None:
            if role_type not in _ALLOWED_ROLE_TYPES:
                raise ValueError(f"role_type 必须是: {', '.join(_ALLOWED_ROLE_TYPES)}")
            fields.append("role_type = %s")
            values.append(role_type)
        if config_json is not None:
            fields.append("config_json = %s")
            values.append(json.dumps(config_json) if config_json else None)
        if input_schema_json is not None:
            fields.append("input_schema_json = %s")
            values.append(json.dumps(input_schema_json) if input_schema_json else None)
        if output_schema_json is not None:
            fields.append("output_schema_json = %s")
            values.append(json.dumps(output_schema_json) if output_schema_json else None)
        if order_index is not None:
            fields.append("order_index = %s")
            values.append(order_index)

        if not fields:
            return self.get_node(node_id)

        if container_id:
            current_node = self.get_node(node_id)
            if not current_node:
                raise ValueError("节点不存在或已删除")
            container = self.get_container(container_id)
            if (not container) or container.get("graph_id") != current_node.get("graph_id"):
                raise ValueError("容器不存在、已删除，或不属于当前图")

        fields.append("updated_at = NOW()")
        values.append(node_id)

        sql = (
            f"UPDATE execution_nodes SET {', '.join(fields)} WHERE node_id = %s AND is_deleted = FALSE"
            " RETURNING node_id, graph_id, container_id, node_key, label, node_type, role_type,"
            " config_json, input_schema_json, output_schema_json, order_index,"
            " created_at::text AS created_at"
        )

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, values)
                row = cur.fetchone()
                if not row:
                    raise ValueError("节点不存在或已删除")
                return dict(row)

    def delete_node(self, node_id: str, updated_by: str = "") -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE execution_nodes
                    SET is_deleted = TRUE, updated_at = NOW()
                    WHERE node_id = %s AND is_deleted = FALSE
                    RETURNING node_id
                    """,
                    (node_id,),
                )
                return cur.fetchone() is not None

    # =======================
    # Edge Methods
    # =======================

    def create_edge(
        self,
        graph_id: str,
        source_node_id: str,
        target_node_id: str,
        edge_type: str,
        label: str = None,
        condition_expr: str = None,
        config_json: Dict = None,
        order_index: int = 0,
        created_by: str = "",
    ) -> Dict[str, Any]:
        edge_id = str(uuid.uuid4())

        # Prevent self-loops
        if source_node_id == target_node_id:
            raise ValueError("不允许创建自环边")

        # Validate edge_type
        if edge_type not in _ALLOWED_EDGE_TYPES:
            raise ValueError(f"edge_type 必须是: {', '.join(_ALLOWED_EDGE_TYPES)}")

        # Verify source and target nodes exist
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Check source node
                cur.execute(
                    "SELECT node_id FROM execution_nodes WHERE node_id = %s AND is_deleted = FALSE",
                    (source_node_id,),
                )
                source_node = cur.fetchone()
                if not source_node:
                    raise ValueError("源节点不存在或已删除")

                # Check target node
                cur.execute(
                    "SELECT node_id FROM execution_nodes WHERE node_id = %s AND is_deleted = FALSE",
                    (target_node_id,),
                )
                target_node = cur.fetchone()
                if not target_node:
                    raise ValueError("目标节点不存在或已删除")

                cur.execute(
                    """
                    SELECT node_id
                    FROM execution_nodes
                    WHERE node_id = %s AND graph_id = %s AND is_deleted = FALSE
                    """,
                    (source_node_id, graph_id),
                )
                if not cur.fetchone():
                    raise ValueError("源节点不属于当前图")

                cur.execute(
                    """
                    SELECT node_id
                    FROM execution_nodes
                    WHERE node_id = %s AND graph_id = %s AND is_deleted = FALSE
                    """,
                    (target_node_id, graph_id),
                )
                if not cur.fetchone():
                    raise ValueError("目标节点不属于当前图")

                # Create edge
                try:
                    cur.execute(
                        """
                        INSERT INTO execution_edges(
                            edge_id, graph_id, source_node_id, target_node_id,
                            edge_type, label, condition_expr, config_json, order_index,
                            created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        RETURNING edge_id, graph_id, source_node_id, target_node_id,
                                  edge_type, label, condition_expr, config_json, order_index,
                                  created_at::text AS created_at
                        """,
                        (
                            edge_id,
                            graph_id,
                            source_node_id,
                            target_node_id,
                            edge_type,
                            label,
                            condition_expr,
                            json.dumps(config_json) if config_json else None,
                            order_index,
                        ),
                    )
                    return dict(cur.fetchone())
                except IntegrityError as e:
                    if "execution_graphs" in str(e):
                        raise ValueError("图不存在或已删除")
                    if "execution_nodes" in str(e):
                        raise ValueError("节点不存在或已删除")
                    if "unique" in str(e).lower():
                        raise ValueError("相同的边已存在")
                    raise

    def list_edges(
        self, graph_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if include_deleted:
                    cur.execute(
                        """
                        SELECT edge_id, graph_id, source_node_id, target_node_id,
                               edge_type, label, condition_expr, config_json, order_index,
                               created_at::text AS created_at
                        FROM execution_edges
                        WHERE graph_id = %s
                        ORDER BY order_index, created_at
                        """,
                        (graph_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT edge_id, graph_id, source_node_id, target_node_id,
                               edge_type, label, condition_expr, config_json, order_index,
                               created_at::text AS created_at
                        FROM execution_edges
                        WHERE graph_id = %s AND is_deleted = FALSE
                        ORDER BY order_index, created_at
                        """,
                        (graph_id,),
                    )
                return [dict(row) for row in cur.fetchall()]

    def get_edge(self, edge_id: str, include_deleted: bool = False) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if include_deleted:
                    cur.execute(
                        """
                        SELECT edge_id, graph_id, source_node_id, target_node_id,
                               edge_type, label, condition_expr, config_json, order_index,
                               created_at::text AS created_at
                        FROM execution_edges
                        WHERE edge_id = %s
                        """,
                        (edge_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT edge_id, graph_id, source_node_id, target_node_id,
                               edge_type, label, condition_expr, config_json, order_index,
                               created_at::text AS created_at
                        FROM execution_edges
                        WHERE edge_id = %s AND is_deleted = FALSE
                        """,
                        (edge_id,),
                    )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_edge(
        self,
        edge_id: str,
        label: str = None,
        edge_type: str = None,
        condition_expr: str = None,
        config_json: Dict = None,
        order_index: int = None,
        updated_by: str = "",
    ) -> Dict[str, Any]:
        fields = []
        values = []

        if label is not None:
            fields.append("label = %s")
            values.append(label)
        if edge_type is not None:
            if edge_type not in _ALLOWED_EDGE_TYPES:
                raise ValueError(f"edge_type 必须是: {', '.join(_ALLOWED_EDGE_TYPES)}")
            fields.append("edge_type = %s")
            values.append(edge_type)
        if condition_expr is not None:
            fields.append("condition_expr = %s")
            values.append(condition_expr)
        if config_json is not None:
            fields.append("config_json = %s")
            values.append(json.dumps(config_json) if config_json else None)
        if order_index is not None:
            fields.append("order_index = %s")
            values.append(order_index)

        if not fields:
            return self.get_edge(edge_id)

        fields.append("updated_at = NOW()")
        values.append(edge_id)

        sql = (
            f"UPDATE execution_edges SET {', '.join(fields)} WHERE edge_id = %s AND is_deleted = FALSE"
            " RETURNING edge_id, graph_id, source_node_id, target_node_id,"
            " edge_type, label, condition_expr, config_json, order_index, created_at::text AS created_at"
        )

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, values)
                row = cur.fetchone()
                if not row:
                    raise ValueError("边不存在或已删除")
                return dict(row)

    def delete_edge(self, edge_id: str, updated_by: str = "") -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE execution_edges
                    SET is_deleted = TRUE, updated_at = NOW()
                    WHERE edge_id = %s AND is_deleted = FALSE
                    RETURNING edge_id
                    """,
                    (edge_id,),
                )
                return cur.fetchone() is not None

    # =======================
    # Aggregated Methods
    # =======================

    def get_graph_detail(
        self, graph_id: str, include_deleted: bool = False
    ) -> Dict[str, Any]:
        graph = self.get_execution_graph(graph_id, include_deleted)
        if not graph:
            return {"graph": None, "containers": [], "nodes": [], "edges": []}

        containers = self.list_containers(graph_id, include_deleted)
        nodes = self.list_nodes(graph_id, include_deleted)
        edges = self.list_edges(graph_id, include_deleted)

        return {
            "graph": graph,
            "containers": containers,
            "nodes": nodes,
            "edges": edges,
        }

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
