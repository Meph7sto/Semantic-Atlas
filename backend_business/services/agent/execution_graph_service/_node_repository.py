"""
执行拓扑图服务 — Node 实体 CRUD
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional, Sequence

from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor

from backend_business.services.agent.execution_graph_service._base import (
    _ALLOWED_NODE_TYPES,
    _ALLOWED_ROLE_TYPES,
)


class _NodeMixin:
    """Node 实体的 CRUD 方法。"""

    _NODE_RETURNING_COLS = (
        "node_id, graph_id, container_id, subgraph_id, node_key, label, node_type, role_type,"
        " phase_label, task_prompt, conditional_edges,"
        " config_json, input_schema_json, output_schema_json, order_index,"
        " created_at::text AS created_at"
    )

    _NODE_SELECT_COLS = (
        "node_id, graph_id, container_id, subgraph_id, node_key, label, node_type, role_type,"
        " phase_label, task_prompt, conditional_edges,"
        " config_json, input_schema_json, output_schema_json, order_index,"
        " created_at::text AS created_at"
    )

    def create_node(
        self,
        graph_id: str,
        node_key: str,
        label: str,
        node_type: str,
        role_type: str,
        container_id: str = None,
        subgraph_id: str = None,
        phase_label: str = None,
        task_prompt: str = None,
        conditional_edges: Sequence = None,
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
        normalized_subgraph_id = subgraph_id or None

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
                if normalized_subgraph_id:
                    cur.execute(
                        """
                        SELECT subgraph_id
                        FROM execution_subgraphs
                        WHERE subgraph_id = %s AND graph_id = %s AND is_deleted = FALSE
                        """,
                        (normalized_subgraph_id, graph_id),
                    )
                    if not cur.fetchone():
                        raise ValueError("子图不存在、已删除，或不属于当前图")
                try:
                    cur.execute(
                        f"""
                        INSERT INTO execution_nodes(
                            node_id, graph_id, container_id, subgraph_id, node_key, label, node_type, role_type,
                            phase_label, task_prompt, conditional_edges,
                            config_json, input_schema_json, output_schema_json, order_index,
                            created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                        RETURNING {self._NODE_RETURNING_COLS}
                        """,
                        (
                            node_id,
                            graph_id,
                            normalized_container_id,
                            normalized_subgraph_id,
                            node_key,
                            label,
                            node_type,
                            role_type,
                            phase_label or None,
                            task_prompt or None,
                            json.dumps(conditional_edges) if conditional_edges else None,
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
                        f"""
                        SELECT {self._NODE_SELECT_COLS}
                        FROM execution_nodes
                        WHERE graph_id = %s
                        ORDER BY order_index, created_at
                        """,
                        (graph_id,),
                    )
                else:
                    cur.execute(
                        f"""
                        SELECT {self._NODE_SELECT_COLS}
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
                        f"""
                        SELECT {self._NODE_SELECT_COLS}
                        FROM execution_nodes
                        WHERE node_id = %s
                        """,
                        (node_id,),
                    )
                else:
                    cur.execute(
                        f"""
                        SELECT {self._NODE_SELECT_COLS}
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
        subgraph_id: str = None,
        label: str = None,
        node_type: str = None,
        role_type: str = None,
        phase_label: str = None,
        task_prompt: str = None,
        conditional_edges: Sequence = None,
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
        if subgraph_id is not None:
            fields.append("subgraph_id = %s")
            values.append(subgraph_id or None)
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
        if phase_label is not None:
            fields.append("phase_label = %s")
            values.append(phase_label or None)
        if task_prompt is not None:
            fields.append("task_prompt = %s")
            values.append(task_prompt or None)
        if conditional_edges is not None:
            fields.append("conditional_edges = %s")
            values.append(json.dumps(conditional_edges) if conditional_edges else None)
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
            f" RETURNING {self._NODE_RETURNING_COLS}"
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
