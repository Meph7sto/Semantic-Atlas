"""
变更请求管理 Mixin
"""

from typing import Dict, List, Optional


# 变更请求状态常量
CHANGE_STATUS_PENDING = "PENDING"
CHANGE_STATUS_APPROVED = "APPROVED"
CHANGE_STATUS_REJECTED = "REJECTED"

ALL_CHANGE_STATUSES = [CHANGE_STATUS_PENDING, CHANGE_STATUS_APPROVED, CHANGE_STATUS_REJECTED]


class ChangeRequestsMixin:
    """变更请求相关的数据库操作 Mixin"""

    def create_change_request(
        self,
        requirement_id: str,
        baseline_id: int,
        requested_by: str,
        reason: str,
        change_summary: str,
    ) -> Optional[Dict]:
        """
        创建变更请求

        Args:
            requirement_id: 需求 ID
            baseline_id: 基线 ID
            requested_by: 申请人用户 ID
            reason: 变更原因
            change_summary: 变更摘要

        Returns:
            创建的变更请求信息，失败返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO change_requests
                    (requirement_id, baseline_id, requested_by, reason, change_summary, status, created_at)
                    VALUES (%s, %s, %s, %s, %s, 'PENDING', NOW())
                    RETURNING id, requirement_id, baseline_id, requested_by, reason, change_summary, status, created_at
                    """,
                    (requirement_id, baseline_id, requested_by, reason, change_summary),
                )
                row = cur.fetchone()
                conn.commit()

        return {
            "id": row[0],
            "requirement_id": row[1],
            "baseline_id": row[2],
            "requested_by": row[3],
            "reason": row[4],
            "change_summary": row[5],
            "status": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
        }

    def approve_change_request(
        self,
        request_id: int,
        reviewed_by: str,
        review_comment: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        批准变更请求

        Args:
            request_id: 变更请求 ID
            reviewed_by: 审批人用户 ID
            review_comment: 审批意见

        Returns:
            更新后的变更请求信息，失败返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE change_requests
                    SET status = 'APPROVED', reviewed_by = %s, review_comment = %s, resolved_at = NOW()
                    WHERE id = %s AND status = 'PENDING'
                    RETURNING id, requirement_id, baseline_id, requested_by, reason, change_summary,
                              status, reviewed_by, review_comment, created_at, resolved_at
                    """,
                    (reviewed_by, review_comment, request_id),
                )
                row = cur.fetchone()
                conn.commit()

        if not row:
            return None

        return {
            "id": row[0],
            "requirement_id": row[1],
            "baseline_id": row[2],
            "requested_by": row[3],
            "reason": row[4],
            "change_summary": row[5],
            "status": row[6],
            "reviewed_by": row[7],
            "review_comment": row[8],
            "created_at": row[9].isoformat() if row[9] else None,
            "resolved_at": row[10].isoformat() if row[10] else None,
        }

    def reject_change_request(
        self,
        request_id: int,
        reviewed_by: str,
        review_comment: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        驳回变更请求

        Args:
            request_id: 变更请求 ID
            reviewed_by: 审批人用户 ID
            review_comment: 驳回原因

        Returns:
            更新后的变更请求信息，失败返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE change_requests
                    SET status = 'REJECTED', reviewed_by = %s, review_comment = %s, resolved_at = NOW()
                    WHERE id = %s AND status = 'PENDING'
                    RETURNING id, requirement_id, baseline_id, requested_by, reason, change_summary,
                              status, reviewed_by, review_comment, created_at, resolved_at
                    """,
                    (reviewed_by, review_comment, request_id),
                )
                row = cur.fetchone()
                conn.commit()

        if not row:
            return None

        return {
            "id": row[0],
            "requirement_id": row[1],
            "baseline_id": row[2],
            "requested_by": row[3],
            "reason": row[4],
            "change_summary": row[5],
            "status": row[6],
            "reviewed_by": row[7],
            "review_comment": row[8],
            "created_at": row[9].isoformat() if row[9] else None,
            "resolved_at": row[10].isoformat() if row[10] else None,
        }

    def list_requirement_change_requests(
        self,
        requirement_id: str,
        status: Optional[str] = None,
    ) -> List[Dict]:
        """
        列出需求的所有变更请求

        Args:
            requirement_id: 需求 ID
            status: 筛选状态（可选）

        Returns:
            变更请求列表
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute(
                        """
                        SELECT
                            cr.id, cr.requirement_id, cr.baseline_id, cr.requested_by,
                            cr.reason, cr.change_summary, cr.status, cr.reviewed_by,
                            cr.review_comment, cr.created_at, cr.resolved_at,
                            ru.username, ru.display_name,
                            au.username as reviewer_username, au.display_name as reviewer_display_name,
                            b.version as baseline_version
                        FROM change_requests cr
                        LEFT JOIN auth_users ru ON cr.requested_by = ru.user_id
                        LEFT JOIN auth_users au ON cr.reviewed_by = au.user_id
                        LEFT JOIN baselines b ON cr.baseline_id = b.id
                        WHERE cr.requirement_id = %s AND cr.status = %s
                        ORDER BY cr.created_at DESC
                        """,
                        (requirement_id, status),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            cr.id, cr.requirement_id, cr.baseline_id, cr.requested_by,
                            cr.reason, cr.change_summary, cr.status, cr.reviewed_by,
                            cr.review_comment, cr.created_at, cr.resolved_at,
                            ru.username, ru.display_name,
                            au.username as reviewer_username, au.display_name as reviewer_display_name,
                            b.version as baseline_version
                        FROM change_requests cr
                        LEFT JOIN auth_users ru ON cr.requested_by = ru.user_id
                        LEFT JOIN auth_users au ON cr.reviewed_by = au.user_id
                        LEFT JOIN baselines b ON cr.baseline_id = b.id
                        WHERE cr.requirement_id = %s
                        ORDER BY cr.created_at DESC
                        """,
                        (requirement_id,),
                    )
                rows = cur.fetchall()

        return [
            {
                "id": row[0],
                "requirement_id": row[1],
                "baseline_id": row[2],
                "requested_by": row[3],
                "reason": row[4],
                "change_summary": row[5],
                "status": row[6],
                "reviewed_by": row[7],
                "review_comment": row[8],
                "created_at": row[9].isoformat() if row[9] else None,
                "resolved_at": row[10].isoformat() if row[10] else None,
                "requester_username": row[11],
                "requester_display_name": row[12],
                "reviewer_username": row[13],
                "reviewer_display_name": row[14],
                "baseline_version": row[15],
            }
            for row in rows
        ]

    def get_pending_change_requests(
        self,
        project_id: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        获取待审批的变更请求

        Args:
            project_id: 项目 ID（可选，用于筛选）
            user_id: 用户 ID（可选，用于筛选申请人）

        Returns:
            待审批变更请求列表
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if project_id and user_id:
                    cur.execute(
                        """
                        SELECT
                            cr.id, cr.requirement_id, cr.baseline_id, cr.requested_by,
                            cr.reason, cr.change_summary, cr.status, cr.created_at,
                            req.title as requirement_title, req.project_id,
                            ru.username, ru.display_name,
                            b.version as baseline_version
                        FROM change_requests cr
                        JOIN manage_requirements req ON cr.requirement_id = req.req_id
                        LEFT JOIN auth_users ru ON cr.requested_by = ru.user_id
                        LEFT JOIN baselines b ON cr.baseline_id = b.id
                        WHERE cr.status = 'PENDING' AND req.project_id = %s AND cr.requested_by = %s
                        ORDER BY cr.created_at DESC
                        """,
                        (project_id, user_id),
                    )
                elif project_id:
                    cur.execute(
                        """
                        SELECT
                            cr.id, cr.requirement_id, cr.baseline_id, cr.requested_by,
                            cr.reason, cr.change_summary, cr.status, cr.created_at,
                            req.title as requirement_title, req.project_id,
                            ru.username, ru.display_name,
                            b.version as baseline_version
                        FROM change_requests cr
                        JOIN manage_requirements req ON cr.requirement_id = req.req_id
                        LEFT JOIN auth_users ru ON cr.requested_by = ru.user_id
                        LEFT JOIN baselines b ON cr.baseline_id = b.id
                        WHERE cr.status = 'PENDING' AND req.project_id = %s
                        ORDER BY cr.created_at DESC
                        """,
                        (project_id,),
                    )
                elif user_id:
                    cur.execute(
                        """
                        SELECT
                            cr.id, cr.requirement_id, cr.baseline_id, cr.requested_by,
                            cr.reason, cr.change_summary, cr.status, cr.created_at,
                            req.title as requirement_title, req.project_id,
                            ru.username, ru.display_name,
                            b.version as baseline_version
                        FROM change_requests cr
                        JOIN manage_requirements req ON cr.requirement_id = req.req_id
                        LEFT JOIN auth_users ru ON cr.requested_by = ru.user_id
                        LEFT JOIN baselines b ON cr.baseline_id = b.id
                        WHERE cr.status = 'PENDING' AND cr.requested_by = %s
                        ORDER BY cr.created_at DESC
                        """,
                        (user_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            cr.id, cr.requirement_id, cr.baseline_id, cr.requested_by,
                            cr.reason, cr.change_summary, cr.status, cr.created_at,
                            req.title as requirement_title, req.project_id,
                            ru.username, ru.display_name,
                            b.version as baseline_version
                        FROM change_requests cr
                        JOIN manage_requirements req ON cr.requirement_id = req.req_id
                        LEFT JOIN auth_users ru ON cr.requested_by = ru.user_id
                        LEFT JOIN baselines b ON cr.baseline_id = b.id
                        WHERE cr.status = 'PENDING'
                        ORDER BY cr.created_at DESC
                        """,
                    )
                rows = cur.fetchall()

        return [
            {
                "id": row[0],
                "requirement_id": row[1],
                "baseline_id": row[2],
                "requested_by": row[3],
                "reason": row[4],
                "change_summary": row[5],
                "status": row[6],
                "created_at": row[7].isoformat() if row[7] else None,
                "requirement_title": row[8],
                "project_id": row[9],
                "requester_username": row[10],
                "requester_display_name": row[11],
                "baseline_version": row[12],
            }
            for row in rows
        ]

    def get_change_request(
        self,
        request_id: int,
    ) -> Optional[Dict]:
        """
        获取变更请求详情

        Args:
            request_id: 变更请求 ID

        Returns:
            变更请求信息，不存在返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        cr.id, cr.requirement_id, cr.baseline_id, cr.requested_by,
                        cr.reason, cr.change_summary, cr.status, cr.reviewed_by,
                        cr.review_comment, cr.created_at, cr.resolved_at,
                        req.title as requirement_title, req.project_id,
                        ru.username, ru.display_name,
                        au.username as reviewer_username, au.display_name as reviewer_display_name,
                        b.version as baseline_version
                    FROM change_requests cr
                    JOIN manage_requirements req ON cr.requirement_id = req.req_id
                    LEFT JOIN auth_users ru ON cr.requested_by = ru.user_id
                    LEFT JOIN auth_users au ON cr.reviewed_by = au.user_id
                    LEFT JOIN baselines b ON cr.baseline_id = b.id
                    WHERE cr.id = %s
                    """,
                    (request_id,),
                )
                row = cur.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "requirement_id": row[1],
            "baseline_id": row[2],
            "requested_by": row[3],
            "reason": row[4],
            "change_summary": row[5],
            "status": row[6],
            "reviewed_by": row[7],
            "review_comment": row[8],
            "created_at": row[9].isoformat() if row[9] else None,
            "resolved_at": row[10].isoformat() if row[10] else None,
            "requirement_title": row[11],
            "project_id": row[12],
            "requester_username": row[13],
            "requester_display_name": row[14],
            "reviewer_username": row[15],
            "reviewer_display_name": row[16],
            "baseline_version": row[17],
        }

    def has_recent_approved_change_request(
        self,
        requirement_id: str,
        hours: int = 24,
    ) -> bool:
        """
        检查需求是否有最近批准的变更请求

        Args:
            requirement_id: 需求 ID
            hours: 时间范围（小时）

        Returns:
            是否有最近批准的变更请求
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*)
                    FROM change_requests
                    WHERE requirement_id = %s
                      AND status = 'APPROVED'
                      AND resolved_at >= NOW() - INTERVAL '%s hours'
                    """,
                    (requirement_id, hours),
                )
                count = cur.fetchone()[0]

        return count > 0

    def get_baseline_change_requests(
        self,
        baseline_id: int,
        status: Optional[str] = None,
    ) -> List[Dict]:
        """
        获取基线的所有变更请求

        Args:
            baseline_id: 基线 ID
            status: 筛选状态（可选）

        Returns:
            变更请求列表
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute(
                        """
                        SELECT
                            cr.id, cr.requirement_id, cr.baseline_id, cr.requested_by,
                            cr.reason, cr.change_summary, cr.status, cr.reviewed_by,
                            cr.review_comment, cr.created_at, cr.resolved_at,
                            req.title as requirement_title,
                            ru.username, ru.display_name,
                            b.version as baseline_version
                        FROM change_requests cr
                        JOIN manage_requirements req ON cr.requirement_id = req.req_id
                        LEFT JOIN auth_users ru ON cr.requested_by = ru.user_id
                        LEFT JOIN baselines b ON cr.baseline_id = b.id
                        WHERE cr.baseline_id = %s AND cr.status = %s
                        ORDER BY cr.created_at DESC
                        """,
                        (baseline_id, status),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            cr.id, cr.requirement_id, cr.baseline_id, cr.requested_by,
                            cr.reason, cr.change_summary, cr.status, cr.reviewed_by,
                            cr.review_comment, cr.created_at, cr.resolved_at,
                            req.title as requirement_title,
                            ru.username, ru.display_name,
                            b.version as baseline_version
                        FROM change_requests cr
                        JOIN manage_requirements req ON cr.requirement_id = req.req_id
                        LEFT JOIN auth_users ru ON cr.requested_by = ru.user_id
                        LEFT JOIN baselines b ON cr.baseline_id = b.id
                        WHERE cr.baseline_id = %s
                        ORDER BY cr.created_at DESC
                        """,
                        (baseline_id,),
                    )
                rows = cur.fetchall()

        return [
            {
                "id": row[0],
                "requirement_id": row[1],
                "baseline_id": row[2],
                "requested_by": row[3],
                "reason": row[4],
                "change_summary": row[5],
                "status": row[6],
                "reviewed_by": row[7],
                "review_comment": row[8],
                "created_at": row[9].isoformat() if row[9] else None,
                "resolved_at": row[10].isoformat() if row[10] else None,
                "requirement_title": row[11],
                "requester_username": row[12],
                "requester_display_name": row[13],
                "baseline_version": row[14],
            }
            for row in rows
        ]
