"""
数据库认证相关操作：用户 CRUD
"""

from typing import Dict, Optional


class AuthMixin:
    """认证相关的数据库操作 Mixin"""

    # ========================
    # User CRUD Operations
    # ========================

    def create_user(
        self,
        user_id: str,
        username: str,
        password_hash: str,
        display_name: str,
        role: Optional[str] = "member",
        is_active: bool = True,
        external_type: Optional[str] = None,
        avatar_url: Optional[str] = None,
        registration_status: Optional[str] = None,
    ) -> Dict:
        """
        创建用户

        Args:
            user_id: 用户 ID
            username: 用户名（唯一）
            password_hash: 密码哈希
            display_name: 显示名称
            role: 角色 (admin, member, viewer)
            is_active: 是否激活
            external_type: 外部身份 (CLIENT, CONTRACTOR)
            avatar_url: 头像 URL
            registration_status: 注册状态 (pending, approved, rejected)

        Returns:
            创建的用户信息
        """
        normalized_role = "viewer" if role is None else role

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO auth_users (user_id, username, password_hash, display_name, role, is_active, external_type, avatar_url, registration_status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING user_id, username, display_name, role, is_active, external_type, avatar_url, created_at, registration_status
                    """,
                    (
                        user_id,
                        username,
                        password_hash,
                        display_name,
                        normalized_role,
                        is_active,
                        external_type,
                        avatar_url,
                        registration_status,
                    ),
                )
                row = cur.fetchone()
                conn.commit()

        return {
            "user_id": row[0],
            "username": row[1],
            "display_name": row[2],
            "role": row[3],
            "is_active": row[4],
            "external_type": row[5],
            "avatar_url": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
            "registration_status": row[8],
        }

    def get_user_by_username(self, username: str) -> Optional[Dict]:
        """
        根据用户名获取用户（仅检查 pending 或 approved 状态）
        用于注册时检查用户名是否已存在

        Args:
            username: 用户名

        Returns:
            用户信息，不存在返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 只检查 pending 或 approved 状态，允许被拒绝的用户重新注册
                cur.execute(
                    """
                    SELECT user_id, username, password_hash, display_name, role, is_active, external_type, avatar_url, created_at, updated_at
                    FROM auth_users
                    WHERE username = %s AND registration_status IN ('pending', 'approved')
                    """,
                    (username,),
                )
                row = cur.fetchone()

        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "display_name": row[3],
            "role": row[4],
            "is_active": row[5],
            "external_type": row[6],
            "avatar_url": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None,
        }

    def get_user_by_id(self, user_id: str) -> Optional[Dict]:
        """
        根据 ID 获取用户

        Args:
            user_id: 用户 ID

        Returns:
            用户信息，不存在返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, username, password_hash, display_name, role, is_active, external_type, avatar_url, created_at, updated_at
                    FROM auth_users
                    WHERE user_id = %s AND is_active = TRUE
                    """,
                    (user_id,),
                )
                row = cur.fetchone()

        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "display_name": row[3],
            "role": row[4],
            "is_active": row[5],
            "external_type": row[6],
            "avatar_url": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None,
        }

    def list_users(
        self,
        role: Optional[str] = None,
        limit: int = 100,
        offset: int = 0,
        include_inactive: bool = False,
    ) -> Dict:
        """
        列出用户

        Args:
            role: 角色筛选
            limit: 返回数量限制
            offset: 偏移量
            include_inactive: 是否包含未激活用户

        Returns:
            用户列表和总数
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 构建查询条件
                conditions = []
                params = []
                if not include_inactive:
                    conditions.append("is_active = TRUE")
                if role:
                    conditions.append("role = %s")
                    params.append(role)

                where_clause = " AND ".join(conditions) if conditions else "TRUE"

                # 查询总数
                cur.execute(
                    f"SELECT COUNT(*) FROM auth_users WHERE {where_clause}",
                    tuple(params),
                )
                total = cur.fetchone()[0]

                # 查询数据
                params.extend([limit, offset])
                cur.execute(
                    f"""
                    SELECT user_id, username, display_name, role, is_active, external_type, avatar_url, created_at
                    FROM auth_users
                    WHERE {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()

        users = [
            {
                "user_id": row[0],
                "username": row[1],
                "display_name": row[2],
                "role": row[3],
                "is_active": row[4],
                "external_type": row[5],
                "avatar_url": row[6],
                "created_at": row[7].isoformat() if row[7] else None,
            }
            for row in rows
        ]

        return {
            "users": users,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def update_user(
        self,
        user_id: str,
        display_name: Optional[str] = None,
        role: Optional[str] = None,
        is_active: Optional[bool] = None,
        external_type: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        更新用户信息

        Args:
            user_id: 用户 ID
            display_name: 显示名称（可选）
            role: 角色（可选）
            is_active: 是否激活（可选）
            external_type: 外部身份（可选）
            avatar_url: 头像 URL（可选）

        Returns:
            更新后的用户信息，不存在返回 None
        """
        updates = []
        params = []

        if display_name is not None:
            updates.append("display_name = %s")
            params.append(display_name)

        if role is not None:
            updates.append("role = %s")
            params.append(role)

        if is_active is not None:
            updates.append("is_active = %s")
            params.append(is_active)

        if external_type is not None:
            updates.append("external_type = %s")
            params.append(external_type)

        if avatar_url is not None:
            updates.append("avatar_url = %s")
            params.append(avatar_url)

        if not updates:
            return self.get_user_by_id(user_id)

        updates.append("updated_at = NOW()")
        params.append(user_id)

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE auth_users
                    SET {", ".join(updates)}
                    WHERE user_id = %s
                    RETURNING user_id, username, display_name, role, is_active, external_type, avatar_url, created_at, updated_at
                    """,
                    tuple(params),
                )
                row = cur.fetchone()
                conn.commit()

        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "display_name": row[2],
            "role": row[3],
            "is_active": row[4],
            "external_type": row[5],
            "avatar_url": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
            "updated_at": row[8].isoformat() if row[8] else None,
        }

    def update_profile(
        self,
        user_id: str,
        display_name: Optional[str] = None,
        avatar_url: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        更新用户个人资料（用户自服务，仅允许修改 display_name 和 avatar_url）

        Args:
            user_id: 用户 ID
            display_name: 显示名称（可选）
            avatar_url: 头像 URL（可选，传空字符串表示清除头像）

        Returns:
            更新后的用户信息，不存在返回 None
        """
        updates = []
        params = []

        if display_name is not None:
            updates.append("display_name = %s")
            params.append(display_name)

        if avatar_url is not None:
            updates.append("avatar_url = %s")
            # 空字符串视为 NULL（清除头像）
            params.append(avatar_url if avatar_url.strip() else None)

        if not updates:
            return self.get_user_by_id(user_id)

        updates.append("updated_at = NOW()")
        params.append(user_id)

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE auth_users
                    SET {", ".join(updates)}
                    WHERE user_id = %s
                    RETURNING user_id, username, display_name, role, is_active, external_type, avatar_url, created_at, updated_at
                    """,
                    tuple(params),
                )
                row = cur.fetchone()
                conn.commit()

        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "display_name": row[2],
            "role": row[3],
            "is_active": row[4],
            "external_type": row[5],
            "avatar_url": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
            "updated_at": row[8].isoformat() if row[8] else None,
        }

    def delete_user(self, user_id: str) -> bool:
        """
        删除用户（软删除：设置 is_active = FALSE）

        Args:
            user_id: 用户 ID

        Returns:
            是否成功
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE auth_users SET is_active = FALSE WHERE user_id = %s",
                    (user_id,),
                )
                conn.commit()

        return cur.rowcount > 0

    def change_password(self, user_id: str, new_password_hash: str) -> bool:
        """
        修改用户密码

        Args:
            user_id: 用户 ID
            new_password_hash: 新密码哈希

        Returns:
            是否成功
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE auth_users
                    SET password_hash = %s, updated_at = NOW()
                    WHERE user_id = %s
                    """,
                    (new_password_hash, user_id),
                )
                conn.commit()

        return cur.rowcount > 0

    # ========================
    # Registration Management Methods
    # ========================

    def get_user_by_username_for_auth(self, username: str) -> Optional[Dict]:
        """
        根据用户名获取用户（不过滤 is_active，用于登录时检查审批状态）

        Args:
            username: 用户名

        Returns:
            用户信息，不存在返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, username, password_hash, display_name, role, is_active,
                           external_type, avatar_url, created_at, updated_at,
                           registration_status, rejection_reason, rejected_at,
                           approved_at, approved_by, rejected_by
                    FROM auth_users
                    WHERE username = %s
                    """,
                    (username,),
                )
                row = cur.fetchone()

        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "password_hash": row[2],
            "display_name": row[3],
            "role": row[4],
            "is_active": row[5],
            "external_type": row[6],
            "avatar_url": row[7],
            "created_at": row[8].isoformat() if row[8] else None,
            "updated_at": row[9].isoformat() if row[9] else None,
            "registration_status": row[10],
            "rejection_reason": row[11],
            "rejected_at": row[12].isoformat() if row[12] else None,
            "approved_at": row[13].isoformat() if row[13] else None,
            "approved_by": row[14],
            "rejected_by": row[15],
        }

    def get_pending_registrations(
        self, status: str = "pending", limit: int = 100, offset: int = 0
    ) -> Dict:
        """
        列出注册请求

        Args:
            status: 状态筛选 (pending, approved, rejected)
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            注册请求列表和总数
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 验证状态值
                valid_statuses = ("pending", "approved", "rejected")
                if status not in valid_statuses:
                    status = "pending"

                # 查询总数
                cur.execute(
                    "SELECT COUNT(*) FROM auth_users WHERE registration_status = %s",
                    (status,),
                )
                total = cur.fetchone()[0]

                # 查询数据
                cur.execute(
                    """
                    SELECT user_id, username, display_name, external_type,
                           avatar_url, created_at, registration_status
                    FROM auth_users
                    WHERE registration_status = %s
                    ORDER BY created_at ASC
                    LIMIT %s OFFSET %s
                    """,
                    (status, limit, offset),
                )
                rows = cur.fetchall()

        registrations = [
            {
                "user_id": row[0],
                "username": row[1],
                "display_name": row[2],
                "external_type": row[3],
                "avatar_url": row[4],
                "created_at": row[5].isoformat() if row[5] else None,
                "registration_status": row[6],
            }
            for row in rows
        ]

        return {
            "registrations": registrations,
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    def approve_registration(
        self,
        user_id: str,
        approved_by_user_id: str,
        role: str,
        external_type: Optional[str] = None,
    ) -> Optional[Dict]:
        """
        批准注册

        Args:
            user_id: 要批准的用户 ID
            approved_by_user_id: 管理员用户 ID
            role: 分配的角色 (admin, member, viewer)
            external_type: 外部身份 (CLIENT, CONTRACTOR)

        Returns:
            更新后的用户信息，不存在或已被处理返回 None
        """
        updates = [
            "is_active = TRUE",
            "registration_status = 'approved'",
            "role = %s",
            "approved_by = %s",
            "approved_at = NOW()",
        ]
        params = [role, approved_by_user_id]

        if external_type is not None:
            updates.append("external_type = %s")
            params.append(external_type)

        params.append(user_id)

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    UPDATE auth_users
                    SET {", ".join(updates)}, updated_at = NOW()
                    WHERE user_id = %s AND registration_status = 'pending'
                    RETURNING user_id, username, display_name, role, is_active,
                             external_type, avatar_url, created_at, registration_status,
                             approved_at, approved_by
                    """,
                    tuple(params),
                )
                row = cur.fetchone()
                conn.commit()

        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "display_name": row[2],
            "role": row[3],
            "is_active": row[4],
            "external_type": row[5],
            "avatar_url": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
            "registration_status": row[8],
            "approved_at": row[9].isoformat() if row[9] else None,
            "approved_by": row[10],
        }

    def reject_registration(
        self,
        user_id: str,
        rejected_by_user_id: str,
        rejection_reason: str,
    ) -> Optional[Dict]:
        """
        拒绝注册

        Args:
            user_id: 要拒绝的用户 ID
            rejected_by_user_id: 管理员用户 ID
            rejection_reason: 拒绝原因

        Returns:
            更新后的用户信息，不存在或已被处理返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE auth_users
                    SET is_active = FALSE,
                        registration_status = 'rejected',
                        rejection_reason = %s,
                        rejected_by = %s,
                        rejected_at = NOW(),
                        updated_at = NOW()
                    WHERE user_id = %s AND registration_status = 'pending'
                    RETURNING user_id, username, display_name, role, is_active,
                             registration_status, rejection_reason, rejected_at, rejected_by
                    """,
                    (rejection_reason, rejected_by_user_id, user_id),
                )
                row = cur.fetchone()
                conn.commit()

        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "display_name": row[2],
            "role": row[3],
            "is_active": row[4],
            "registration_status": row[5],
            "rejection_reason": row[6],
            "rejected_at": row[7].isoformat() if row[7] else None,
            "rejected_by": row[8],
        }

    def get_registration_details(self, user_id: str) -> Optional[Dict]:
        """
        获取注册详情

        Args:
            user_id: 用户 ID

        Returns:
            用户注册详情，不存在返回 None
        """
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, username, display_name, role, is_active,
                           external_type, avatar_url, created_at, registration_status,
                           rejection_reason, rejected_at, approved_at, approved_by, rejected_by
                    FROM auth_users
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                row = cur.fetchone()

        if not row:
            return None

        return {
            "user_id": row[0],
            "username": row[1],
            "display_name": row[2],
            "role": row[3],
            "is_active": row[4],
            "external_type": row[5],
            "avatar_url": row[6],
            "created_at": row[7].isoformat() if row[7] else None,
            "registration_status": row[8],
            "rejection_reason": row[9],
            "rejected_at": row[10].isoformat() if row[10] else None,
            "approved_at": row[11].isoformat() if row[11] else None,
            "approved_by": row[12],
            "rejected_by": row[13],
        }
