"""Executor for requirement_update tasks."""

import json
import uuid
from typing import Any, Dict, Optional

from psycopg2.extras import RealDictCursor

from backend_business.services.agent.tasks.executors.base import BaseTaskExecutor


class RequirementUpdateExecutor(BaseTaskExecutor):
    task_type = "requirement_update"

    def execute(
        self,
        payload: Dict[str, Any],
        actor: str,
        conn: Optional[Any] = None,
    ) -> Dict[str, Any]:
        req_id = payload.get("req_id") or payload.get("requirement_id")
        fields = payload.get("fields") or {}
        project_id = payload.get("project_id")

        if not req_id:
            raise ValueError("payload.req_id is required")
        if not fields:
            raise ValueError("payload.fields is required")

        if conn is not None:
            updated_req = self._update_requirement_with_conn(
                conn=conn,
                req_id=req_id,
                fields=fields,
                updated_by=actor,
            )
            try:
                self._add_audit_log_with_conn(
                    conn=conn,
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
                pass  # audit failures must not block execution
        else:
            svc = self._req_service()
            updated_req = svc.update_requirement(
                req_id=req_id,
                fields=fields,
                updated_by=actor,
            )
            try:
                svc.add_audit_log(
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
                pass  # audit failures must not block execution

        return {
            "action": "requirement_update",
            "requirement_id": req_id,
            "updated_fields": list(fields.keys()),
            "requirement": updated_req,
        }

    def confirmation_message(self, task: Dict[str, Any], result: Dict[str, Any]) -> str:
        task_title = task.get("title", "")
        req_id = result.get("requirement_id", "")
        updated_fields = result.get("updated_fields", [])
        fields_str = ", ".join(updated_fields) if updated_fields else "N/A"

        payload = task.get("payload") or {}
        diff_preview = payload.get("diff_preview") or {}
        diff_block = ""
        if diff_preview and isinstance(diff_preview, dict):
            try:
                lines = [
                    f"- {k}: {v.get('before')} -> {v.get('after')}"
                    for k, v in diff_preview.items()
                ]
                diff_block = "\n".join(lines)
            except Exception:
                pass

        content = (
            f"✅ **任务已批准并执行成功**\n\n"
            f"**任务:** {task_title}\n"
            f"**需求ID:** {req_id}\n"
            f"**更新字段:** {fields_str}"
        )
        if diff_block:
            content += f"\n\n**变更明细:**\n{diff_block}"
        return content

    @staticmethod
    def _req_service():
        from backend_business.services.requirements_manage_service import (
            RequirementsManageService,
        )
        from backend_business.config import settings

        return RequirementsManageService(settings.POSTGRES_DSN)

    @staticmethod
    def _update_requirement_with_conn(
        conn: Any,
        req_id: str,
        fields: Dict[str, Any],
        updated_by: str,
    ) -> Dict[str, Any]:
        allowed = {
            "title",
            "description",
            "status",
            "priority",
            "assignee",
            "tags",
            "due_date",
            "custom_fields",
            "order_index",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            raise ValueError("没有可更新字段")

        set_clauses = []
        values = []
        for key, value in updates.items():
            if key in {"tags", "custom_fields"}:
                set_clauses.append(f"{key} = %s::jsonb")
                values.append(
                    json.dumps(value or ({} if key == "custom_fields" else []))
                )
            else:
                set_clauses.append(f"{key} = %s")
                values.append(value)

        set_clauses.append("updated_by = %s")
        values.append(updated_by)
        set_clauses.append("updated_at = NOW()")
        values.append(req_id)

        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(
                f"""
                UPDATE manage_requirements
                SET {", ".join(set_clauses)}
                WHERE req_id = %s
                RETURNING req_id, project_id, requirement_type, status, title, description,
                          priority, assignee, tags, due_date, parent_id, order_index,
                          source_req_id, source_level, custom_fields, created_by,
                          created_at::text AS created_at, updated_by, updated_at::text AS updated_at, deleted, is_planned
                """,
                values,
            )
            row = cur.fetchone()
            if not row:
                raise ValueError("需求不存在")
            return dict(row)

    @staticmethod
    def _add_audit_log_with_conn(
        conn: Any,
        project_id: Optional[str],
        actor: str,
        action: str,
        target_type: str,
        target_id: str,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        log_id = str(uuid.uuid4())
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO manage_audit_logs (
                    log_id, project_id, product_id, actor, action, target_type, target_id, detail, created_at
                )
                VALUES (%s, %s, NULL, %s, %s, %s, %s, %s::jsonb, NOW())
                """,
                (
                    log_id,
                    project_id,
                    actor,
                    action,
                    target_type,
                    target_id,
                    json.dumps(detail or {}),
                ),
            )
