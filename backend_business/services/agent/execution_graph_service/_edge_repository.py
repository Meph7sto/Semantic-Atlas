"""
执行拓扑图服务 — Edge 实体 CRUD
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor

from backend_business.services.agent.execution_graph_service._base import (
    _ALLOWED_EDGE_TYPES,
)


class _EdgeMixin:
    """Edge 实体的 CRUD 方法。"""

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
