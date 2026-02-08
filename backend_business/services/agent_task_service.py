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


def _get_requirements_manage_service():
    """Lazy import to avoid circular dependencies."""
    from backend_business.services.requirements_manage_service import (
        RequirementsManageService,
    )
    from backend_business.config import settings

    return RequirementsManageService(settings.POSTGRES_DSN)


def _get_ai_chat_service():
    """Lazy import to avoid circular dependencies."""
    from backend_business.services.ai_chat_service import ai_chat_service

    return ai_chat_service


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
        """
        Approve and execute a pending task.

        Uses SELECT FOR UPDATE to lock the task row during execution.
        Only marks as approved after successful execution.
        Writes a confirmation message back to the chat session.
        """
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Lock the task row to prevent concurrent approval
                cur.execute(
                    """
                    SELECT
                        task_id, session_id, project_id, user_id,
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

                task = dict(row)
                if task.get("payload") and isinstance(task["payload"], str):
                    try:
                        task["payload"] = json.loads(task["payload"])
                    except Exception:
                        pass

                if task["user_id"] != user_id:
                    raise ValueError("Not authorized to approve this task")
                if task["status"] != "pending":
                    raise ValueError(
                        f"Task is not pending, current status: {task['status']}"
                    )

                # Execute the task based on task_type
                execution_result = self._execute_task_payload(task, user_id)

                # Mark as approved after successful execution
                resolved_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"
                cur.execute(
                    """
                    UPDATE agent_pending_tasks
                    SET status = 'approved', resolved_at = %s
                    WHERE task_id = %s
                    """,
                    (resolved_at, task_id),
                )

                conn.commit()

        task["status"] = "approved"
        task["resolved_at"] = resolved_at
        task["execution_result"] = execution_result

        # Write confirmation message back to the chat session
        self._send_approval_confirmation(task, execution_result, actor=user_id)

        return task

    def _execute_task_payload(self, task: Dict[str, Any], actor: str) -> Dict[str, Any]:
        """
        Execute the task payload based on task_type.

        Returns execution result dict.
        Raises exception on failure (transaction will rollback).
        """
        task_type = task.get("task_type")
        payload = task.get("payload") or {}

        if task_type == "requirement_update":
            return self._execute_requirement_update(payload, actor)
        else:
            raise ValueError(f"Unknown task_type: {task_type}")

    def _execute_requirement_update(
        self, payload: Dict[str, Any], actor: str
    ) -> Dict[str, Any]:
        """Execute a requirement_update task."""
        req_id = payload.get("req_id") or payload.get("requirement_id")
        fields = payload.get("fields") or {}
        project_id = payload.get("project_id")

        if not req_id:
            raise ValueError("payload.req_id is required")
        if not fields:
            raise ValueError("payload.fields is required")

        # Use lazy import to get service
        req_service = _get_requirements_manage_service()

        # Execute the update
        updated_req = req_service.update_requirement(
            req_id=req_id,
            fields=fields,
            updated_by=actor,
        )

        # Audit log
        try:
            req_service.add_audit_log(
                project_id=project_id or updated_req.get("project_id"),
                actor=actor,
                action="agent_update",
                target_type="requirement",
                target_id=req_id,
                detail={
                    "fields": fields,
                    "source": payload.get("source"),
                    "rationale": payload.get("rationale"),
                    "diff_preview": payload.get("diff_preview"),
                },
            )
        except Exception:
            # Avoid blocking execution on audit failures
            pass

        return {
            "action": "requirement_update",
            "requirement_id": req_id,
            "updated_fields": list(fields.keys()),
            "requirement": updated_req,
        }

    def _send_approval_confirmation(
        self, task: Dict[str, Any], execution_result: Dict[str, Any], actor: str
    ) -> None:
        """Send a confirmation message back to the chat session."""
        session_id = task.get("session_id")
        if not session_id:
            return  # No session to send to

        ai_chat = _get_ai_chat_service()
        if not ai_chat:
            return

        task_type = task.get("task_type", "")
        task_title = task.get("title", "")

        # Build confirmation message based on task type
        if task_type == "requirement_update":
            result = execution_result or {}
            req_id = result.get("requirement_id", "")
            updated_fields = result.get("updated_fields", [])
            fields_str = ", ".join(updated_fields) if updated_fields else "N/A"
            # Try to include a brief field/value summary for auditability.
            payload = task.get("payload") or {}
            diff_preview = payload.get("diff_preview") or {}
            if diff_preview and isinstance(diff_preview, dict):
                try:
                    diff_lines = []
                    for k, v in diff_preview.items():
                        before = v.get("before")
                        after = v.get("after")
                        diff_lines.append(f"- {k}: {before} -> {after}")
                    diff_block = "\n".join(diff_lines)
                except Exception:
                    diff_block = ""
            else:
                diff_block = ""
            content = (
                f"✅ **任务已批准并执行成功**\n\n"
                f"**任务:** {task_title}\n"
                f"**需求ID:** {req_id}\n"
                f"**更新字段:** {fields_str}"
            )
            if diff_block:
                content += f"\n\n**变更明细:**\n{diff_block}"
        else:
            content = f"✅ **任务已批准并执行成功**\n\n**任务:** {task_title}"

        try:
            ai_chat.create_message(
                session_id=session_id,
                user_id=task.get("user_id") or actor,  # Ensure session access passes
                role="assistant",
                content=content,
                metadata={
                    "type": "task_approval_confirmation",
                    "task_id": task.get("task_id"),
                    "task_type": task_type,
                    "execution_result": execution_result,
                },
            )
        except Exception:
            # Don't fail the approval if message sending fails
            pass

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
