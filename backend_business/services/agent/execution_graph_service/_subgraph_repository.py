"""
执行拓扑图服务 — Subgraph 实体 CRUD
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor


class _SubgraphMixin:
    """Subgraph 实体的 CRUD 方法。"""

    def create_subgraph(
        self,
        graph_id: str,
        container_id: str,
        subgraph_key: str,
        label: str,
        task_description: str,
        order_index: int = 0,
        config_json: Dict = None,
        created_by: str = "",
    ) -> Dict[str, Any]:
        subgraph_id = str(uuid.uuid4())

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Verify container belongs to graph
                cur.execute(
                    "SELECT container_id FROM execution_containers WHERE container_id = %s AND graph_id = %s AND is_deleted = FALSE",
                    (container_id, graph_id),
                )
                if not cur.fetchone():
                    raise ValueError("容器不存在、已删除，或不属于当前图")
                try:
                    cur.execute(
                        """
                        INSERT INTO execution_subgraphs(
                            subgraph_id, graph_id, container_id, subgraph_key, label,
                            task_description, status, order_index, config_json, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        RETURNING subgraph_id, graph_id, container_id, subgraph_key, label,
                                  task_description, status, order_index, config_json,
                                  created_at::text AS created_at
                        """,
                        (
                            subgraph_id,
                            graph_id,
                            container_id,
                            subgraph_key,
                            label,
                            task_description,
                            "pending",
                            order_index,
                            json.dumps(config_json) if config_json else None,
                        ),
                    )
                    return dict(cur.fetchone())
                except IntegrityError as e:
                    if "unique" in str(e).lower() and "subgraph_key" in str(e).lower():
                        raise ValueError(f"子图 key '{subgraph_key}' 在图中已存在")
                    raise

    def list_subgraphs(
        self, graph_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if include_deleted:
                    cur.execute(
                        """
                        SELECT subgraph_id, graph_id, container_id, subgraph_key, label,
                               task_description, status, order_index, config_json,
                               created_at::text AS created_at
                        FROM execution_subgraphs
                        WHERE graph_id = %s
                        ORDER BY order_index, created_at
                        """,
                        (graph_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT subgraph_id, graph_id, container_id, subgraph_key, label,
                               task_description, status, order_index, config_json,
                               created_at::text AS created_at
                        FROM execution_subgraphs
                        WHERE graph_id = %s AND is_deleted = FALSE
                        ORDER BY order_index, created_at
                        """,
                        (graph_id,),
                    )
                return [dict(row) for row in cur.fetchall()]

    def get_subgraph(
        self, subgraph_id: str, include_deleted: bool = False
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if include_deleted:
                    cur.execute(
                        """
                        SELECT subgraph_id, graph_id, container_id, subgraph_key, label,
                               task_description, status, order_index, config_json,
                               created_at::text AS created_at
                        FROM execution_subgraphs
                        WHERE subgraph_id = %s
                        """,
                        (subgraph_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT subgraph_id, graph_id, container_id, subgraph_key, label,
                               task_description, status, order_index, config_json,
                               created_at::text AS created_at
                        FROM execution_subgraphs
                        WHERE subgraph_id = %s AND is_deleted = FALSE
                        """,
                        (subgraph_id,),
                    )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_subgraph(
        self,
        subgraph_id: str,
        label: str = None,
        task_description: str = None,
        status: str = None,
        order_index: int = None,
        config_json: Dict = None,
        updated_by: str = "",
    ) -> Dict[str, Any]:
        fields = []
        values = []

        if label is not None:
            fields.append("label = %s")
            values.append(label)
        if task_description is not None:
            fields.append("task_description = %s")
            values.append(task_description)
        if status is not None:
            _ALLOWED_SUBGRAPH_STATUSES = {"pending", "running", "completed", "failed"}
            if status not in _ALLOWED_SUBGRAPH_STATUSES:
                raise ValueError(f"status 必须是: {', '.join(sorted(_ALLOWED_SUBGRAPH_STATUSES))}")
            fields.append("status = %s")
            values.append(status)
        if order_index is not None:
            fields.append("order_index = %s")
            values.append(order_index)
        if config_json is not None:
            fields.append("config_json = %s")
            values.append(json.dumps(config_json) if config_json else None)

        if not fields:
            return self.get_subgraph(subgraph_id)

        fields.append("updated_at = NOW()")
        values.append(subgraph_id)

        sql = (
            f"UPDATE execution_subgraphs SET {', '.join(fields)} "
            "WHERE subgraph_id = %s AND is_deleted = FALSE "
            "RETURNING subgraph_id, graph_id, container_id, subgraph_key, label, "
            "task_description, status, order_index, config_json, created_at::text AS created_at"
        )

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, values)
                row = cur.fetchone()
                if not row:
                    raise ValueError("子图不存在或已删除")
                return dict(row)

    def delete_subgraph(self, subgraph_id: str, updated_by: str = "") -> bool:
        with self._connect() as conn:
            with conn.cursor() as cur:
                # Clear subgraph_id from nodes that referenced this subgraph
                cur.execute(
                    """
                    UPDATE execution_nodes
                    SET subgraph_id = NULL, updated_at = NOW()
                    WHERE subgraph_id = %s AND is_deleted = FALSE
                    """,
                    (subgraph_id,),
                )
                cur.execute(
                    """
                    UPDATE execution_subgraphs
                    SET is_deleted = TRUE, updated_at = NOW()
                    WHERE subgraph_id = %s AND is_deleted = FALSE
                    RETURNING subgraph_id
                    """,
                    (subgraph_id,),
                )
                return cur.fetchone() is not None
