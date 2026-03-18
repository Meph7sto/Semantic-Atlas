"""
执行拓扑图服务 — Graph 实体 CRUD
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor

from backend_business.services.agent.execution_graph_service._base import (
    _ALLOWED_GRAPH_STATUSES,
    _ALLOWED_GRAPH_TYPES,
)


class _GraphMixin:
    """Graph 实体的 CRUD 方法。"""

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

    def create_runtime_graph(
        self,
        project_id: str,
        name: str,
        description: str = "",
        created_by: str = "",
        meta_json: Dict[str, Any] | None = None,
        layout_json: Dict[str, Any] | None = None,
        status: str = "running",
    ) -> Dict[str, Any]:
        if status not in _ALLOWED_GRAPH_STATUSES:
            raise ValueError(f"status 必须是: {', '.join(sorted(_ALLOWED_GRAPH_STATUSES))}")

        graph_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO execution_graphs(
                            graph_id, project_id, name, description,
                            graph_type, version, status, layout_json, meta_json,
                            created_by, updated_by, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, 'agent_runtime_execution', 1, %s, %s, %s, %s, %s, NOW(), NOW())
                        RETURNING graph_id, project_id, name, description, graph_type, version, status,
                                  layout_json, meta_json, created_by, updated_by,
                                  created_at::text AS created_at
                        """,
                        (
                            graph_id,
                            project_id,
                            name,
                            description,
                            status,
                            json.dumps(layout_json) if layout_json else None,
                            json.dumps(meta_json) if meta_json else None,
                            created_by,
                            created_by,
                        ),
                    )
                    return dict(cur.fetchone())
                except IntegrityError as e:
                    if "manage_projects" in str(e):
                        raise ValueError("项目不存在")
                    raise

    def list_execution_graphs(
        self,
        project_id: str,
        include_deleted: bool = False,
        graph_types: List[str] | None = None,
    ) -> List[Dict[str, Any]]:
        normalized_graph_types = graph_types or ["execution_topology_template"]
        invalid_graph_types = [graph_type for graph_type in normalized_graph_types if graph_type not in _ALLOWED_GRAPH_TYPES]
        if invalid_graph_types:
            raise ValueError(f"graph_type 必须是: {', '.join(sorted(_ALLOWED_GRAPH_TYPES))}")

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
                          AND graph_type = ANY(%s)
                        ORDER BY updated_at DESC
                        """,
                        (project_id, normalized_graph_types),
                    )
                else:
                    cur.execute(
                        """
                        SELECT graph_id, project_id, name, description, graph_type, version, status,
                               layout_json, meta_json, created_by, updated_by,
                               created_at::text AS created_at
                        FROM execution_graphs
                        WHERE project_id = %s
                          AND graph_type = ANY(%s)
                          AND is_deleted = FALSE
                        ORDER BY updated_at DESC
                        """,
                        (project_id, normalized_graph_types),
                )
                return [dict(row) for row in cur.fetchall()]

    def list_runtime_graphs_by_session(
        self,
        session_id: str,
        *,
        project_id: str | None = None,
        include_deleted: bool = False,
    ) -> List[Dict[str, Any]]:
        if not session_id:
            return []

        where_deleted = "" if include_deleted else "AND is_deleted = FALSE"
        project_clause = ""
        params: List[Any] = [session_id]
        if project_id:
            project_clause = "AND project_id = %s"
            params.append(project_id)

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT graph_id, project_id, name, description, graph_type, version, status,
                           layout_json, meta_json, created_by, updated_by,
                           created_at::text AS created_at
                    FROM execution_graphs
                    WHERE graph_type = 'agent_runtime_execution'
                      AND meta_json->>'session_id' = %s
                      {project_clause}
                      {where_deleted}
                    ORDER BY updated_at DESC
                    """,
                    params,
                )
                return [dict(row) for row in cur.fetchall()]

    def get_latest_runtime_graph_by_session(
        self,
        session_id: str,
        *,
        project_id: str | None = None,
        include_deleted: bool = False,
    ) -> Optional[Dict[str, Any]]:
        graphs = self.list_runtime_graphs_by_session(
            session_id=session_id,
            project_id=project_id,
            include_deleted=include_deleted,
        )
        return graphs[0] if graphs else None

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
