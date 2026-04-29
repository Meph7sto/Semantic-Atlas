from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor


class RequirementGraphDataAccess:
    """Read-only data access for requirement graph assembly."""

    def __init__(self, db: Any):
        self._db = db

    def resolve_project_session(self, project_id: Optional[str]) -> Optional[str]:
        if not project_id:
            return None
        with self._db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT current_session_id
                    FROM manage_projects
                    WHERE project_id = %s
                    """,
                    (project_id,),
                )
                row = cur.fetchone()
        return row[0] if row and row[0] else None

    def resolve_project_id_by_session(self, session_id: Optional[str]) -> Optional[str]:
        if not session_id:
            return None
        with self._db.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT project_id
                    FROM manage_projects
                    WHERE current_session_id = %s
                    ORDER BY updated_at DESC NULLS LAST, created_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
        return row[0] if row and row[0] else None

    def load_project_requirements(
        self,
        project_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not project_id:
            return []
        with self._db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, project_id, requirement_type, status, title,
                           description, priority, assignee, tags, parent_id,
                           source_req_id, source_level, custom_fields, created_by,
                           updated_by, created_at::text AS created_at,
                           updated_at::text AS updated_at
                    FROM manage_requirements
                    WHERE project_id = %s AND COALESCE(deleted, FALSE) = FALSE
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (project_id, limit),
                )
                return [dict(row) for row in cur.fetchall()]

    def load_l123_requirements(
        self,
        session_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not session_id:
            return []
        with self._db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, session_id, level, text, fingerprint,
                           anchor_span_id, r, created_at::text AS created_at
                    FROM requirements_l123
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (session_id, limit),
                )
                return [dict(row) for row in cur.fetchall()]

    def load_l4_requirements(
        self,
        session_id: Optional[str],
        limit: int,
    ) -> List[Dict[str, Any]]:
        if not session_id:
            return []
        with self._db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, session_id, source_top_id, source_top_text,
                           text, component, acceptance_criteria, test_method,
                           interfaces, data_contracts, error_handling, nfr,
                           open_questions, evidence_ids, confidence, source,
                           meta, created_at::text AS created_at
                    FROM low_level_requirements
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    (session_id, limit),
                )
                return [dict(row) for row in cur.fetchall()]

    def load_l4_requirement_links(
        self,
        session_id: Optional[str],
    ) -> List[Dict[str, Any]]:
        if not session_id:
            return []
        with self._db.get_connection() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, session_id, top_req_id,
                           created_at::text AS created_at
                    FROM low_level_requirement_links
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def load_project_members(self, project_id: Optional[str]) -> Dict[str, Dict[str, Any]]:
        if not project_id:
            return {}
        if hasattr(self._db, "list_project_members"):
            data = self._db.list_project_members(project_id, include_roles=True)
            members = data.get("members") if isinstance(data, dict) else []
            return {member["user_id"]: member for member in members if member.get("user_id")}
        return {}
