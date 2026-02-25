"""
成员角色管理 Mixin
"""

from typing import Dict, List, Optional, Set


# 角色常量
ROLE_PO = "PO"       # 产品负责人
ROLE_BA = "BA"       # 业务分析师
ROLE_DEV = "DEV"     # 开发人员
ROLE_REVIEWER = "REVIEWER"  # 评审人员
ROLE_QA = "QA"       # 测试人员
ROLE_CONTRACTOR = "CONTRACTOR"  # 外包成员
ROLE_CLIENT = "CLIENT"  # 客户

ALL_ROLES = [ROLE_PO, ROLE_BA, ROLE_DEV, ROLE_REVIEWER, ROLE_QA, ROLE_CONTRACTOR, ROLE_CLIENT]


class MemberRolesMixin:
    """成员角色相关的数据库操作 Mixin"""

    def assign_role(
        self,
        project_id: str,
        user_id: str,
        role_id: str,
        granted_by: str,
    ) -> Optional[Dict]:
        """
        分配角色给成员

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            role_id: 角色 ID
            granted_by: 授权者用户 ID

        Returns:
            创建的角色绑定信息，失败返回 None
        """
        if role_id not in ALL_ROLES:
            return None

        # 获取成员 ID
        member_id = self.get_member_id(project_id, user_id)
        if not member_id:
            return None

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 检查角色是否已存在
                cur.execute(
                    """
                    SELECT id FROM member_roles
                    WHERE member_id = %s AND role_id = %s
                    """,
                    (member_id, role_id),
                )
                if cur.fetchone():
                    return None  # 角色已存在

                cur.execute(
                    """
                    INSERT INTO member_roles (member_id, role_id, granted_by, granted_at)
                    VALUES (%s, %s, %s, NOW())
                    RETURNING id, member_id, role_id, granted_by, granted_at
                    """,
                    (member_id, role_id, granted_by),
                )
                row = cur.fetchone()
                conn.commit()

        return {
            "id": row[0],
            "member_id": row[1],
            "role_id": row[2],
            "granted_by": row[3],
            "granted_at": row[4].isoformat() if row[4] else None,
        }

    def revoke_role(
        self,
        project_id: str,
        user_id: str,
        role_id: str,
    ) -> bool:
        """
        撤销成员的角色

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            role_id: 角色 ID

        Returns:
            是否成功撤销
        """
        member_id = self.get_member_id(project_id, user_id)
        if not member_id:
            return False

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM member_roles
                    WHERE member_id = %s AND role_id = %s
                    """,
                    (member_id, role_id),
                )
                conn.commit()

        return cur.rowcount > 0

    def get_user_roles(
        self,
        project_id: str,
        user_id: str,
    ) -> List[str]:
        """
        获取用户在项目中的所有角色

        Args:
            project_id: 项目 ID
            user_id: 用户 ID

        Returns:
            角色列表
        """
        member_id = self.get_member_id(project_id, user_id)
        if not member_id:
            return []

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT role_id FROM member_roles
                    WHERE member_id = %s
                    """,
                    (member_id,),
                )
                rows = cur.fetchall()

        return [row[0] for row in rows]

    def set_user_roles(
        self,
        project_id: str,
        user_id: str,
        role_ids: List[str],
        granted_by: str,
    ) -> Dict:
        """
        全量设置用户的角色（先删除所有现有角色，再添加新角色）

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            role_ids: 角色列表
            granted_by: 授权者用户 ID

        Returns:
            操作结果：新增、删除、保留的角色列表
        """
        member_id = self.get_member_id(project_id, user_id)
        if not member_id:
            return {"error": "用户不是项目成员"}

        # 验证角色有效性
        valid_roles = [r for r in role_ids if r in ALL_ROLES]
        invalid_roles = set(role_ids) - set(valid_roles)

        if invalid_roles:
            return {"error": f"无效的角色: {', '.join(invalid_roles)}"}

        # 获取现有角色
        existing_roles = set(self.get_user_roles(project_id, user_id))
        new_roles = set(valid_roles)

        # 计算差异
        to_add = new_roles - existing_roles
        to_remove = existing_roles - new_roles
        to_keep = existing_roles & new_roles

        added = []
        removed = []

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 删除需要移除的角色
                if to_remove:
                    for role_id in to_remove:
                        cur.execute(
                            """
                            DELETE FROM member_roles
                            WHERE member_id = %s AND role_id = %s
                            """,
                            (member_id, role_id),
                        )
                        removed.append(role_id)

                # 添加新角色
                if to_add:
                    for role_id in to_add:
                        cur.execute(
                            """
                            INSERT INTO member_roles (member_id, role_id, granted_by, granted_at)
                            VALUES (%s, %s, %s, NOW())
                            """,
                            (member_id, role_id, granted_by),
                        )
                        added.append(role_id)

                conn.commit()

        return {
            "added": added,
            "removed": removed,
            "kept": list(to_keep),
        }

    def get_members_by_role(
        self,
        project_id: str,
        role_id: str,
    ) -> List[Dict]:
        """
        获取项目中具有指定角色的所有成员

        Args:
            project_id: 项目 ID
            role_id: 角色 ID

        Returns:
            成员列表
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        pm.id, pm.project_id, pm.user_id, pm.joined_at,
                        au.username, au.display_name, au.external_type
                    FROM member_roles mr
                    JOIN project_members pm ON mr.member_id = pm.id
                    LEFT JOIN auth_users au ON pm.user_id = au.user_id
                    WHERE pm.project_id = %s AND mr.role_id = %s
                    ORDER BY pm.joined_at DESC
                    """,
                    (project_id, role_id),
                )
                rows = cur.fetchall()

        return [
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

    def check_user_has_role(
        self,
        project_id: str,
        user_id: str,
        role_id: str,
    ) -> bool:
        """
        检查用户是否具有指定角色

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            role_id: 角色 ID

        Returns:
            是否具有该角色
        """
        roles = self.get_user_roles(project_id, user_id)
        return role_id in roles

    def check_user_has_any_role(
        self,
        project_id: str,
        user_id: str,
        role_ids: List[str],
    ) -> bool:
        """
        检查用户是否具有任意一个指定角色

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            role_ids: 角色列表

        Returns:
            是否具有任意一个角色
        """
        roles = set(self.get_user_roles(project_id, user_id))
        return bool(roles & set(role_ids))

    def get_all_project_roles(
        self,
        project_id: str,
    ) -> Dict[str, List[Dict]]:
        """
        获取项目中所有角色的成员分布

        Args:
            project_id: 项目 ID

        Returns:
            按角色分组的成员字典
        """
        result = {role: [] for role in ALL_ROLES}

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT
                        mr.role_id, pm.user_id, au.username, au.display_name, au.external_type
                    FROM member_roles mr
                    JOIN project_members pm ON mr.member_id = pm.id
                    LEFT JOIN auth_users au ON pm.user_id = au.user_id
                    WHERE pm.project_id = %s
                    ORDER BY mr.role_id, pm.joined_at DESC
                    """,
                    (project_id,),
                )
                rows = cur.fetchall()

        for row in rows:
            role_id, user_id, username, display_name, external_type = row
            result[role_id].append({
                "user_id": user_id,
                "username": username,
                "display_name": display_name,
                "external_type": external_type,
            })

        return result
