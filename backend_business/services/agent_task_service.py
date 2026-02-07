"""
Agent pending tasks service.

Manages tasks that require user approval before execution.
"""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor

from backend_business.services.db_service import db_service


class AgentTaskService:
    # ========================
    # Task Management
    # ========================
    def create_task(
        self,
        user_id: str,
        task_type: str,
        title: str,
        description: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new pending task for user approval."""
        if not user_id:
            raise ValueError("user_id is required")
        if not task_type:
            raise ValueError("task_type is required")
        if not title:
            raise ValueError("title is required")

        task_id = f"task_{uuid.uuid4().hex[:12]}"
        created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_pending_tasks (
                        task_id, session_id, project_id, user_id,
                        task_type, title, description, payload, status, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'pending', %s)
                    """,
                    (
                        task_id,
                        session_id,
                        project_id,
                        user_id,
                        task_type,
                        title,
                        description,
                        json.dumps(payload, ensure_ascii=False) if payload else None,
                        created_at,
                    ),
                )

        return {
            "task_id": task_id,
            "session_id": session_id,
            "project_id": project_id,
            "user_id": user_id,
            "task_type": task_type,
            "title": title,
            "description": description,
            "payload": payload,
            "status": "pending",
            "created_at": created_at,
            "resolved_at": None,
        }

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by ID."""
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        task_id, session_id, project_id, user_id,
                        task_type, title, description, payload, status,
                        created_at::text AS created_at,
                        resolved_at::text AS resolved_at
                    FROM agent_pending_tasks
                    WHERE task_id = %s
                    """,
                    (task_id,),
                )
                row = cur.fetchone()

        if not row:
            return None

        task = dict(row)
        if task.get("payload") and isinstance(task["payload"], str):
            try:
                task["payload"] = json.loads(task["payload"])
            except Exception:
                pass
        return task

    def list_pending_tasks(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List pending tasks for a user, optionally filtered by project."""
        limit = max(1, min(200, int(limit)))
        params: List[Any] = [user_id]
        where_clause = "WHERE user_id = %s AND status = 'pending'"

        if project_id:
            where_clause += " AND project_id = %s"
            params.append(project_id)

        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT
                        task_id, session_id, project_id, user_id,
                        task_type, title, description, payload, status,
                        created_at::text AS created_at,
                        resolved_at::text AS resolved_at
                    FROM agent_pending_tasks
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    params + [limit],
                )
                rows = cur.fetchall()

        tasks = []
        for row in rows:
            task = dict(row)
            if task.get("payload") and isinstance(task["payload"], str):
                try:
                    task["payload"] = json.loads(task["payload"])
                except Exception:
                    pass
            tasks.append(task)
        return tasks

    def list_all_tasks(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List all tasks for a user with optional filters."""
        limit = max(1, min(200, int(limit)))
        params: List[Any] = [user_id]
        where_clause = "WHERE user_id = %s"

        if project_id:
            where_clause += " AND project_id = %s"
            params.append(project_id)

        if status:
            where_clause += " AND status = %s"
            params.append(status)

        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT
                        task_id, session_id, project_id, user_id,
                        task_type, title, description, payload, status,
                        created_at::text AS created_at,
                        resolved_at::text AS resolved_at
                    FROM agent_pending_tasks
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    params + [limit],
                )
                rows = cur.fetchall()

        tasks = []
        for row in rows:
            task = dict(row)
            if task.get("payload") and isinstance(task["payload"], str):
                try:
                    task["payload"] = json.loads(task["payload"])
                except Exception:
                    pass
            tasks.append(task)
        return tasks

    def approve_task(self, task_id: str, user_id: str) -> Dict[str, Any]:
        """Approve a pending task."""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        if task["user_id"] != user_id:
            raise ValueError("Not authorized to approve this task")
        if task["status"] != "pending":
            raise ValueError(f"Task is not pending, current status: {task['status']}")

        resolved_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_pending_tasks
                    SET status = 'approved', resolved_at = %s
                    WHERE task_id = %s
                    """,
                    (resolved_at, task_id),
                )

        task["status"] = "approved"
        task["resolved_at"] = resolved_at

        # TODO: Execute the task payload here
        # This would involve calling the appropriate service based on task_type
        # For now, we just return the approved task

        return task

    def reject_task(self, task_id: str, user_id: str) -> Dict[str, Any]:
        """Reject a pending task."""
        task = self.get_task(task_id)
        if not task:
            raise ValueError(f"Task {task_id} not found")
        if task["user_id"] != user_id:
            raise ValueError("Not authorized to reject this task")
        if task["status"] != "pending":
            raise ValueError(f"Task is not pending, current status: {task['status']}")

        resolved_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_pending_tasks
                    SET status = 'rejected', resolved_at = %s
                    WHERE task_id = %s
                    """,
                    (resolved_at, task_id),
                )

        task["status"] = "rejected"
        task["resolved_at"] = resolved_at
        return task

    def get_pending_count(
        self,
        user_id: str,
        project_id: Optional[str] = None,
    ) -> int:
        """Get count of pending tasks for a user."""
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                if project_id:
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM agent_pending_tasks
                        WHERE user_id = %s AND project_id = %s AND status = 'pending'
                        """,
                        (user_id, project_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM agent_pending_tasks
                        WHERE user_id = %s AND status = 'pending'
                        """,
                        (user_id,),
                    )
                result = cur.fetchone()
                return result[0] if result else 0

    def expire_old_tasks(self, hours: int = 24) -> int:
        """Mark old pending tasks as expired."""
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_pending_tasks
                    SET status = 'expired', resolved_at = NOW()
                    WHERE status = 'pending'
                      AND created_at < NOW() - INTERVAL '%s hours'
                    """,
                    (hours,),
                )
                return cur.rowcount


agent_task_service = AgentTaskService() if db_service else None
