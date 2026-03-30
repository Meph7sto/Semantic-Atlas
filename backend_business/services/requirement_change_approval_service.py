"""Approval-gated requirement change workflow."""

from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime
from typing import Any

from psycopg2.extras import RealDictCursor

from backend_business.config import settings
from backend_business.services.ai_chat_service import AiChatService, ai_chat_service
from backend_business.services.agent.actor.actor_runtime import AgentActorRuntime
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.db_service import db_service
from backend_business.services.push_service import PushService, push_service
from backend_business.services.requirements_manage_service import RequirementsManageService


logger = logging.getLogger(__name__)


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class RequirementChangeApprovalService:
    """Persists pending requirement updates and resolves them from mobile approval actions."""

    _MANAGE_SYNC_FIELDS = {"title", "description", "priority"}

    def __init__(
        self,
        *,
        requirements_service: RequirementsManageService | None = None,
        push_service_instance: PushService | None = None,
        chat_storage: AiChatService | None = None,
        execution_graph_service: ExecutionGraphService | None = None,
        actor_runtime: AgentActorRuntime | None = None,
    ) -> None:
        self.requirements_service = requirements_service or RequirementsManageService(
            settings.POSTGRES_DSN
        )
        self.push_service = push_service_instance or push_service
        self.chat_storage = chat_storage or ai_chat_service
        self.execution_graph_service = execution_graph_service or ExecutionGraphService(
            settings.POSTGRES_DSN
        )
        self.actor_runtime = actor_runtime or AgentActorRuntime(
            query_source="requirement_agent_chat",
            loop_thread_name="requirement-approval-actor-loop",
        )

    def create_approval_request(
        self,
        *,
        project_id: str,
        requirement_id: str,
        requested_by: str,
        updates: dict[str, Any],
        session_id: str | None,
        graph_id: str | None,
        source_agent: str = "requirement_agent",
    ) -> dict[str, Any]:
        requirement = self.requirements_service.get_requirement(requirement_id)
        if not requirement or requirement.get("deleted"):
            raise ValueError("目标需求不存在或已删除")
        if requirement.get("project_id") != project_id:
            raise ValueError("目标需求不属于当前项目")
        if not updates:
            raise ValueError("updates 不能为空")

        summary_text = self._build_summary_text(requirement=requirement, updates=updates)
        existing = self._find_reusable_approval_request(
            project_id=project_id,
            requirement_id=requirement_id,
            requested_by=requested_by,
            updates=updates,
            session_id=session_id,
            graph_id=graph_id,
            source_agent=source_agent,
        )
        if existing:
            ensured_push_message_id = self._ensure_push_message_for_approval(
                approval=existing,
                requirement=requirement,
                summary_text=summary_text,
                session_id=session_id,
                graph_id=graph_id,
                source_agent=source_agent,
                updates=updates,
            )
            return {
                "approval_request_id": existing["approval_request_id"],
                "status": existing.get("status") or "pending",
                "project_id": project_id,
                "session_id": session_id,
                "graph_id": graph_id,
                "requirement_id": requirement_id,
                "requested_by": requested_by,
                "updates": dict(updates),
                "summary_text": summary_text,
                "push_message_id": ensured_push_message_id,
                "created_at": existing.get("created_at"),
            }

        approval_request_id = f"apr_{uuid.uuid4().hex[:12]}"
        created_at = _utc_now_iso()

        try:
            with db_service._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        INSERT INTO requirement_change_approvals (
                            approval_request_id, project_id, session_id, graph_id, requirement_id,
                            requested_by, source_agent, approval_type, status, updates_json,
                            summary_text, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, 'requirement_update', 'pending', %s::jsonb, %s, %s::timestamptz)
                        """,
                        (
                            approval_request_id,
                            project_id,
                            session_id,
                            graph_id,
                            requirement_id,
                            requested_by,
                            source_agent,
                            json.dumps(updates, ensure_ascii=False),
                            summary_text,
                            created_at,
                        ),
                    )
        except Exception as exc:
            logger.exception(
                "创建需求变更审批记录失败 approval_request_id=%s requirement_id=%s project_id=%s",
                approval_request_id,
                requirement_id,
                project_id,
            )
            raise RuntimeError(
                "审批记录写入失败，请检查数据库连接以及 requirement_change_approvals 表是否已初始化。"
            ) from exc

        push_message_id = self._ensure_push_message_for_approval(
            approval={
                "approval_request_id": approval_request_id,
                "push_message_id": None,
            },
            requirement=requirement,
            summary_text=summary_text,
            session_id=session_id,
            graph_id=graph_id,
            source_agent=source_agent,
            updates=updates,
        )

        if graph_id:
            try:
                self.execution_graph_service.patch_graph_meta(
                    graph_id,
                    {
                        "approval_request_id": approval_request_id,
                        "approval_push_message_id": push_message_id,
                        "approval_status": "pending",
                        "approval_summary": summary_text,
                    },
                    updated_by=requested_by,
                )
            except Exception:
                pass

        return {
            "approval_request_id": approval_request_id,
            "status": "pending",
            "project_id": project_id,
            "session_id": session_id,
            "graph_id": graph_id,
            "requirement_id": requirement_id,
            "requested_by": requested_by,
            "updates": dict(updates),
            "summary_text": summary_text,
            "push_message_id": push_message_id,
            "created_at": created_at,
        }

    def get_approval_by_push_message(self, push_message_id: str) -> dict[str, Any] | None:
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT approval_request_id, project_id, session_id, graph_id, requirement_id,
                           requested_by, source_agent, approval_type, status, updates_json,
                           summary_text, push_message_id, approved_by, rejected_by,
                           decision_comment, created_at::text AS created_at,
                           resolved_at::text AS resolved_at, applied_at::text AS applied_at
                    FROM requirement_change_approvals
                    WHERE push_message_id = %s
                    """,
                    (push_message_id,),
                )
                row = cur.fetchone()
        return self._normalize_row(row)

    def approve_from_push_message(
        self,
        *,
        push_message_id: str,
        approved_by: str,
    ) -> dict[str, Any]:
        approval = self.get_approval_by_push_message(push_message_id)
        if not approval:
            raise ValueError("审批请求不存在")
        if approval["status"] == "rejected":
            raise ValueError("该审批请求已被驳回")
        if approval["status"] == "applied":
            return {
                **approval,
                "write_result": None,
                "already_processed": True,
            }

        resolved_at = _utc_now_iso()
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE requirement_change_approvals
                    SET status = 'approved', approved_by = %s, resolved_at = %s::timestamptz
                    WHERE approval_request_id = %s AND status = 'pending'
                    """,
                    (approved_by, resolved_at, approval["approval_request_id"]),
                )

        write_result = self._apply_approved_change(approval, approved_by=approved_by)
        updated = self.get_approval_by_push_message(push_message_id) or approval
        return {
            **updated,
            "write_result": write_result,
            "already_processed": False,
        }

    def reject_from_push_message(
        self,
        *,
        push_message_id: str,
        rejected_by: str,
    ) -> dict[str, Any]:
        approval = self.get_approval_by_push_message(push_message_id)
        if not approval:
            raise ValueError("审批请求不存在")
        if approval["status"] == "applied":
            raise ValueError("该审批请求已执行，无法驳回")
        if approval["status"] == "rejected":
            return {**approval, "already_processed": True}

        resolved_at = _utc_now_iso()
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE requirement_change_approvals
                    SET status = 'rejected', rejected_by = %s, resolved_at = %s::timestamptz
                    WHERE approval_request_id = %s AND status IN ('pending', 'approved')
                    """,
                    (rejected_by, resolved_at, approval["approval_request_id"]),
                )

        self.push_service.mark_read(push_message_id)
        reply_text = (
            f"你在移动端驳回了需求 {approval['requirement_id']} 的修改申请，系统未执行此次变更。"
        )
        self._notify_resolution(
            approval=approval,
            resolution_status="rejected",
            reply_text=reply_text,
        )
        updated = self.get_approval_by_push_message(push_message_id) or approval
        return {**updated, "already_processed": False}

    def _apply_approved_change(
        self,
        approval: dict[str, Any],
        *,
        approved_by: str,
    ) -> dict[str, Any]:
        actor_manager = self.actor_runtime.get_actor_manager()
        command = {
            "type": "UpdateRequirementContent",
            "updates": approval["updates_json"] or {},
            "metadata": {
                "graph_id": approval.get("graph_id"),
                "session_id": approval.get("session_id"),
                "approval_request_id": approval["approval_request_id"],
                "approved_by": approved_by,
                "source": "requirement_change_approval",
            },
            "source": approval.get("requested_by") or "requirement_change_approval",
        }
        write_result = self.actor_runtime.actor_write(
            actor_manager,
            approval["requirement_id"],
            command,
        )
        if write_result.get("status") != "success":
            raise ValueError("审批通过后写入需求失败")

        self._sync_manage_requirement(
            requirement_id=approval["requirement_id"],
            updates=approval["updates_json"] or {},
            updated_by=approved_by,
        )

        state_result = self.actor_runtime.actor_query(actor_manager, approval["requirement_id"])
        if state_result.get("status") != "success":
            raise ValueError("审批通过后读取需求状态失败")

        state = state_result.get("state") or {}
        content = state.get("content") or {}
        applied_at = _utc_now_iso()
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE requirement_change_approvals
                    SET status = 'applied', applied_at = %s::timestamptz
                    WHERE approval_request_id = %s
                    """,
                    (applied_at, approval["approval_request_id"]),
                )

        self.push_service.mark_read(approval["push_message_id"])
        reply_text = (
            f"你已在移动端同意需求 {approval['requirement_id']} 的修改申请，变更现已生效。"
        )
        self._notify_resolution(
            approval=approval,
            resolution_status="applied",
            reply_text=reply_text,
        )
        return {
            "write_status": write_result.get("status"),
            "event_id": write_result.get("event_id"),
            "requirement_id": state.get("requirement_id"),
            "version": state.get("version"),
            "status": state.get("status"),
            "priority": state.get("priority"),
            "title": content.get("title"),
            "description": content.get("description"),
            "acceptance_criteria": content.get("acceptance_criteria"),
            "applied_updates": approval["updates_json"] or {},
        }

    def _find_reusable_approval_request(
        self,
        *,
        project_id: str,
        requirement_id: str,
        requested_by: str,
        updates: dict[str, Any],
        session_id: str | None,
        graph_id: str | None,
        source_agent: str,
    ) -> dict[str, Any] | None:
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT approval_request_id, project_id, session_id, graph_id, requirement_id,
                           requested_by, source_agent, approval_type, status, updates_json,
                           summary_text, push_message_id, approved_by, rejected_by,
                           decision_comment, created_at::text AS created_at,
                           resolved_at::text AS resolved_at, applied_at::text AS applied_at
                    FROM requirement_change_approvals
                    WHERE project_id = %s
                      AND requirement_id = %s
                      AND requested_by = %s
                      AND source_agent = %s
                      AND status IN ('pending', 'approved')
                      AND session_id IS NOT DISTINCT FROM %s
                      AND graph_id IS NOT DISTINCT FROM %s
                      AND updates_json = %s::jsonb
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (
                        project_id,
                        requirement_id,
                        requested_by,
                        source_agent,
                        session_id,
                        graph_id,
                        json.dumps(updates, ensure_ascii=False),
                    ),
                )
                row = cur.fetchone()
        return self._normalize_row(row)

    def _ensure_push_message_for_approval(
        self,
        *,
        approval: dict[str, Any],
        requirement: dict[str, Any],
        summary_text: str,
        session_id: str | None,
        graph_id: str | None,
        source_agent: str,
        updates: dict[str, Any],
    ) -> str:
        existing_push_message_id = str(approval.get("push_message_id") or "").strip()
        if existing_push_message_id and self.push_service.get_message(existing_push_message_id):
            return existing_push_message_id

        approval_request_id = approval["approval_request_id"]
        requirement_id = str(requirement.get("req_id") or approval.get("requirement_id") or "").strip()
        try:
            message = self.push_service.create_message(
                message_type="change",
                title=f"需求变更待审批: {requirement.get('title') or requirement_id}",
                content=summary_text,
                source=source_agent,
                priority="high" if "priority" in updates else "medium",
                ai_suggestion="请在移动端确认后再应用需求修改",
                metadata={
                    "approval_request_id": approval_request_id,
                    "approval_type": "requirement_update",
                    "session_id": session_id or "",
                    "graph_id": graph_id or "",
                    "requirement_id": requirement_id,
                    "proposed_changes_summary": summary_text,
                },
            )
            self.push_service.push_message(message["message_id"])
        except Exception as exc:
            logger.exception(
                "创建或推送需求变更审批通知失败 approval_request_id=%s requirement_id=%s",
                approval_request_id,
                requirement_id,
            )
            raise RuntimeError(
                "审批通知推送失败，请检查 push_messages 表和消息推送服务状态。"
            ) from exc

        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE requirement_change_approvals
                    SET push_message_id = %s
                    WHERE approval_request_id = %s
                    """,
                    (message["message_id"], approval_request_id),
                )

        return message["message_id"]

    def _sync_manage_requirement(
        self,
        *,
        requirement_id: str,
        updates: dict[str, Any],
        updated_by: str,
    ) -> None:
        manage_updates = {
            key: value
            for key, value in (updates or {}).items()
            if key in self._MANAGE_SYNC_FIELDS and value is not None
        }
        if not manage_updates:
            return
        self.requirements_service.update_requirement(
            requirement_id,
            manage_updates,
            updated_by=updated_by,
        )

    def _notify_resolution(
        self,
        *,
        approval: dict[str, Any],
        resolution_status: str,
        reply_text: str,
    ) -> None:
        graph_id = approval.get("graph_id")
        if graph_id:
            try:
                self.execution_graph_service.patch_graph_meta(
                    graph_id,
                    {
                        "approval_request_id": approval["approval_request_id"],
                        "approval_push_message_id": approval.get("push_message_id"),
                        "approval_status": resolution_status,
                        "final_reply": reply_text,
                    },
                    status="succeeded",
                    updated_by=approval.get("requested_by") or "",
                )
            except Exception:
                pass

        session_id = approval.get("session_id")
        if not session_id or not self.chat_storage:
            return

        self.chat_storage.create_message(
            session_id=session_id,
            user_id=None,
            role="assistant",
            content=reply_text,
            metadata={
                "approval_request_id": approval["approval_request_id"],
                "approval_status": resolution_status,
                "push_message_id": approval.get("push_message_id"),
                "requirement_id": approval.get("requirement_id"),
            },
            is_read=False,
        )

    @staticmethod
    def _build_summary_text(
        *,
        requirement: dict[str, Any],
        updates: dict[str, Any],
    ) -> str:
        parts = [
            f"需求: {requirement.get('title') or requirement.get('req_id')}",
        ]
        for key, value in updates.items():
            if key == "priority":
                old_value = requirement.get("priority") or "-"
                parts.append(f"优先级 {old_value} -> {value}")
            elif key == "title":
                old_value = requirement.get("title") or "-"
                parts.append(f"标题 {old_value} -> {value}")
            else:
                parts.append(f"{key} 已申请更新")
        return "；".join(parts)

    @staticmethod
    def _normalize_row(row: dict[str, Any] | None) -> dict[str, Any] | None:
        if not row:
            return None
        item = dict(row)
        updates = item.get("updates_json")
        if isinstance(updates, str):
            try:
                item["updates_json"] = json.loads(updates)
            except Exception:
                item["updates_json"] = {}
        return item


requirement_change_approval_service = RequirementChangeApprovalService()
