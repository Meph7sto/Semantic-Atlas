"""
执行拓扑图服务 — Container 实体 CRUD
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor

from backend_business.services.agent.execution_graph_service._base import (
    _ALLOWED_ROLE_TYPES,
)


class _ContainerMixin:
    """Container 实体的 CRUD 方法。"""

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
