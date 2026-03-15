"""
项目成员管理 Mixin
"""

from typing import Dict, List, Optional


class ProjectMembersMixin:
    """项目成员相关的数据库操作 Mixin"""

    def add_project_member(
        self,
        project_id: str,
        user_id: str,
        added_by: str,
    ) -> Optional[Dict]:
        """
        添加项目成员

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            added_by: 添加者用户 ID

        Returns:
            创建的成员信息，失败返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 检查用户是否已是成员
                cur.execute(
                    """
                    SELECT id FROM project_members
                    WHERE project_id = %s AND user_id = %s
                    """,
                    (project_id, user_id),
                )
                if cur.fetchone():
                    return None  # 已是成员

                cur.execute(
                    """
                    INSERT INTO project_members (project_id, user_id, joined_at)
                    VALUES (%s, %s, NOW())
                    RETURNING id, project_id, user_id, joined_at
                    """,
                    (project_id, user_id),
                )
                row = cur.fetchone()
                conn.commit()

        return {
            "id": row[0],
            "project_id": row[1],
            "user_id": row[2],
            "joined_at": row[3].isoformat() if row[3] else None,
        }

    def remove_project_member(
        self,
        project_id: str,
        user_id: str,
    ) -> bool:
        """
        移除项目成员

        Args:
            project_id: 项目 ID
            user_id: 用户 ID

        Returns:
            是否成功移除
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM project_members
                    WHERE project_id = %s AND user_id = %s
                    """,
                    (project_id, user_id),
                )
                conn.commit()

        return cur.rowcount > 0

    def list_project_members(
        self,
        project_id: str,
        include_roles: bool = False,
    ) -> Dict:
        """
        列出项目成员

        Args:
            project_id: 项目 ID
            include_roles: 是否包含角色信息

        Returns:
            成员列表和总数
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 查询总数
                cur.execute(
                    """
                    SELECT COUNT(*) FROM project_members
                    WHERE project_id = %s
                    """,
                    (project_id,),
                )
                total = cur.fetchone()[0]

                if include_roles:
                    # 查询包含角色的成员列表
                    cur.execute(
                        """
                        SELECT
                            pm.id, pm.project_id, pm.user_id, pm.joined_at,
                            au.username, au.display_name, au.external_type,
                            COALESCE(
                                json_agg(
                                    json_build_object(
                                        'role_id', mr.role_id,
                                        'granted_by', mr.granted_by,
                                        'granted_at', mr.granted_at
                                    )
                                ) FILTER (WHERE mr.role_id IS NOT NULL),
                                '[]'::json
                            ) as roles
                        FROM project_members pm
                        LEFT JOIN auth_users au ON pm.user_id = au.user_id
                        LEFT JOIN member_roles mr ON pm.id = mr.member_id
                        WHERE pm.project_id = %s
                        GROUP BY pm.id, au.username, au.display_name, au.external_type
                        ORDER BY pm.joined_at DESC
                        """,
                        (project_id,),
                    )
                    rows = cur.fetchall()

                    members = [
                        {
                            "id": row[0],
                            "project_id": row[1],
                            "user_id": row[2],
                            "joined_at": row[3].isoformat() if row[3] else None,
                            "username": row[4],
                            "display_name": row[5],
                            "external_type": row[6],
                            "roles": row[7] if isinstance(row[7], list) else [],
                        }
                        for row in rows
                    ]
                else:
                    # 查询基本成员列表
                    cur.execute(
                        """
                        SELECT
                            pm.id, pm.project_id, pm.user_id, pm.joined_at,
                            au.username, au.display_name, au.external_type
                        FROM project_members pm
                        LEFT JOIN auth_users au ON pm.user_id = au.user_id
                        WHERE pm.project_id = %s
                        ORDER BY pm.joined_at DESC
                        """,
                        (project_id,),
                    )
                    rows = cur.fetchall()

                    members = [
                        {
                            "id": row[0],
                            "project_id": row[1],
                            "user_id": row[2],
                            "joined_at": row[3].isoformat() if row[3] else None,
                            "username": row[4],
                            "display_name": row[5],
                            "external_type": row[6],
                        }
                        for row in rows
                    ]

        return {
            "members": members,
            "total": total,
        }

    def get_member_id(
        self,
        project_id: str,
        user_id: str,
    ) -> Optional[int]:
        """
        获取成员 ID

        Args:
            project_id: 项目 ID
            user_id: 用户 ID

        Returns:
            成员 ID，不存在返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id FROM project_members
                    WHERE project_id = %s AND user_id = %s
                    """,
                    (project_id, user_id),
                )
                row = cur.fetchone()

        return row[0] if row else None

    def is_project_member(
        self,
        project_id: str,
        user_id: str,
    ) -> bool:
        """
        检查用户是否为项目成员

        Args:
            project_id: 项目 ID
            user_id: 用户 ID

        Returns:
            是否为成员
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT COUNT(*) FROM project_members
                    WHERE project_id = %s AND user_id = %s
                    """,
                    (project_id, user_id),
                )
                count = cur.fetchone()[0]

        return count > 0

    def list_user_projects(
        self,
        user_id: str,
        include_roles: bool = False,
    ) -> List[Dict]:
        """
        列出用户参与的所有项目

        Args:
            user_id: 用户 ID
            include_roles: 是否包含角色信息

        Returns:
            项目列表
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if include_roles:
                    cur.execute(
                        """
                        SELECT
                            p.project_id, p.name, p.description, p.status,
                            pm.joined_at,
                            COALESCE(
                                json_agg(
                                    json_build_object(
                                        'role_id', mr.role_id
                                    )
                                ) FILTER (WHERE mr.role_id IS NOT NULL),
                                '[]'::json
                            ) as roles
                        FROM project_members pm
                        JOIN manage_projects p ON pm.project_id = p.project_id
                        LEFT JOIN member_roles mr ON pm.id = mr.member_id
                        WHERE pm.user_id = %s
                        GROUP BY p.project_id, p.name, p.description, p.status, pm.joined_at
                        ORDER BY pm.joined_at DESC
                        """,
                        (user_id,),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            p.project_id, p.name, p.description, p.status, pm.joined_at
                        FROM project_members pm
                        JOIN manage_projects p ON pm.project_id = p.project_id
                        WHERE pm.user_id = %s
                        ORDER BY pm.joined_at DESC
                        """,
                        (user_id,),
                    )
                rows = cur.fetchall()

        if include_roles:
            return [
                {
                    "project_id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "status": row[3],
                    "joined_at": row[4].isoformat() if row[4] else None,
                    "roles": row[5] if isinstance(row[5], list) else [],
                }
                for row in rows
            ]
        else:
            return [
                {
                    "project_id": row[0],
                    "name": row[1],
                    "description": row[2],
                    "status": row[3],
                    "joined_at": row[4].isoformat() if row[4] else None,
                }
                for row in rows
            ]
