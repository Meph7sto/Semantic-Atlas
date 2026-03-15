"""
基线管理 Mixin
"""

from typing import Dict, List, Optional


class BaselinesMixin:
    """基线相关的数据库操作 Mixin"""

    def create_baseline(
        self,
        project_id: str,
        version: str,
        created_by: str,
        locked: bool = False,
    ) -> Optional[Dict]:
        """
        创建基线

        Args:
            project_id: 项目 ID
            version: 版本号
            created_by: 创建者用户 ID
            locked: 是否锁定

        Returns:
            创建的基线信息，失败返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO baselines (project_id, version, locked, created_by, created_at)
                    VALUES (%s, %s, %s, %s, NOW())
                    RETURNING id, project_id, version, locked, created_by, created_at
                    """,
                    (project_id, version, locked, created_by),
                )
                row = cur.fetchone()
                conn.commit()

        return {
            "id": row[0],
            "project_id": row[1],
            "version": row[2],
            "locked": row[3],
            "created_by": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
        }

    def lock_baseline(
        self,
        baseline_id: int,
        user_id: str,
    ) -> Optional[Dict]:
        """
        锁定基线

        Args:
            baseline_id: 基线 ID
            user_id: 操作者用户 ID

        Returns:
            更新后的基线信息，失败返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE baselines
                    SET locked = TRUE
                    WHERE id = %s
                    RETURNING id, project_id, version, locked, created_by, created_at
                    """,
                    (baseline_id,),
                )
                row = cur.fetchone()
                conn.commit()

        if not row:
            return None

        return {
            "id": row[0],
            "project_id": row[1],
            "version": row[2],
            "locked": row[3],
            "created_by": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
        }

    def unlock_baseline(
        self,
        baseline_id: int,
        user_id: str,
    ) -> Optional[Dict]:
        """
        解锁基线

        Args:
            baseline_id: 基线 ID
            user_id: 操作者用户 ID

        Returns:
            更新后的基线信息，失败返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE baselines
                    SET locked = FALSE
                    WHERE id = %s
                    RETURNING id, project_id, version, locked, created_by, created_at
                    """,
                    (baseline_id,),
                )
                row = cur.fetchone()
                conn.commit()

        if not row:
            return None

        return {
            "id": row[0],
            "project_id": row[1],
            "version": row[2],
            "locked": row[3],
            "created_by": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
        }

    def list_project_baselines(
        self,
        project_id: str,
        include_locked: bool = True,
    ) -> List[Dict]:
        """
        列出项目的所有基线

        Args:
            project_id: 项目 ID
            include_locked: 是否包含已锁定的基线

        Returns:
            基线列表
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if include_locked:
                    cur.execute(
                        """
                        SELECT
                            b.id, b.project_id, b.version, b.locked, b.created_by, b.created_at,
                            au.username, au.display_name
                        FROM baselines b
                        LEFT JOIN auth_users au ON b.created_by = au.user_id
                        WHERE b.project_id = %s
                        ORDER BY b.id DESC
                        """,
                        (project_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            b.id, b.project_id, b.version, b.locked, b.created_by, b.created_at,
                            au.username, au.display_name
                        FROM baselines b
                        LEFT JOIN auth_users au ON b.created_by = au.user_id
                        WHERE b.project_id = %s AND b.locked = FALSE
                        ORDER BY b.id DESC
                        """,
                        (project_id,),
                    )
                rows = cur.fetchall()

        return [
            {
                "id": row[0],
                "project_id": row[1],
                "version": row[2],
                "locked": row[3],
                "created_by": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "creator_username": row[6],
                "creator_display_name": row[7],
            }
            for row in rows
        ]

    def get_baseline(
        self,
        baseline_id: int,
    ) -> Optional[Dict]:
        """
        获取基线详情

        Args:
            baseline_id: 基线 ID

        Returns:
            基线信息，不存在返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        b.id, b.project_id, b.version, b.locked, b.created_by, b.created_at,
                        au.username, au.display_name
                    FROM baselines b
                    LEFT JOIN auth_users au ON b.created_by = au.user_id
                    WHERE b.id = %s
                    """,
                    (baseline_id,),
                )
                row = cur.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "project_id": row[1],
            "version": row[2],
            "locked": row[3],
            "created_by": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "creator_username": row[6],
            "creator_display_name": row[7],
        }

    def get_latest_baseline(
        self,
        project_id: str,
        include_locked: bool = True,
    ) -> Optional[Dict]:
        """
        获取项目的最新基线

        Args:
            project_id: 项目 ID
            include_locked: 是否包含已锁定的基线

        Returns:
            最新基线信息，不存在返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if include_locked:
                    cur.execute(
                        """
                        SELECT
                            b.id, b.project_id, b.version, b.locked, b.created_by, b.created_at,
                            au.username, au.display_name
                        FROM baselines b
                        LEFT JOIN auth_users au ON b.created_by = au.user_id
                        WHERE b.project_id = %s
                        ORDER BY b.id DESC
                        LIMIT 1
                        """,
                        (project_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            b.id, b.project_id, b.version, b.locked, b.created_by, b.created_at,
                            au.username, au.display_name
                        FROM baselines b
                        LEFT JOIN auth_users au ON b.created_by = au.user_id
                        WHERE b.project_id = %s AND b.locked = FALSE
                        ORDER BY b.id DESC
                        LIMIT 1
                        """,
                        (project_id,),
                    )
                row = cur.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "project_id": row[1],
            "version": row[2],
            "locked": row[3],
            "created_by": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "creator_username": row[6],
            "creator_display_name": row[7],
        }

    def get_baseline_by_version(
        self,
        project_id: str,
        version: str,
    ) -> Optional[Dict]:
        """
        根据版本号获取基线

        Args:
            project_id: 项目 ID
            version: 版本号

        Returns:
            基线信息，不存在返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        b.id, b.project_id, b.version, b.locked, b.created_by, b.created_at,
                        au.username, au.display_name
                    FROM baselines b
                    LEFT JOIN auth_users au ON b.created_by = au.user_id
                    WHERE b.project_id = %s AND b.version = %s
                    ORDER BY b.id DESC
                    LIMIT 1
                    """,
                    (project_id, version),
                )
                row = cur.fetchone()

        if not row:
            return None

        return {
            "id": row[0],
            "project_id": row[1],
            "version": row[2],
            "locked": row[3],
            "created_by": row[4],
            "created_at": row[5].isoformat() if row[5] else None,
            "creator_username": row[6],
            "creator_display_name": row[7],
        }

    def is_baseline_locked(
        self,
        baseline_id: int,
    ) -> bool:
        """
        检查基线是否已锁定

        Args:
            baseline_id: 基线 ID

        Returns:
            是否已锁定
        """
        baseline = self.get_baseline(baseline_id)
        return baseline.get("locked", False) if baseline else False

    def get_requirements_in_baseline(
        self,
        baseline_id: int,
    ) -> List[Dict]:
        """
        获取基线中的所有需求

        Args:
            baseline_id: 基线 ID

        Returns:
            需求列表
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        req_id, project_id, requirement_type, status, title, description,
                        priority, assignee, tags, due_date, parent_id, order_index,
                        created_by, created_at, updated_by, updated_at
                    FROM manage_requirements
                    WHERE baseline_id = %s AND deleted = FALSE
                    ORDER BY order_index ASC, created_at ASC
                    """,
                    (baseline_id,),
                )
                rows = cur.fetchall()

        return [
            {
                "req_id": row[0],
                "project_id": row[1],
                "requirement_type": row[2],
                "status": row[3],
                "title": row[4],
                "description": row[5],
                "priority": row[6],
                "assignee": row[7],
                "tags": row[8],
                "due_date": row[9],
                "parent_id": row[10],
                "order_index": row[11],
                "created_by": row[12],
                "created_at": row[13].isoformat() if row[13] else None,
                "updated_by": row[14],
                "updated_at": row[15].isoformat() if row[15] else None,
            }
            for row in rows
        ]

    def set_requirement_baseline(
        self,
        requirement_id: str,
        baseline_id: Optional[int],
    ) -> bool:
        """
        设置需求关联的基线

        Args:
            requirement_id: 需求 ID
            baseline_id: 基线 ID（设为 NULL 则取消关联）

        Returns:
            是否成功
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE manage_requirements
                    SET baseline_id = %s, updated_at = NOW()
                    WHERE req_id = %s
                    """,
                    (baseline_id, requirement_id),
                )
                conn.commit()

        return cur.rowcount > 0
