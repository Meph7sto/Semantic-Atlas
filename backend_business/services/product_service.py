"""
产品管理服务
实现产品薄层：产品线、路线图与版本视角
支持"产品→多个项目"归属关系
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2 import IntegrityError
from psycopg2.extras import RealDictCursor


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


class ProductService:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(self.dsn)

    # ----------------------
    # Products CRUD
    # ----------------------
    def create_product(
        self,
        name: str,
        description: str = "",
        roadmap: str = "",
        version: str = "",
        tags: Optional[List[str]] = None,
        created_by: str = "",
    ) -> Dict[str, Any]:
        product_id = str(uuid.uuid4())
        tags_payload = json.dumps(tags or [])
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                try:
                    cur.execute(
                        """
                        INSERT INTO manage_products(
                            product_id, name, description, roadmap, version, tags,
                            created_by, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s, NOW(), NOW())
                        RETURNING product_id, name, description, status, roadmap, version, tags,
                                  created_by, created_at::text AS created_at, updated_at::text AS updated_at
                        """,
                        (
                            product_id,
                            name,
                            description,
                            roadmap,
                            version,
                            tags_payload,
                            created_by,
                        ),
                    )
                    product = dict(cur.fetchone())
                    if created_by:
                        # 约定：创建者默认成为 owner（用于产品级权限）
                        cur.execute(
                            """
                            INSERT INTO manage_product_members(product_id, user_id, role, created_at, updated_at)
                            VALUES (%s, %s, 'owner', NOW(), NOW())
                            ON CONFLICT (product_id, user_id) DO UPDATE SET role = 'owner', updated_at = NOW()
                            """,
                            (product_id, created_by),
                        )
                    return product
                except IntegrityError as e:
                    if "uk_manage_products_name" in str(e) or "unique" in str(e).lower():
                        raise ValueError(f"产品名称 '{name}' 已存在")
                    raise

    def get_member_role(self, product_id: str, user_id: str) -> Optional[str]:
        if not user_id:
            return None
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT role
                    FROM manage_product_members
                    WHERE product_id = %s AND user_id = %s
                    """,
                    (product_id, user_id),
                )
                row = cur.fetchone()
                return row.get("role") if row else None

    @staticmethod
    def can_write_product(global_role: str, member_role: Optional[str]) -> bool:
        if (global_role or "").lower() in ("super_admin", "admin"):
            return True
        return (member_role or "") in ("owner", "admin")

    def list_products(self, include_archived: bool = False) -> List[Dict[str, Any]]:
        where_clause = "" if include_archived else "WHERE status = 'active'"
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT product_id, name, description, status, roadmap, version, tags,
                           created_by, created_at::text AS created_at, updated_at::text AS updated_at
                    FROM manage_products
                    {where_clause}
                    ORDER BY created_at DESC
                    """
                )
                return [dict(row) for row in cur.fetchall()]

    def get_product(self, product_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT product_id, name, description, status, roadmap, version, tags,
                           created_by, created_at::text AS created_at, updated_at::text AS updated_at
                    FROM manage_products
                    WHERE product_id = %s
                    """,
                    (product_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_product(
        self, product_id: str, fields: Dict[str, Any], updated_by: str = ""
    ) -> Dict[str, Any]:
        allowed = {"name", "description", "status", "roadmap", "version", "tags"}
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            raise ValueError("没有可更新字段")

        set_clauses = []
        values = []
        for key, value in updates.items():
            if key == "tags":
                set_clauses.append(f"{key} = %s::jsonb")
                values.append(json.dumps(value or []))
            else:
                set_clauses.append(f"{key} = %s")
                values.append(value)

        set_clauses.append("updated_at = NOW()")
        values.append(product_id)

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    UPDATE manage_products
                    SET {", ".join(set_clauses)}
                    WHERE product_id = %s
                    RETURNING product_id, name, description, status, roadmap, version, tags,
                              created_by, created_at::text AS created_at, updated_at::text AS updated_at
                    """,
                    values,
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError("产品不存在")
                return dict(row)

    def delete_product(self, product_id: str) -> int:
        """软删除：将产品状态设为 archived"""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE manage_products
                    SET status = 'archived', updated_at = NOW()
                    WHERE product_id = %s AND status = 'active'
                    """,
                    (product_id,),
                )
                return cur.rowcount

    # ----------------------
    # Product Members
    # ----------------------
    def add_member(
        self,
        product_id: str,
        user_id: str,
        role: str = "member",
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO manage_product_members(product_id, user_id, role, created_at, updated_at)
                    VALUES (%s, %s, %s, NOW(), NOW())
                    ON CONFLICT (product_id, user_id) DO UPDATE SET role = %s, updated_at = NOW()
                    RETURNING id, product_id, user_id, role, created_at::text AS created_at
                    """,
                    (product_id, user_id, role, role),
                )
                return dict(cur.fetchone())

    def remove_member(self, product_id: str, user_id: str) -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    DELETE FROM manage_product_members
                    WHERE product_id = %s AND user_id = %s
                    """,
                    (product_id, user_id),
                )
                return cur.rowcount

    def list_members(self, product_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT id, product_id, user_id, role, created_at::text AS created_at
                    FROM manage_product_members
                    WHERE product_id = %s
                    ORDER BY created_at ASC
                    """,
                    (product_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    # ----------------------
    # Product-Project Relations
    # ----------------------
    def list_projects_by_product(self, product_id: str) -> List[Dict[str, Any]]:
        """列出某产品下的所有项目"""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT project_id, name, description, status, product_id,
                           created_by, created_at::text AS created_at, updated_at::text AS updated_at
                    FROM manage_projects
                    WHERE product_id = %s
                    ORDER BY created_at DESC
                    """,
                    (product_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def bind_project_to_product(
        self, project_id: str, product_id: Optional[str]
    ) -> Dict[str, Any]:
        """将项目绑定到产品（或解绑：product_id=None）"""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE manage_projects
                    SET product_id = %s, updated_at = NOW()
                    WHERE project_id = %s
                    RETURNING project_id, name, description, status, product_id,
                              created_by, created_at::text AS created_at, updated_at::text AS updated_at
                    """,
                    (product_id, project_id),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError("项目不存在")
                return dict(row)

    def create_project_under_product(
        self,
        product_id: str,
        name: str,
        description: str = "",
        created_by: str = "",
    ) -> Dict[str, Any]:
        """在产品下创建新项目"""
        project_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 验证产品存在
                cur.execute(
                    "SELECT product_id FROM manage_products WHERE product_id = %s AND status = 'active'",
                    (product_id,),
                )
                if not cur.fetchone():
                    raise ValueError("产品不存在或已归档")

                try:
                    cur.execute(
                        """
                        INSERT INTO manage_projects(
                            project_id, name, description, product_id, created_by, created_at, updated_at
                        )
                        VALUES (%s, %s, %s, %s, %s, NOW(), NOW())
                        RETURNING project_id, name, description, status, product_id,
                                  created_by, created_at::text AS created_at, updated_at::text AS updated_at
                        """,
                        (project_id, name, description, product_id, created_by),
                    )
                    project = dict(cur.fetchone())

                    # 为新项目创建默认 main 分支引用
                    cur.execute(
                        """
                        INSERT INTO manage_branch_refs (ref_id, project_id, ref_name, ref_type, milestone_id, created_by, created_at, updated_at)
                        VALUES (%s, %s, %s, 'branch', NULL, %s, NOW(), NOW())
                        ON CONFLICT (project_id, ref_name) DO NOTHING
                        """,
                        (str(uuid.uuid4()), project_id, "main", created_by),
                    )
                    return project
                except IntegrityError as e:
                    if "uk_manage_projects_name" in str(e) or "unique" in str(e).lower():
                        raise ValueError(f"项目名称 '{name}' 已存在")
                    raise

    # ----------------------
    # Product Overview (聚合查看)
    # ----------------------
    def get_product_overview(self, product_id: str) -> Dict[str, Any]:
        """获取产品概览：包含项目数量、需求统计、里程碑/基线统计"""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 获取产品信息
                cur.execute(
                    """
                    SELECT product_id, name, description, status, roadmap, version, tags,
                           created_by, created_at::text AS created_at
                    FROM manage_products
                    WHERE product_id = %s
                    """,
                    (product_id,),
                )
                product = cur.fetchone()
                if not product:
                    raise ValueError("产品不存在")

                # 项目统计
                cur.execute(
                    """
                    SELECT COUNT(*) as total,
                           SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) as active,
                           SUM(CASE WHEN status = 'archived' THEN 1 ELSE 0 END) as archived
                    FROM manage_projects
                    WHERE product_id = %s
                    """,
                    (product_id,),
                )
                project_stats = dict(cur.fetchone())

                # 需求统计（跨项目聚合）
                cur.execute(
                    """
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN r.requirement_type = 'top_level' THEN 1 ELSE 0 END) as top_level,
                        SUM(CASE WHEN r.requirement_type = 'low_level' THEN 1 ELSE 0 END) as low_level,
                        SUM(CASE WHEN r.requirement_type = 'task' THEN 1 ELSE 0 END) as task,
                        SUM(CASE WHEN r.status = 'draft' THEN 1 ELSE 0 END) as draft,
                        SUM(CASE WHEN r.status = 'confirmed' THEN 1 ELSE 0 END) as confirmed,
                        SUM(CASE WHEN r.status = 'in_progress' THEN 1 ELSE 0 END) as in_progress,
                        SUM(CASE WHEN r.status = 'completed' THEN 1 ELSE 0 END) as completed
                    FROM manage_requirements r
                    JOIN manage_projects p ON r.project_id = p.project_id
                    WHERE p.product_id = %s AND r.deleted = FALSE
                    """,
                    (product_id,),
                )
                req_stats = dict(cur.fetchone())

                # 里程碑统计
                cur.execute(
                    """
                    SELECT 
                        COUNT(*) as total,
                        SUM(CASE WHEN m.is_baseline THEN 1 ELSE 0 END) as baselines
                    FROM manage_milestones m
                    JOIN manage_projects p ON m.project_id = p.project_id
                    WHERE p.product_id = %s
                    """,
                    (product_id,),
                )
                milestone_stats = dict(cur.fetchone())

                return {
                    "product": dict(product),
                    "stats": {
                        "projects": project_stats,
                        "requirements": req_stats,
                        "milestones": milestone_stats,
                    },
                }

    def list_requirements_by_product(
        self, product_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        """按产品聚合查看所有需求"""
        where_deleted = "" if include_deleted else "AND r.deleted = FALSE"
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT r.req_id, r.project_id, p.name as project_name,
                           r.requirement_type, r.status, r.title, r.description,
                           r.priority, r.assignee, r.tags, r.due_date, r.parent_id,
                           r.order_index, r.created_by, r.created_at::text AS created_at
                    FROM manage_requirements r
                    JOIN manage_projects p ON r.project_id = p.project_id
                    WHERE p.product_id = %s {where_deleted}
                    ORDER BY p.name, r.order_index ASC, r.created_at DESC
                    """,
                    (product_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def list_milestones_by_product(self, product_id: str) -> List[Dict[str, Any]]:
        """按产品聚合查看所有里程碑"""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT m.milestone_id, m.project_id, p.name as project_name,
                           m.name, m.description, m.message, m.milestone_type,
                           m.is_baseline, m.sprint, m.version, m.tags,
                           m.created_by, m.created_at::text AS created_at
                    FROM manage_milestones m
                    JOIN manage_projects p ON m.project_id = p.project_id
                    WHERE p.product_id = %s
                    ORDER BY p.name, m.created_at DESC
                    """,
                    (product_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def list_baselines_by_product(self, product_id: str) -> List[Dict[str, Any]]:
        """按产品聚合查看所有基线"""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT m.milestone_id, m.project_id, p.name as project_name,
                           m.name, m.description, m.version, m.tags,
                           m.created_by, m.created_at::text AS created_at
                    FROM manage_milestones m
                    JOIN manage_projects p ON m.project_id = p.project_id
                    WHERE p.product_id = %s AND m.is_baseline = TRUE
                    ORDER BY m.created_at DESC
                    """,
                    (product_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    # ----------------------
    # Audit Logging
    # ----------------------
    def add_audit_log(
        self,
        product_id: Optional[str],
        actor: str,
        action: str,
        target_type: str,
        target_id: str,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        log_id = str(uuid.uuid4())
        detail_payload = json.dumps(detail or {})
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO manage_audit_logs(log_id, project_id, product_id, actor, action, target_type, target_id, detail, created_at)
                    VALUES (%s, NULL, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                    """,
                    (
                        log_id,
                        product_id,
                        actor,
                        action,
                        target_type,
                        target_id,
                        detail_payload,
                    ),
                )
