"""
权限管理 Mixin
"""

from typing import Dict, List, Optional, Set


# ========================
# 系统级身份常量
# ========================
SYS_ADMIN = "SYS_ADMIN"       # 超级管理员（全权限）
SYS_USER = "SYS_USER"         # 普通内部用户


# ========================
# 角色常量（引用自 member_roles）
# ========================
ROLE_PO = "PO"
ROLE_BA = "BA"
ROLE_DEV = "DEV"
ROLE_REVIEWER = "REVIEWER"
ROLE_QA = "QA"
ROLE_CONTRACTOR = "CONTRACTOR"
ROLE_CLIENT = "CLIENT"


# ========================
# 权限点常量（共 21 个）
# ========================
# 需求查看
PERM_REQ_VIEW = "req:view"
PERM_REQ_VIEW_SHARED = "req:view_shared"
PERM_REQ_VIEW_ASSIGNED = "req:view_assigned"

# 需求操作
PERM_REQ_CREATE = "req:create"
PERM_REQ_EDIT = "req:edit"
PERM_REQ_DELETE = "req:delete"

# 优先级
PERM_REQ_PRIORITY_SUGGEST = "req:priority_suggest"
PERM_REQ_PRIORITY_DECIDE = "req:priority_decide"

# 评审
PERM_REQ_APPROVE = "req:approve"
PERM_REQ_REJECT = "req:reject"
PERM_REQ_REVIEW_COMMENT = "req:review_comment"
PERM_REQ_REVIEW_INITIATE = "req:review_initiate"
PERM_REQ_CLIENT_CONFIRM = "req:client_confirm"

# 基线与变更
PERM_REQ_BASELINE_MANAGE = "req:baseline_manage"
PERM_REQ_CHANGE_REQUEST = "req:change_request"
PERM_REQ_CHANGE_APPROVE = "req:change_approve"
PERM_REQ_CHANGE_REJECT = "req:change_reject"

# 状态
PERM_REQ_STATUS_DEV = "req:status_dev"

# 代码与测试
PERM_CODE_LINK = "code:link"
PERM_TEST_LINK_CASE = "test:link_case"
PERM_TEST_REJECT_RELEASE = "test:reject_release"

# 交付
PERM_DELIVERY_SUBMIT = "delivery:submit"

# 项目管理
PERM_PROJ_CONFIG = "proj:config"
PERM_PROJ_ADD_MEMBER = "proj:add_member"
PERM_PROJ_REMOVE_MEMBER = "proj:remove_member"


# 所有权限点列表
ALL_PERMISSIONS = [
    PERM_REQ_VIEW, PERM_REQ_VIEW_SHARED, PERM_REQ_VIEW_ASSIGNED,
    PERM_REQ_CREATE, PERM_REQ_EDIT, PERM_REQ_DELETE,
    PERM_REQ_PRIORITY_SUGGEST, PERM_REQ_PRIORITY_DECIDE,
    PERM_REQ_APPROVE, PERM_REQ_REJECT, PERM_REQ_REVIEW_COMMENT,
    PERM_REQ_REVIEW_INITIATE, PERM_REQ_CLIENT_CONFIRM,
    PERM_REQ_BASELINE_MANAGE, PERM_REQ_CHANGE_REQUEST,
    PERM_REQ_CHANGE_APPROVE, PERM_REQ_CHANGE_REJECT,
    PERM_REQ_STATUS_DEV,
    PERM_CODE_LINK, PERM_TEST_LINK_CASE, PERM_TEST_REJECT_RELEASE,
    PERM_DELIVERY_SUBMIT,
    PERM_PROJ_CONFIG, PERM_PROJ_ADD_MEMBER, PERM_PROJ_REMOVE_MEMBER,
]


# ========================
# 角色-权限映射
# ========================
ROLE_PERMISSIONS = {
    ROLE_PO: [
        PERM_REQ_VIEW,
        PERM_REQ_CREATE,
        PERM_REQ_EDIT,
        PERM_REQ_DELETE,
        PERM_REQ_PRIORITY_DECIDE,
        PERM_REQ_REVIEW_INITIATE,
        PERM_REQ_BASELINE_MANAGE,
        PERM_REQ_CHANGE_REQUEST,
        PERM_REQ_CHANGE_APPROVE,
        PERM_REQ_CHANGE_REJECT,
        PERM_PROJ_CONFIG,
        PERM_PROJ_ADD_MEMBER,
        PERM_PROJ_REMOVE_MEMBER,
    ],
    ROLE_BA: [
        PERM_REQ_VIEW,
        PERM_REQ_CREATE,
        PERM_REQ_EDIT,
        PERM_REQ_PRIORITY_SUGGEST,
        PERM_REQ_REVIEW_INITIATE,
        PERM_REQ_CHANGE_REQUEST,
    ],
    ROLE_DEV: [
        PERM_REQ_VIEW,
        PERM_REQ_STATUS_DEV,
        PERM_CODE_LINK,
    ],
    ROLE_REVIEWER: [
        PERM_REQ_VIEW,
        PERM_REQ_APPROVE,
        PERM_REQ_REJECT,
        PERM_REQ_REVIEW_COMMENT,
    ],
    ROLE_QA: [
        PERM_REQ_VIEW,
        PERM_TEST_LINK_CASE,
        PERM_TEST_REJECT_RELEASE,
    ],
    ROLE_CONTRACTOR: [
        PERM_REQ_VIEW_ASSIGNED,
        PERM_DELIVERY_SUBMIT,
    ],
    ROLE_CLIENT: [
        PERM_REQ_VIEW_SHARED,
        PERM_REQ_CLIENT_CONFIRM,
    ],
}


class PermissionsMixin:
    """权限检查相关的数据库操作 Mixin"""

    @staticmethod
    def _is_super_admin(user: Optional[Dict]) -> bool:
        return bool(user and user.get("role") == "super_admin")

    def get_system_identity(self, user: Dict) -> str:
        """
        获取用户的系统级身份

        Args:
            user: 用户信息字典

        Returns:
            系统级身份：SYS_ADMIN, SYS_USER
        """
        # 根据系统级角色判断
        role = user.get("role", "")

        if role == "super_admin":
            return SYS_ADMIN

        return SYS_USER

    def get_user_permissions(
        self,
        project_id: str,
        user_id: str,
        user: Optional[Dict] = None,
    ) -> Set[str]:
        """
        获取用户在项目中的所有权限（角色权限的并集）

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            user: 用户信息字典（可选，用于判断系统身份）

        Returns:
            权限点集合
        """
        # 获取用户信息（如果未提供）
        if user is None:
            user = self.get_user_by_id(user_id)

        if not user:
            return set()

        # 获取系统级身份
        system_identity = self.get_system_identity(user)

        # 超级管理员拥有所有权限
        if system_identity == SYS_ADMIN:
            return set(ALL_PERMISSIONS)

        # 普通用户：基于项目角色计算权限
        roles = self.get_user_roles(project_id, user_id)

        # 如果用户不在项目中，返回空权限
        if not roles:
            return set()

        # 计算所有角色权限的并集
        permissions = set()
        for role in roles:
            permissions.update(ROLE_PERMISSIONS.get(role, []))

        return permissions

    def check_permission(
        self,
        project_id: str,
        user_id: str,
        permission: str,
        user: Optional[Dict] = None,
    ) -> bool:
        """
        检查用户是否具有指定权限

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            permission: 权限点
            user: 用户信息字典（可选）

        Returns:
            是否具有该权限
        """
        permissions = self.get_user_permissions(project_id, user_id, user)
        return permission in permissions

    def can_approve_review(
        self,
        project_id: str,
        user_id: str,
        requirement_id: str,
    ) -> bool:
        """
        检查用户是否可以审批指定需求的评审

        需要满足以下条件之一：
        1. 具有角色权限（REVIEWER、PO、BA）
        2. 被动态指派为该需求的评审人

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            requirement_id: 需求 ID

        Returns:
            是否可以审批
        """
        # 检查角色权限
        if self.check_permission(project_id, user_id, PERM_REQ_APPROVE):
            return True

        # 检查是否有待处理的评审指派
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

    def get_user_context(
        self,
        project_id: str,
        user_id: str,
        user: Optional[Dict] = None,
    ) -> Dict:
        """
        获取用户的权限上下文信息

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            user: 用户信息字典（可选）

        Returns:
            用户权限上下文
        """
        # 获取用户信息
        if user is None:
            user = self.get_user_by_id(user_id)

        if not user:
            return {
                "user_id": user_id,
                "project_id": project_id,
                "system_identity": None,
                "roles": [],
                "permissions": [],
            }

        # 获取系统级身份
        system_identity = self.get_system_identity(user)

        # 获取项目角色
        roles = self.get_user_roles(project_id, user_id)

        # 获取权限
        permissions = self.get_user_permissions(project_id, user_id, user)

        return {
            "user_id": user_id,
            "username": user.get("username"),
            "display_name": user.get("display_name"),
            "system_role": user.get("role"),
            "external_type": user.get("external_type"),
            "system_identity": system_identity,
            "project_id": project_id,
            "roles": roles,
            "permissions": sorted(list(permissions)),
            "can_access_project": self.can_access_project(project_id, user_id, user),
            "can_edit_project": self.can_edit_project(project_id, user_id, user),
        }

    def build_query_filter(
        self,
        project_id: str,
        user_id: str,
        external_type: Optional[str] = None,
    ) -> Dict:
        """
        构建基础查询过滤条件（兼容旧接口）

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            external_type: 外部身份类型（兼容字段，不参与过滤）

        Returns:
            包含 WHERE 条件和参数的字典
        """
        _ = user_id, external_type
        conditions = ["project_id = %s", "deleted = FALSE"]
        params = [project_id]

        return {
            "where_clause": " AND ".join(conditions),
            "params": tuple(params),
        }

    def check_edit_permission(
        self,
        project_id: str,
        user_id: str,
        requirement_id: str,
        user: Optional[Dict] = None,
    ) -> Dict:
        """
        检查用户是否可以编辑需求（包含基线锁定检查）

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            requirement_id: 需求 ID
            user: 用户信息字典（可选）

        Returns:
            包含 allowed 和 reason 的字典
        """
        # 基础权限检查
        if not self.check_permission(project_id, user_id, PERM_REQ_EDIT, user):
            return {
                "allowed": False,
                "reason": "无编辑权限",
            }

        # 检查基线锁定
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                # 获取需求关联的基线
                cur.execute(
                    """
                    SELECT baseline_id FROM manage_requirements
                    WHERE req_id = %s
                    """,
                    (requirement_id,),
                )
                row = cur.fetchone()

                if not row or not row[0]:
                    return {"allowed": True, "reason": ""}

                baseline_id = row[0]

                # 检查基线是否锁定
                cur.execute(
                    """
                    SELECT locked FROM baselines WHERE id = %s
                    """,
                    (baseline_id,),
                )
                baseline_row = cur.fetchone()

                if not baseline_row or not baseline_row[0]:
                    return {"allowed": True, "reason": ""}

                # 基线已锁定，检查是否有最近批准的变更请求
                cur.execute(
                    """
                    SELECT COUNT(*) FROM change_requests
                    WHERE requirement_id = %s
                      AND baseline_id = %s
                      AND status = 'APPROVED'
                      AND resolved_at >= NOW() - INTERVAL '24 hours'
                    """,
                    (requirement_id, baseline_id),
                )
                count = cur.fetchone()[0]

                if count > 0:
                    return {
                        "allowed": True,
                        "reason": "基线已锁定，但有最近批准的变更请求",
                    }
                else:
                    return {
                        "allowed": False,
                        "reason": "基线已锁定，需要先提交并批准变更请求",
                    }

    def can_access_project(
        self,
        project_id: str,
        user_id: str,
        user: Optional[Dict] = None,
    ) -> bool:
        """
        检查用户是否可以访问项目

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            user: 用户信息字典（可选）

        Returns:
            是否可以访问
        """
        if user is None:
            user = self.get_user_by_id(user_id)
        if not user:
            return False

        if self._is_super_admin(user):
            return True

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT p.product_id
                    FROM manage_projects p
                    WHERE p.project_id = %s
                    """,
                    (project_id,),
                )
                row = cur.fetchone()
                if not row:
                    return False
                product_id = row[0]

                cur.execute(
                    """
                    SELECT 1
                    FROM user_project_scopes
                    WHERE user_id = %s AND project_id = %s
                    """,
                    (user_id, project_id),
                )
                if cur.fetchone():
                    return True

                if not product_id:
                    return False

                cur.execute(
                    """
                    SELECT 1
                    FROM user_product_scopes
                    WHERE user_id = %s AND product_id = %s
                    """,
                    (user_id, product_id),
                )
                return cur.fetchone() is not None

    def can_access_product(
        self,
        product_id: str,
        user_id: str,
        user: Optional[Dict] = None,
    ) -> bool:
        if user is None:
            user = self.get_user_by_id(user_id)
        if not user:
            return False
        if self._is_super_admin(user):
            return True
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT 1
                    FROM user_product_scopes
                    WHERE user_id = %s AND product_id = %s
                    """,
                    (user_id, product_id),
                )
                return cur.fetchone() is not None

    def can_edit_product(
        self,
        product_id: str,
        user_id: str,
        user: Optional[Dict] = None,
    ) -> bool:
        if user is None:
            user = self.get_user_by_id(user_id)
        if not user:
            return False
        if self._is_super_admin(user):
            return True
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT can_edit
                    FROM user_product_scopes
                    WHERE user_id = %s AND product_id = %s
                    """,
                    (user_id, product_id),
                )
                row = cur.fetchone()
                return bool(row and row[0])

    def can_edit_project(
        self,
        project_id: str,
        user_id: str,
        user: Optional[Dict] = None,
    ) -> bool:
        if user is None:
            user = self.get_user_by_id(user_id)
        if not user:
            return False
        if self._is_super_admin(user):
            return True

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT can_edit
                    FROM user_project_scopes
                    WHERE user_id = %s AND project_id = %s
                    """,
                    (user_id, project_id),
                )
                explicit_row = cur.fetchone()
                if explicit_row is not None:
                    return bool(explicit_row[0])

                cur.execute(
                    """
                    SELECT product_id
                    FROM manage_projects
                    WHERE project_id = %s
                    """,
                    (project_id,),
                )
                project_row = cur.fetchone()
                if not project_row or not project_row[0]:
                    return False
                product_id = project_row[0]

                cur.execute(
                    """
                    SELECT can_edit
                    FROM user_product_scopes
                    WHERE user_id = %s AND product_id = %s
                    """,
                    (user_id, product_id),
                )
                product_row = cur.fetchone()
                return bool(product_row and product_row[0])

    def get_accessible_product_ids(
        self,
        user_id: str,
        user: Optional[Dict] = None,
    ) -> List[str]:
        if user is None:
            user = self.get_user_by_id(user_id)
        if not user:
            return []

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if self._is_super_admin(user):
                    cur.execute(
                        """
                        SELECT product_id
                        FROM manage_products
                        ORDER BY created_at DESC
                        """
                    )
                    return [row[0] for row in cur.fetchall()]

                cur.execute(
                    """
                    SELECT product_id
                    FROM user_product_scopes
                    WHERE user_id = %s
                    ORDER BY granted_at DESC
                    """,
                    (user_id,),
                )
                return [row[0] for row in cur.fetchall()]

    def get_accessible_projects(
        self,
        user_id: str,
        user: Optional[Dict] = None,
    ) -> List[str]:
        """
        获取用户可以访问的项目 ID 列表

        Args:
            user_id: 用户 ID
            user: 用户信息字典（可选）

        Returns:
            项目 ID 列表
        """
        if user is None:
            user = self.get_user_by_id(user_id)
        if not user:
            return []

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                if self._is_super_admin(user):
                    cur.execute(
                        """
                        SELECT project_id
                        FROM manage_projects
                        ORDER BY created_at DESC
                        """
                    )
                    return [row[0] for row in cur.fetchall()]

                cur.execute(
                    """
                    SELECT project_id
                    FROM user_project_scopes
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                explicit_project_ids = {row[0] for row in cur.fetchall()}

                product_ids = self.get_accessible_product_ids(user_id, user=user)
                derived_project_ids: Set[str] = set()
                if product_ids:
                    cur.execute(
                        """
                        SELECT project_id
                        FROM manage_projects
                        WHERE product_id = ANY(%s)
                        """,
                        (product_ids,),
                    )
                    derived_project_ids = {row[0] for row in cur.fetchall()}

                project_ids = explicit_project_ids | derived_project_ids
                return sorted(project_ids)

    def list_scope_options(self) -> Dict:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT product_id, name, status
                    FROM manage_products
                    WHERE status = 'active'
                    ORDER BY created_at DESC
                    """
                )
                products = [
                    {
                        "product_id": row[0],
                        "name": row[1],
                        "status": row[2],
                    }
                    for row in cur.fetchall()
                ]

                cur.execute(
                    """
                    SELECT project_id, name, status, product_id
                    FROM manage_projects
                    WHERE status = 'active'
                    ORDER BY created_at DESC
                    """
                )
                projects = [
                    {
                        "project_id": row[0],
                        "name": row[1],
                        "status": row[2],
                        "product_id": row[3],
                    }
                    for row in cur.fetchall()
                ]

        return {
            "products": products,
            "projects": projects,
        }

    def get_user_scopes(self, user_id: str) -> Dict:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT s.product_id, p.name, s.can_edit, s.granted_by, s.granted_at
                    FROM user_product_scopes s
                    JOIN manage_products p ON p.product_id = s.product_id
                    WHERE s.user_id = %s
                    ORDER BY p.name ASC
                    """,
                    (user_id,),
                )
                product_scopes = [
                    {
                        "product_id": row[0],
                        "product_name": row[1],
                        "can_edit": bool(row[2]),
                        "granted_by": row[3],
                        "granted_at": row[4].isoformat() if row[4] else None,
                    }
                    for row in cur.fetchall()
                ]

                cur.execute(
                    """
                    SELECT s.project_id, p.name, p.product_id, s.can_edit, s.granted_by, s.granted_at
                    FROM user_project_scopes s
                    JOIN manage_projects p ON p.project_id = s.project_id
                    WHERE s.user_id = %s
                    ORDER BY p.name ASC
                    """,
                    (user_id,),
                )
                project_scopes = [
                    {
                        "project_id": row[0],
                        "project_name": row[1],
                        "product_id": row[2],
                        "can_edit": bool(row[3]),
                        "granted_by": row[4],
                        "granted_at": row[5].isoformat() if row[5] else None,
                    }
                    for row in cur.fetchall()
                ]

        return {
            "product_scopes": product_scopes,
            "project_scopes": project_scopes,
        }

    def replace_user_scopes(
        self,
        user_id: str,
        product_scopes: List[Dict],
        project_scopes: List[Dict],
        granted_by: str,
    ) -> Dict:
        product_map: Dict[str, bool] = {}
        for item in product_scopes:
            product_id = str(item.get("product_id", "")).strip()
            if not product_id:
                continue
            product_map[product_id] = bool(item.get("can_edit", False))

        project_map: Dict[str, bool] = {}
        for item in project_scopes:
            project_id = str(item.get("project_id", "")).strip()
            if not project_id:
                continue
            project_map[project_id] = bool(item.get("can_edit", False))

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT user_id, role
                    FROM auth_users
                    WHERE user_id = %s
                    """,
                    (user_id,),
                )
                user_row = cur.fetchone()
                if not user_row:
                    raise ValueError("目标用户不存在")
                if user_row[1] == "super_admin":
                    raise ValueError("不能配置 super_admin 的可见范围")

                if product_map:
                    cur.execute(
                        """
                        SELECT product_id
                        FROM manage_products
                        WHERE product_id = ANY(%s)
                        """,
                        (list(product_map.keys()),),
                    )
                    existing_product_ids = {row[0] for row in cur.fetchall()}
                    invalid_product_ids = set(product_map.keys()) - existing_product_ids
                    if invalid_product_ids:
                        raise ValueError(
                            f"存在无效产品ID: {', '.join(sorted(invalid_product_ids))}"
                        )

                if project_map:
                    cur.execute(
                        """
                        SELECT project_id
                        FROM manage_projects
                        WHERE project_id = ANY(%s)
                        """,
                        (list(project_map.keys()),),
                    )
                    existing_project_ids = {row[0] for row in cur.fetchall()}
                    invalid_project_ids = set(project_map.keys()) - existing_project_ids
                    if invalid_project_ids:
                        raise ValueError(
                            f"存在无效项目ID: {', '.join(sorted(invalid_project_ids))}"
                        )

                cur.execute(
                    "DELETE FROM user_product_scopes WHERE user_id = %s",
                    (user_id,),
                )
                cur.execute(
                    "DELETE FROM user_project_scopes WHERE user_id = %s",
                    (user_id,),
                )

                for product_id, can_edit in product_map.items():
                    cur.execute(
                        """
                        INSERT INTO user_product_scopes (user_id, product_id, can_edit, granted_by, granted_at, updated_at)
                        VALUES (%s, %s, %s, %s, NOW(), NOW())
                        """,
                        (user_id, product_id, can_edit, granted_by),
                    )

                for project_id, can_edit in project_map.items():
                    cur.execute(
                        """
                        INSERT INTO user_project_scopes (user_id, project_id, can_edit, granted_by, granted_at, updated_at)
                        VALUES (%s, %s, %s, %s, NOW(), NOW())
                        """,
                        (user_id, project_id, can_edit, granted_by),
                    )

                conn.commit()

        return self.get_user_scopes(user_id)

    def grant_full_scopes_for_user(self, user_id: str, granted_by: Optional[str] = None) -> None:
        user = self.get_user_by_id(user_id)
        if not user:
            return
        if user.get("role") == "super_admin":
            return

        operator = granted_by or user_id
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_product_scopes (user_id, product_id, can_edit, granted_by, granted_at, updated_at)
                    SELECT %s, p.product_id, TRUE, %s, NOW(), NOW()
                    FROM manage_products p
                    ON CONFLICT (user_id, product_id) DO NOTHING
                    """,
                    (user_id, operator),
                )
                cur.execute(
                    """
                    INSERT INTO user_project_scopes (user_id, project_id, can_edit, granted_by, granted_at, updated_at)
                    SELECT %s, p.project_id, TRUE, %s, NOW(), NOW()
                    FROM manage_projects p
                    ON CONFLICT (user_id, project_id) DO NOTHING
                    """,
                    (user_id, operator),
                )
                conn.commit()

    def upsert_user_product_scope(
        self,
        user_id: str,
        product_id: str,
        can_edit: bool,
        granted_by: str,
    ) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_product_scopes (user_id, product_id, can_edit, granted_by, granted_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (user_id, product_id)
                    DO UPDATE SET
                        can_edit = EXCLUDED.can_edit,
                        granted_by = EXCLUDED.granted_by,
                        updated_at = NOW()
                    """,
                    (user_id, product_id, can_edit, granted_by),
                )
                conn.commit()

    def upsert_user_project_scope(
        self,
        user_id: str,
        project_id: str,
        can_edit: bool,
        granted_by: str,
    ) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_project_scopes (user_id, project_id, can_edit, granted_by, granted_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (user_id, project_id)
                    DO UPDATE SET
                        can_edit = EXCLUDED.can_edit,
                        granted_by = EXCLUDED.granted_by,
                        updated_at = NOW()
                    """,
                    (user_id, project_id, can_edit, granted_by),
                )
                conn.commit()

    def grant_project_scope_to_all_non_super_users(
        self,
        project_id: str,
        granted_by: str,
        can_edit: bool = True,
    ) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_project_scopes (user_id, project_id, can_edit, granted_by, granted_at, updated_at)
                    SELECT u.user_id, %s, %s, %s, NOW(), NOW()
                    FROM auth_users u
                    WHERE u.role <> 'super_admin'
                    ON CONFLICT (user_id, project_id)
                    DO UPDATE SET
                        can_edit = EXCLUDED.can_edit,
                        granted_by = EXCLUDED.granted_by,
                        updated_at = NOW()
                    """,
                    (project_id, can_edit, granted_by),
                )
                conn.commit()

    def grant_product_scope_to_all_non_super_users(
        self,
        product_id: str,
        granted_by: str,
        can_edit: bool = True,
    ) -> None:
        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO user_product_scopes (user_id, product_id, can_edit, granted_by, granted_at, updated_at)
                    SELECT u.user_id, %s, %s, %s, NOW(), NOW()
                    FROM auth_users u
                    WHERE u.role <> 'super_admin'
                    ON CONFLICT (user_id, product_id)
                    DO UPDATE SET
                        can_edit = EXCLUDED.can_edit,
                        granted_by = EXCLUDED.granted_by,
                        updated_at = NOW()
                    """,
                    (product_id, can_edit, granted_by),
                )
                conn.commit()

    def filter_requirements_by_permission(
        self,
        project_id: str,
        user_id: str,
        user: Optional[Dict] = None,
    ) -> Dict:
        """
        根据权限生成需求查询过滤条件

        Args:
            project_id: 项目 ID
            user_id: 用户 ID
            user: 用户信息字典（可选）

        Returns:
            包含 WHERE 条件和参数的字典
        """
        if user is None:
            user = self.get_user_by_id(user_id)

        if not user:
            return {
                "where_clause": "FALSE",
                "params": tuple(),
            }

        # 超级管理员可以看到所有需求
        if self.get_system_identity(user) == SYS_ADMIN:
            return {
                "where_clause": "project_id = %s AND deleted = FALSE",
                "params": (project_id,),
            }

        permissions = self.get_user_permissions(project_id, user_id, user)

        # 有查看权限可以看到所有
        if PERM_REQ_VIEW in permissions:
            return {
                "where_clause": "project_id = %s AND deleted = FALSE",
                "params": (project_id,),
            }

        visibility_conditions = []
        visibility_params: List[str] = []

        if PERM_REQ_VIEW_ASSIGNED in permissions:
            visibility_conditions.append("assignee = %s")
            visibility_params.append(user_id)

        if PERM_REQ_VIEW_SHARED in permissions:
            visibility_conditions.append("status IN (%s, %s)")
            visibility_params.extend(["confirmed", "completed"])

        if not visibility_conditions:
            return {
                "where_clause": "FALSE",
                "params": tuple(),
            }

        where_clause = (
            "project_id = %s AND deleted = FALSE AND ("
            + " OR ".join(visibility_conditions)
            + ")"
        )
        return {
            "where_clause": where_clause,
            "params": (project_id, *visibility_params),
        }
