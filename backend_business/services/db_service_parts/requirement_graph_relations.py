import json
import uuid
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor

from backend_business.services.db_service_parts.utils import _utc_now_iso


class RequirementGraphRelationsMixin:
    def save_requirement_graph_snapshot(
        self,
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        relation_mode: str,
        edges: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        normalized_relation_mode = str(relation_mode or "").strip().lower() or "default"
        normalized_project_id = str(project_id or "").strip() or None
        normalized_session_id = str(session_id or "").strip() or None
        if not normalized_project_id and not normalized_session_id:
            raise ValueError("project_id 和 session_id 至少提供一个")

        snapshot_id = uuid.uuid4().hex
        now = _utc_now_iso()
        normalized_edges = [
            edge for edge in (self._normalize_requirement_relation_edge(item) for item in edges)
            if edge
        ]

        where_sql, where_params = self._build_relation_snapshot_where_clause(
            project_id=normalized_project_id,
            session_id=normalized_session_id,
            relation_mode=normalized_relation_mode,
            active_only=True,
        )

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE requirement_graph_relations
                    SET is_active = FALSE, invalidated_at = %s
                    WHERE {where_sql}
                    """,
                    (now, *where_params),
                )
                for edge in normalized_edges:
                    cur.execute(
                        """
                        INSERT INTO requirement_graph_relations (
                            snapshot_id, project_id, session_id, relation_mode,
                            source_node_id, target_node_id, source_req_id, target_req_id,
                            relation_type, source_kind, source_detail, weight, confidence,
                            reason, evidence, model, review_action, review_package_id,
                            properties, is_active, created_at
                        )
                        VALUES (
                            %s, %s, %s, %s,
                            %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, %s, %s, %s, %s,
                            %s, TRUE, %s
                        )
                        """,
                        (
                            snapshot_id,
                            normalized_project_id,
                            normalized_session_id,
                            normalized_relation_mode,
                            edge["source_node_id"],
                            edge["target_node_id"],
                            edge["source_req_id"],
                            edge["target_req_id"],
                            edge["relation_type"],
                            edge["source_kind"],
                            edge["source_detail"],
                            edge["weight"],
                            edge["confidence"],
                            edge["reason"],
                            json.dumps(edge["evidence"], ensure_ascii=False),
                            edge["model"],
                            edge["review_action"],
                            edge["review_package_id"],
                            json.dumps(edge["properties"], ensure_ascii=False),
                            now,
                        ),
                    )

        return {
            "snapshot_id": snapshot_id,
            "relation_mode": normalized_relation_mode,
            "edge_count": len(normalized_edges),
        }

    def get_latest_requirement_graph_snapshot(
        self,
        *,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        relation_mode: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        normalized_relation_mode = str(relation_mode or "").strip().lower() or None
        normalized_project_id = str(project_id or "").strip() or None
        normalized_session_id = str(session_id or "").strip() or None
        if not normalized_project_id and not normalized_session_id:
            return None

        where_sql, where_params = self._build_relation_snapshot_where_clause(
            project_id=normalized_project_id,
            session_id=normalized_session_id,
            relation_mode=normalized_relation_mode,
            active_only=True,
        )

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT snapshot_id, project_id, session_id, relation_mode,
                           is_active, created_at::text AS created_at,
                           invalidated_at::text AS invalidated_at
                    FROM requirement_graph_relations
                    WHERE {where_sql}
                    ORDER BY id DESC
                    LIMIT 1
                    """,
                    where_params,
                )
                row = cur.fetchone()
                if not row:
                    return None
        return self.get_requirement_graph_snapshot_by_id(row["snapshot_id"])

    def list_requirement_graph_snapshots(
        self,
        *,
        project_id: Optional[str] = None,
        session_id: Optional[str] = None,
        relation_mode: Optional[str] = None,
        limit: int = 20,
    ) -> List[Dict[str, Any]]:
        normalized_relation_mode = str(relation_mode or "").strip().lower() or None
        normalized_project_id = str(project_id or "").strip() or None
        normalized_session_id = str(session_id or "").strip() or None
        normalized_limit = max(1, min(100, int(limit or 20)))
        if not normalized_project_id and not normalized_session_id:
            return []

        where_sql, where_params = self._build_relation_snapshot_where_clause(
            project_id=normalized_project_id,
            session_id=normalized_session_id,
            relation_mode=normalized_relation_mode,
            active_only=False,
        )

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT snapshot_id, project_id, session_id, relation_mode,
                           BOOL_OR(is_active) AS is_active,
                           COUNT(*)::int AS edge_count,
                           MAX(created_at)::text AS created_at,
                           MAX(invalidated_at)::text AS invalidated_at,
                           MAX(id) AS latest_row_id
                    FROM requirement_graph_relations
                    WHERE {where_sql}
                    GROUP BY snapshot_id, project_id, session_id, relation_mode
                    ORDER BY latest_row_id DESC
                    LIMIT %s
                    """,
                    (*where_params, normalized_limit),
                )
                rows = cur.fetchall()

        return [self._serialize_requirement_graph_snapshot_summary(dict(row)) for row in rows]

    def get_requirement_graph_snapshot_by_id(self, snapshot_id: str) -> Optional[Dict[str, Any]]:
        normalized_snapshot_id = str(snapshot_id or "").strip()
        if not normalized_snapshot_id:
            return None

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT snapshot_id, project_id, session_id, relation_mode,
                           BOOL_OR(is_active) AS is_active,
                           COUNT(*)::int AS edge_count,
                           MAX(created_at)::text AS created_at,
                           MAX(invalidated_at)::text AS invalidated_at
                    FROM requirement_graph_relations
                    WHERE snapshot_id = %s
                    GROUP BY snapshot_id, project_id, session_id, relation_mode
                    """,
                    (normalized_snapshot_id,),
                )
                snapshot_row = cur.fetchone()
                if not snapshot_row:
                    return None
                cur.execute(
                    """
                    SELECT source_node_id, target_node_id, source_req_id, target_req_id,
                           relation_type, source_kind, source_detail, weight, confidence,
                           reason, evidence, model, review_action, review_package_id,
                           properties, created_at::text AS created_at
                    FROM requirement_graph_relations
                    WHERE snapshot_id = %s
                    ORDER BY id ASC
                    """,
                    (normalized_snapshot_id,),
                )
                rows = cur.fetchall()

        snapshot = self._serialize_requirement_graph_snapshot_summary(dict(snapshot_row))
        snapshot["edges"] = [dict(item) for item in rows]
        return snapshot

    @staticmethod
    def _serialize_requirement_graph_snapshot_summary(row: Dict[str, Any]) -> Dict[str, Any]:
        return {
            "snapshot_id": row.get("snapshot_id"),
            "project_id": row.get("project_id"),
            "session_id": row.get("session_id"),
            "relation_mode": row.get("relation_mode"),
            "created_at": row.get("created_at"),
            "invalidated_at": row.get("invalidated_at"),
            "is_active": bool(row.get("is_active")),
            "edge_count": int(row.get("edge_count") or 0),
        }

    @staticmethod
    def _normalize_requirement_relation_edge(edge: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(edge, dict):
            return None
        source = str(edge.get("source") or "").strip()
        target = str(edge.get("target") or "").strip()
        relation_type = str(edge.get("type") or "").strip()
        if not source.startswith("req:") or not target.startswith("req:") or not relation_type:
            return None

        properties = edge.get("properties") if isinstance(edge.get("properties"), dict) else {}
        return {
            "source_node_id": source,
            "target_node_id": target,
            "source_req_id": source.removeprefix("req:"),
            "target_req_id": target.removeprefix("req:"),
            "relation_type": relation_type,
            "source_kind": str(properties.get("source_kind") or "rule").strip() or "rule",
            "source_detail": str(properties.get("source_detail") or "").strip() or None,
            "weight": float(edge.get("weight") or 0),
            "confidence": float(properties.get("confidence")) if properties.get("confidence") is not None else None,
            "reason": str(properties.get("reason") or "").strip() or None,
            "evidence": properties.get("evidence") if isinstance(properties.get("evidence"), list) else [],
            "model": str(properties.get("model") or "").strip() or None,
            "review_action": str(properties.get("review_action") or "").strip() or None,
            "review_package_id": str(properties.get("review_package_id") or "").strip() or None,
            "properties": properties,
        }

    @staticmethod
    def _build_relation_snapshot_where_clause(
        *,
        project_id: Optional[str],
        session_id: Optional[str],
        relation_mode: Optional[str],
        active_only: bool,
    ) -> tuple[str, list[Any]]:
        clauses = []
        params: list[Any] = []
        if project_id:
            clauses.append("project_id = %s")
            params.append(project_id)
        if session_id:
            clauses.append("session_id = %s")
            params.append(session_id)
        if relation_mode:
            clauses.append("relation_mode = %s")
            params.append(relation_mode)
        if active_only:
            clauses.append("is_active = TRUE")
        if not clauses:
            raise ValueError("至少需要一个快照过滤条件")
        return " AND ".join(clauses), params
