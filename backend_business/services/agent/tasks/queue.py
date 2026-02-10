"""Task queue - persistence for tasks awaiting human approval.
任务队列 - 待人工批准任务的持久化。
"""

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor

from backend_business.services.db_service import db_service

logger = logging.getLogger(__name__)


def _parse_payload(task: Dict[str, Any]) -> Dict[str, Any]:
    """Helper to parse JSONB payload if needed.
    如果需要，解析 JSONB 载荷的辅助函数。
    """
    if isinstance(task.get("payload"), str):
        try:
            task["payload"] = json.loads(task["payload"])
        except Exception:
            task["payload"] = {}
    return task


class AgentTaskQueue:
    """Manages the lifecycle of agent-created tasks.
    管理 Agent 创建的任务的生命周期。
    """

    # ========================
    # Write
    # 写入
    # ========================

    def create_task(
        self,
        user_id: str,
        task_type: str,
        title: str,
        description: str,
        payload: Dict[str, Any],
        session_id: Optional[str] = None,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new pending task.
        创建一个新的待处理任务。
        """
        task_id = f"task_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc)

        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO agent_pending_tasks (
                        task_id, user_id, task_type, title, description,
                        payload, status, session_id, project_id, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'pending', %s, %s, %s)
                    """,
                    (
                        task_id,
                        user_id,
                        task_type,
                        title,
                        description,
                        json.dumps(payload),
                        session_id,
                        project_id,
                        created_at,
                    ),
                )
        return {
            "task_id": task_id,
            "status": "pending",
            "title": title,
            "description": description,
        }

    # ========================
    # Read
    # 读取
    # ========================

    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """Get a task by ID.
        根据 ID 获取任务。
        """
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
        """List pending tasks for a user (and optionally project).
        列出用户的待处理任务（可选项目过滤）。
        """
        return self._list_tasks(user_id, project_id=project_id, status="pending", limit=limit)

    def list_all_tasks(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List all tasks with optional filters.
        列出所有任务（可选过滤器）。
        """
        return self._list_tasks(user_id, project_id=project_id, status=status, limit=limit)

    def get_pending_count(
        self,
        user_id: str,
        project_id: Optional[str] = None,
    ) -> int:
        """Get the count of pending tasks.
        获取待处理任务的数量。
        """
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
    # 批准 / 拒绝
    # ========================

    def approve_task(self, task_id: str, user_id: str) -> Dict[str, Any]:
        """Approve and execute a pending task.
        批准并执行待处理任务。

        Uses SELECT FOR UPDATE to prevent concurrent approvals/rejections.
        Task execution and final status transition happen in one DB transaction.
        使用 SELECT FOR UPDATE 防止并发批准/拒绝。
        任务执行和最终状态转换在一个 DB 事务中发生。
        """
        # Lazy import avoids circular dependency at module load time
        # 延迟导入以避免模块加载时的循环依赖
        from backend_business.services.agent.tasks.executor import task_executor_registry

        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Lock the row
                # 锁定行
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

                # Execute logic
                # 执行逻辑
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

        # Notify user in chat
        # 在聊天中通知用户
        self._send_confirmation(task, execution_result)
        return task

    def reject_task(self, task_id: str, user_id: str) -> Dict[str, Any]:
        """Reject a pending task.
        拒绝待处理任务。
        """
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
    # 维护
    # ========================

    def expire_old_tasks(self, hours: int = 24) -> int:
        """Mark tasks older than *hours* as expired.
        将超过 *hours* 小时的任务标记为已过期。
        """
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
    # 内部辅助函数
    # ========================

    def _list_tasks(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """Internal helper to query tasks.
        查询任务的内部辅助函数。
        """
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
        """Send a confirmation message back to the originating chat session.
        将确认消息发送回发起的聊天会话。
        """
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
            pass  # confirmation failure must not break the approval response; 确认失败不应破坏批准响应


# Global singleton
# 全局单例
agent_task_queue = AgentTaskQueue() if db_service else None
