"""Agent pending task queue - CRUD and approval/rejection state machine."""

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor

from backend_business.services.db_service import db_service


def _parse_payload(task: dict) -> dict:
    if task.get("payload") and isinstance(task["payload"], str):
        try:
            task["payload"] = json.loads(task["payload"])
        except Exception:
            pass
    return task


class AgentTaskQueue:
    # ========================
    # Create
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

    # ========================
    # Read
    # ========================

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT task_id, session_id, project_id, user_id,
                           task_type, title, description, payload, status,
                           created_at::text AS created_at,
                           resolved_at::text AS resolved_at
                    FROM agent_pending_tasks
                    WHERE task_id = %s
                    """,
                    (task_id,),
                )
                row = cur.fetchone()
        return _parse_payload(dict(row)) if row else None

    def list_pending_tasks(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return self._list_tasks(user_id, project_id=project_id, status="pending", limit=limit)

    def list_all_tasks(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        return self._list_tasks(user_id, project_id=project_id, status=status, limit=limit)

    def get_pending_count(
        self,
        user_id: str,
        project_id: Optional[str] = None,
    ) -> int:
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                if project_id:
                    cur.execute(
                        """
                        SELECT COUNT(*) FROM agent_pending_tasks
                        WHERE user_id = %s AND project_id = %s AND status = 'pending'
                        """,
                        (user_id, project_id),
                    )
                else:
                    cur.execute(
                        "SELECT COUNT(*) FROM agent_pending_tasks WHERE user_id = %s AND status = 'pending'",
                        (user_id,),
                    )
                result = cur.fetchone()
                return result[0] if result else 0

    # ========================
    # Approve / Reject
    # ========================

    def approve_task(self, task_id: str, user_id: str) -> Dict[str, Any]:
        """Approve and execute a pending task.

        Uses SELECT FOR UPDATE to prevent concurrent approvals/rejections.
        Task execution and final status transition happen in one DB transaction.
        """
        # Lazy import avoids circular dependency at module load time
        from backend_business.services.agent.tasks.executor import task_executor_registry

        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT task_id, session_id, project_id, user_id,
                           task_type, title, description, payload, status,
                           created_at::text AS created_at,
                           resolved_at::text AS resolved_at
                    FROM agent_pending_tasks
                    WHERE task_id = %s
                    FOR UPDATE
                    """,
                    (task_id,),
                )
                row = cur.fetchone()

                if not row:
                    raise ValueError(f"Task {task_id} not found")

                task = _parse_payload(dict(row))

                if task["user_id"] != user_id:
                    raise ValueError("Not authorized to approve this task")
                if task["status"] != "pending":
                    raise ValueError(f"Task is not pending, current status: {task['status']}")

                execution_result = task_executor_registry.execute(
                    task["task_type"],
                    task.get("payload") or {},
                    user_id,
                    conn=conn,
                )

                resolved_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                cur.execute(
                    """
                    UPDATE agent_pending_tasks
                    SET status = 'approved', resolved_at = %s
                    WHERE task_id = %s AND status = 'pending'
                    """,
                    (resolved_at, task_id),
                )
                if cur.rowcount != 1:
                    raise ValueError("Task status changed during approval, please retry")
                conn.commit()

        task["status"] = "approved"
        task["resolved_at"] = resolved_at
        task["execution_result"] = execution_result

        self._send_confirmation(task, execution_result)
        return task

    def reject_task(self, task_id: str, user_id: str) -> Dict[str, Any]:
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT task_id, session_id, project_id, user_id,
                           task_type, title, description, payload, status,
                           created_at::text AS created_at,
                           resolved_at::text AS resolved_at
                    FROM agent_pending_tasks
                    WHERE task_id = %s
                    FOR UPDATE
                    """,
                    (task_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError(f"Task {task_id} not found")

                task = _parse_payload(dict(row))
                if task["user_id"] != user_id:
                    raise ValueError("Not authorized to reject this task")
                if task["status"] != "pending":
                    raise ValueError(
                        f"Task is not pending, current status: {task['status']}"
                    )

                resolved_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                cur.execute(
                    """
                    UPDATE agent_pending_tasks
                    SET status = 'rejected', resolved_at = %s
                    WHERE task_id = %s AND status = 'pending'
                    """,
                    (resolved_at, task_id),
                )
                if cur.rowcount != 1:
                    raise ValueError("Task status changed during rejection, please retry")
                conn.commit()

        task["status"] = "rejected"
        task["resolved_at"] = resolved_at
        return task

    # ========================
    # Maintenance
    # ========================

    def expire_old_tasks(self, hours: int = 24) -> int:
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

    # ========================
    # Internal helpers
    # ========================

    def _list_tasks(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(200, int(limit)))
        params: List[Any] = [user_id]
        where = "WHERE user_id = %s"
        if project_id:
            where += " AND project_id = %s"
            params.append(project_id)
        if status:
            where += " AND status = %s"
            params.append(status)

        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT task_id, session_id, project_id, user_id,
                           task_type, title, description, payload, status,
                           created_at::text AS created_at,
                           resolved_at::text AS resolved_at
                    FROM agent_pending_tasks
                    {where}
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    params + [limit],
                )
                rows = cur.fetchall()
        return [_parse_payload(dict(r)) for r in rows]

    def _send_confirmation(
        self, task: Dict[str, Any], execution_result: Dict[str, Any]
    ) -> None:
        """Send a confirmation message back to the originating chat session."""
        session_id = task.get("session_id")
        if not session_id:
            return
        try:
            from backend_business.services.ai_chat_service import ai_chat_service
            from backend_business.services.agent.tasks.executor import task_executor_registry

            if not ai_chat_service:
                return

            executor = task_executor_registry.get(task.get("task_type", ""))
            content = executor.confirmation_message(task, execution_result)

            ai_chat_service.create_message(
                session_id=session_id,
                user_id=task.get("user_id") or "",
                role="assistant",
                content=content,
                metadata={
                    "type": "task_approval_confirmation",
                    "task_id": task.get("task_id"),
                    "task_type": task.get("task_type"),
                    "execution_result": execution_result,
                },
            )
        except Exception:
            pass  # confirmation failure must not break the approval response


agent_task_queue = AgentTaskQueue() if db_service else None
