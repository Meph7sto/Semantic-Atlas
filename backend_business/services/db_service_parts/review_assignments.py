"""
评审指派管理 Mixin
"""

from typing import Dict, List, Optional


# 评审指派状态常量
REVIEW_STATUS_PENDING = "PENDING"
REVIEW_STATUS_APPROVED = "APPROVED"
REVIEW_STATUS_REJECTED = "REJECTED"
REVIEW_STATUS_WITHDRAWN = "WITHDRAWN"

ALL_REVIEW_STATUSES = [REVIEW_STATUS_PENDING, REVIEW_STATUS_APPROVED, REVIEW_STATUS_REJECTED, REVIEW_STATUS_WITHDRAWN]


class ReviewAssignmentsMixin:
    """评审指派相关的数据库操作 Mixin"""

    def create_review_assignment(
        self,
        requirement_id: str,
        reviewer_id: str,
        initiated_by: str,
        seq: int = 1,
        comment: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        创建评审指派

        Args:
            requirement_id: 需求 ID
            reviewer_id: 评审人用户 ID
            initiated_by: 发起人用户 ID
            seq: 序号（用于多轮评审）
            comment: 初始评论

        Returns:
            创建的评审指派信息，失败返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO review_assignments (requirement_id, reviewer_id, initiated_by, seq, comment, created_at)
                    VALUES (%s, %s, %s, %s, %s, NOW())
                    RETURNING id, requirement_id, reviewer_id, initiated_by, seq, status, comment, created_at
                    """,
                    (requirement_id, reviewer_id, initiated_by, seq, comment),
                )
                row = cur.fetchone()
                conn.commit()

        return {
            "id": row[0],
            "requirement_id": row[1],
            "reviewer_id": row[2],
            "initiated_by": row[3],
            "seq": row[4],
            "status": row[5],
            "comment": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
        }

    def approve_review(
        self,
        assignment_id: int,
        reviewer_id: str,
        comment: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        通过评审

        Args:
            assignment_id: 评审指派 ID
            reviewer_id: 评审人用户 ID
            comment: 审批意见

        Returns:
            更新后的评审指派信息，失败返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 先检查是否由正确的评审人操作且状态为 PENDING
                cur.execute(
                    """
                    UPDATE review_assignments
                    SET status = 'APPROVED', comment = %s, decided_at = NOW()
                    WHERE id = %s AND reviewer_id = %s AND status = 'PENDING'
                    RETURNING id, requirement_id, reviewer_id, initiated_by, seq, status, comment, decided_at
                    """,
                    (comment, assignment_id, reviewer_id),
                )
                row = cur.fetchone()
                conn.commit()

        if not row:
            return None

        return {
            "id": row[0],
            "requirement_id": row[1],
            "reviewer_id": row[2],
            "initiated_by": row[3],
            "seq": row[4],
            "status": row[5],
            "comment": row[6],
            "decided_at": row[7].isoformat() if row[7] else None,
        }

    def reject_review(
        self,
        assignment_id: int,
        reviewer_id: str,
        comment: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        驳回评审

        Args:
            assignment_id: 评审指派 ID
            reviewer_id: 评审人用户 ID
            comment: 驳回原因

        Returns:
            更新后的评审指派信息，失败返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE review_assignments
                    SET status = 'REJECTED', comment = %s, decided_at = NOW()
                    WHERE id = %s AND reviewer_id = %s AND status = 'PENDING'
                    RETURNING id, requirement_id, reviewer_id, initiated_by, seq, status, comment, decided_at
                    """,
                    (comment, assignment_id, reviewer_id),
                )
                row = cur.fetchone()
                conn.commit()

        if not row:
            return None

        return {
            "id": row[0],
            "requirement_id": row[1],
            "reviewer_id": row[2],
            "initiated_by": row[3],
            "seq": row[4],
            "status": row[5],
            "comment": row[6],
            "decided_at": row[7].isoformat() if row[7] else None,
        }

    def withdraw_review(
        self,
        assignment_id: int,
        initiated_by: str,
    ) -> Optional[Dict]:
        """
        撤回评审

        Args:
            assignment_id: 评审指派 ID
            initiated_by: 发起人用户 ID

        Returns:
            更新后的评审指派信息，失败返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE review_assignments
                    SET status = 'WITHDRAWN'
                    WHERE id = %s AND initiated_by = %s AND status = 'PENDING'
                    RETURNING id, requirement_id, reviewer_id, initiated_by, seq, status
                    """,
                    (assignment_id, initiated_by),
                )
                row = cur.fetchone()
                conn.commit()

        if not row:
            return None

        return {
            "id": row[0],
            "requirement_id": row[1],
            "reviewer_id": row[2],
            "initiated_by": row[3],
            "seq": row[4],
            "status": row[5],
        }

    def list_requirement_reviews(
        self,
        requirement_id: str,
        status: Optional[str] = None,
    ) -> List[Dict]:
        """
        列出需求的所有评审

        Args:
            requirement_id: 需求 ID
            status: 筛选状态（可选）

        Returns:
            评审列表
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if status:
                    cur.execute(
                        """
                        SELECT
                            ra.id, ra.requirement_id, ra.reviewer_id, ra.initiated_by,
                            ra.seq, ra.status, ra.comment, ra.decided_at, ra.created_at,
                            ru.username, ru.display_name,
                            iu.username as initiator_username, iu.display_name as initiator_display_name
                        FROM review_assignments ra
                        LEFT JOIN auth_users ru ON ra.reviewer_id = ru.user_id
                        LEFT JOIN auth_users iu ON ra.initiated_by = iu.user_id
                        WHERE ra.requirement_id = %s AND ra.status = %s
                        ORDER BY ra.seq ASC, ra.created_at DESC
                        """,
                        (requirement_id, status),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            ra.id, ra.requirement_id, ra.reviewer_id, ra.initiated_by,
                            ra.seq, ra.status, ra.comment, ra.decided_at, ra.created_at,
                            ru.username, ru.display_name,
                            iu.username as initiator_username, iu.display_name as initiator_display_name
                        FROM review_assignments ra
                        LEFT JOIN auth_users ru ON ra.reviewer_id = ru.user_id
                        LEFT JOIN auth_users iu ON ra.initiated_by = iu.user_id
                        WHERE ra.requirement_id = %s
                        ORDER BY ra.seq ASC, ra.created_at DESC
                        """,
                        (requirement_id,),
                    )
                rows = cur.fetchall()

        return [
            {
                "id": row[0],
                "requirement_id": row[1],
                "reviewer_id": row[2],
                "initiated_by": row[3],
                "seq": row[4],
                "status": row[5],
                "comment": row[6],
                "decided_at": row[7].isoformat() if row[7] else None,
                "created_at": row[8].isoformat() if row[8] else None,
                "reviewer_username": row[9],
                "reviewer_display_name": row[10],
                "initiator_username": row[11],
                "initiator_display_name": row[12],
            }
            for row in rows
        ]

    def get_user_pending_reviews(
        self,
        user_id: str,
        project_id: Optional[str] = None,
    ) -> List[Dict]:
        """
        获取用户的待处理评审列表

        Args:
            user_id: 用户 ID
            project_id: 项目 ID（可选，用于筛选）

        Returns:
            待处理评审列表
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if project_id:
                    cur.execute(
                        """
                        SELECT
                            ra.id, ra.requirement_id, ra.reviewer_id, ra.initiated_by,
                            ra.seq, ra.status, ra.comment, ra.created_at,
                            req.title as requirement_title, req.status as requirement_status,
                            ru.username as initiator_username, ru.display_name as initiator_display_name
                        FROM review_assignments ra
                        JOIN manage_requirements req ON ra.requirement_id = req.req_id
                        LEFT JOIN auth_users ru ON ra.initiated_by = ru.user_id
                        WHERE ra.reviewer_id = %s AND ra.status = 'PENDING' AND req.project_id = %s
                        ORDER BY ra.created_at DESC
                        """,
                        (user_id, project_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            ra.id, ra.requirement_id, ra.reviewer_id, ra.initiated_by,
                            ra.seq, ra.status, ra.comment, ra.created_at,
                            req.title as requirement_title, req.status as requirement_status,
                            req.project_id,
                            ru.username as initiator_username, ru.display_name as initiator_display_name
                        FROM review_assignments ra
                        JOIN manage_requirements req ON ra.requirement_id = req.req_id
                        LEFT JOIN auth_users ru ON ra.initiated_by = ru.user_id
                        WHERE ra.reviewer_id = %s AND ra.status = 'PENDING'
                        ORDER BY ra.created_at DESC
                        """,
                        (user_id,),
                    )
                rows = cur.fetchall()

        if project_id:
            return [
                {
                    "id": row[0],
                    "requirement_id": row[1],
                    "reviewer_id": row[2],
                    "initiated_by": row[3],
                    "seq": row[4],
                    "status": row[5],
                    "comment": row[6],
                    "created_at": row[7].isoformat() if row[7] else None,
                    "requirement_title": row[8],
                    "requirement_status": row[9],
                    "initiator_username": row[10],
                    "initiator_display_name": row[11],
                }
                for row in rows
            ]
        else:
            return [
                {
                    "id": row[0],
                    "requirement_id": row[1],
                    "reviewer_id": row[2],
                    "initiated_by": row[3],
                    "seq": row[4],
                    "status": row[5],
                    "comment": row[6],
                    "created_at": row[7].isoformat() if row[7] else None,
                    "requirement_title": row[8],
                    "requirement_status": row[9],
                    "project_id": row[10],
                    "initiator_username": row[11],
                    "initiator_display_name": row[12],
                }
                for row in rows
            ]

    def get_review_assignment(
        self,
        assignment_id: int,
    ) -> Optional[Dict]:
        """
        获取评审指派详情

        Args:
            assignment_id: 评审指派 ID

        Returns:
            评审指派信息，不存在返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        ra.id, ra.requirement_id, ra.reviewer_id, ra.initiated_by,
                        ra.seq, ra.status, ra.comment, ra.decided_at, ra.created_at,
                        req.title as requirement_title, req.project_id,
                        ru.username, ru.display_name,
                        iu.username as initiator_username, iu.display_name as initiator_display_name
                    FROM review_assignments ra
                    JOIN manage_requirements req ON ra.requirement_id = req.req_id
                    LEFT JOIN auth_users ru ON ra.reviewer_id = ru.user_id
                    LEFT JOIN auth_users iu ON ra.initiated_by = iu.user_id
                    WHERE ra.id = %s
                    """,
                    (assignment_id,),
                )
                row = cur.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "requirement_id": row[1],
            "reviewer_id": row[2],
            "initiated_by": row[3],
            "seq": row[4],
            "status": row[5],
            "comment": row[6],
            "decided_at": row[7].isoformat() if row[7] else None,
            "created_at": row[8].isoformat() if row[8] else None,
            "requirement_title": row[9],
            "project_id": row[10],
            "reviewer_username": row[11],
            "reviewer_display_name": row[12],
            "initiator_username": row[13],
            "initiator_display_name": row[14],
        }

    def can_user_review(
        self,
        requirement_id: str,
        user_id: str,
    ) -> bool:
        """
        检查用户是否可以评审该需求（是否有待处理的评审指派）

        Args:
            requirement_id: 需求 ID
            user_id: 用户 ID

        Returns:
            是否可以评审
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM review_assignments
                    WHERE requirement_id = %s AND reviewer_id = %s AND status = 'PENDING'
                    """,
                    (requirement_id, user_id),
                )
                count = cur.fetchone()[0]

        return count > 0

    def get_requirement_review_status(
        self,
        requirement_id: str,
    ) -> Dict:
        """
        获取需求的评审状态汇总

        Args:
            requirement_id: 需求 ID

        Returns:
            评审状态统计
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        status,
                        COUNT(*) as count
                    FROM review_assignments
                    WHERE requirement_id = %s
                    GROUP BY status
                    """,
                    (requirement_id,),
                )
                rows = cur.fetchall()

        status_counts = {s: 0 for s in ALL_REVIEW_STATUSES}
        for row in rows:
            status_counts[row[0]] = row[1]

        return {
            "requirement_id": requirement_id,
            "status_counts": status_counts,
            "total": sum(status_counts.values()),
            "pending": status_counts[REVIEW_STATUS_PENDING],
            "approved": status_counts[REVIEW_STATUS_APPROVED],
            "rejected": status_counts[REVIEW_STATUS_REJECTED],
            "withdrawn": status_counts[REVIEW_STATUS_WITHDRAWN],
        }
