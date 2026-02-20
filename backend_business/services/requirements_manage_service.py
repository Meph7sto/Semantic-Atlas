"""
需求管理监控服务
基于 requirements_l123 及新增 manage_* 表实现需求树、里程碑、分支与审计
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2.extras import RealDictCursor


def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


_ALLOWED_PRIORITIES = {"low", "medium", "high"}


def normalize_priority(priority: Any, allow_none: bool = True) -> Optional[str]:
    """Normalize priority values to low/medium/high."""
    if priority is None:
        return None if allow_none else "medium"

    text = str(priority).strip()
    if not text:
        return None if allow_none else "medium"

    normalized = text.lower()
    if normalized in _ALLOWED_PRIORITIES:
        return normalized
    raise ValueError("priority 必须是 low、medium、high")


class RequirementsManageService:
    def __init__(self, dsn: str):
        self.dsn = dsn

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(self.dsn)

    # ----------------------
    # Projects
    # ----------------------
    def create_project(
        self, name: str, description: str = "", created_by: str = ""
    ) -> Dict[str, Any]:
        project_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO manage_projects(project_id, name, description, created_by, created_at, updated_at)
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    RETURNING project_id, name, description, status, product_id, current_session_id, created_by, created_at::text AS created_at
                    """,
                    (project_id, name, description, created_by),
                )
                project = dict(cur.fetchone())
                cur.execute(
                    """
                    INSERT INTO manage_branch_refs (ref_id, project_id, ref_name, ref_type, milestone_id, created_by, created_at, updated_at)
                    VALUES (%s, %s, %s, 'branch', NULL, %s, NOW(), NOW())
                    ON CONFLICT (project_id, ref_name) DO NOTHING
                    """,
                    (str(uuid.uuid4()), project_id, "main", created_by),
                )
                return project

    def list_projects(self) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT project_id, name, description, status, product_id, current_session_id, created_by, created_at::text AS created_at
                    FROM manage_projects
                    ORDER BY created_at DESC
                    """
                )
                return [dict(row) for row in cur.fetchall()]

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT project_id, name, description, status, product_id, current_session_id, created_by, created_at::text AS created_at
                    FROM manage_projects
                    WHERE project_id = %s
                    """,
                    (project_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def set_project_session(
        self, project_id: str, session_id: str, updated_by: str = ""
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    UPDATE manage_projects
                    SET current_session_id = %s, updated_at = NOW()
                    WHERE project_id = %s
                    RETURNING project_id, name, description, status, product_id, current_session_id, created_by, created_at::text AS created_at
                    """,
                    (session_id, project_id),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError("项目不存在")
                return dict(row)

    def update_project_info(
        self,
        project_id: str,
        name: str = None,
        description: str = None,
        updated_by: str = "",
    ) -> Dict[str, Any]:
        fields = []
        values = []
        if name is not None:
            fields.append("name = %s")
            values.append(name)
        if description is not None:
            fields.append("description = %s")
            values.append(description)
        if not fields:
            return self.get_project(project_id)
        fields.append("updated_at = NOW()")
        values.append(project_id)
        sql = (
            f"UPDATE manage_projects SET {', '.join(fields)} WHERE project_id = %s"
            " RETURNING project_id, name, description, status, product_id, current_session_id, created_by, created_at::text AS created_at"
        )
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, values)
                row = cur.fetchone()
                if not row:
                    raise ValueError("项目不存在")
                return dict(row)

    def archive_project(self, project_id: str, updated_by: str = "") -> int:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE manage_projects
                    SET status = 'archived', updated_at = NOW()
                    WHERE project_id = %s AND status != 'archived'
                    """,
                    (project_id,),
                )
                return cur.rowcount

    # ----------------------
    # Requirements
    # ----------------------
    @staticmethod
    def _can_have_child(parent_type: str, child_type: str) -> bool:
        rules = {
            "top_level": {"low_level", "task"},
            "low_level": {"task"},
            "task": set(),
        }
        return child_type in rules.get(parent_type, set())

    def create_requirement(
        self,
        project_id: str,
        requirement_type: str,
        title: str,
        description: str = "",
        status: str = "draft",
        parent_id: Optional[str] = None,
        order_index: int = 0,
        priority: Optional[str] = None,
        assignee: Optional[str] = None,
        tags: Optional[List[str]] = None,
        due_date: Optional[str] = None,
        created_by: str = "",
        source_req_id: Optional[str] = None,
        source_level: Optional[str] = None,
        custom_fields: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        req_id = str(uuid.uuid4())
        priority = normalize_priority(priority, allow_none=True)
        tags_payload = json.dumps(tags or [])
        custom_payload = json.dumps(custom_fields or {})

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if parent_id:
                    cur.execute(
                        """
                        SELECT req_id, requirement_type, project_id
                        FROM manage_requirements
                        WHERE req_id = %s AND deleted = FALSE
                        """,
                        (parent_id,),
                    )
                    parent = cur.fetchone()
                    if not parent:
                        raise ValueError("父节点不存在")
                    if parent["project_id"] != project_id:
                        raise ValueError("父节点不属于当前项目")
                    if not self._can_have_child(
                        parent["requirement_type"], requirement_type
                    ):
                        raise ValueError("不符合层级规则")

                cur.execute(
                    """
                    INSERT INTO manage_requirements (
                        req_id, project_id, requirement_type, status, title, description,
                        priority, assignee, tags, due_date, parent_id, order_index,
                        source_req_id, source_level, custom_fields,
                        created_by, created_at, updated_by, updated_at, deleted
                    )
                    VALUES (
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s::jsonb, %s, %s, %s,
                        %s, %s, %s::jsonb,
                        %s, NOW(), %s, NOW(), FALSE
                    )
                    RETURNING req_id, project_id, requirement_type, status, title, description,
                              priority, assignee, tags, due_date, parent_id, order_index,
                              source_req_id, source_level, custom_fields, created_by,
                              created_at::text AS created_at, updated_by, updated_at::text AS updated_at, is_planned
                    """,
                    (
                        req_id,
                        project_id,
                        requirement_type,
                        status,
                        title,
                        description,
                        priority,
                        assignee,
                        tags_payload,
                        due_date,
                        parent_id,
                        int(order_index),
                        source_req_id,
                        source_level,
                        custom_payload,
                        created_by,
                        created_by,
                    ),
                )
                return dict(cur.fetchone())

    def list_requirements(
        self, project_id: str, include_deleted: bool = False
    ) -> List[Dict[str, Any]]:
        where_clause = "" if include_deleted else "AND deleted = FALSE"
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT req_id, project_id, requirement_type, status, title, description,
                           priority, assignee, tags, due_date, parent_id, order_index,
                           source_req_id, source_level, custom_fields, created_by,
                           created_at::text AS created_at, updated_by, updated_at::text AS updated_at, deleted, is_planned
                    FROM manage_requirements
                    WHERE project_id = %s {where_clause}
                    ORDER BY order_index ASC, created_at DESC
                    """,
                    (project_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def get_requirement(self, req_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, project_id, requirement_type, status, title, description,
                           priority, assignee, tags, due_date, parent_id, order_index,
                           source_req_id, source_level, custom_fields, created_by,
                           created_at::text AS created_at, updated_by, updated_at::text AS updated_at, deleted, is_planned
                    FROM manage_requirements
                    WHERE req_id = %s
                    """,
                    (req_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_requirement(
        self, req_id: str, fields: Dict[str, Any], updated_by: str = ""
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
        if "priority" in updates:
            updates["priority"] = normalize_priority(updates.get("priority"), allow_none=True)

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

        with self._connect() as conn:
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

    def bulk_update_requirement_status(
        self, req_ids: List[str], status: str, updated_by: str = ""
    ) -> Dict[str, Any]:
        if not req_ids:
            raise ValueError("缺少需求ID列表")
        allowed_status = {
            "draft",
            "under_review",
            "confirmed",
            "in_progress",
            "completed",
            "archived",
        }
        if status not in allowed_status:
            raise ValueError("非法状态")

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, requirement_type
                    FROM manage_requirements
                    WHERE req_id = ANY(%s)
                    """,
                    (req_ids,),
                )
                rows = cur.fetchall()
                low_level_ids = [
                    r["req_id"] for r in rows if r["requirement_type"] == "low_level"
                ]
                skipped = len(req_ids) - len(low_level_ids)

                if not low_level_ids:
                    return {"updated": 0, "skipped": skipped}

                cur.execute(
                    """
                    UPDATE manage_requirements
                    SET status = %s, updated_by = %s, updated_at = NOW()
                    WHERE req_id = ANY(%s)
                      AND deleted = FALSE
                      AND requirement_type = 'low_level'
                    """,
                    (status, updated_by, low_level_ids),
                )
                return {"updated": cur.rowcount, "skipped": skipped}

    def move_requirement(
        self,
        req_id: str,
        new_parent_id: Optional[str],
        new_order: int = 0,
        updated_by: str = "",
    ) -> None:
        requirement = self.get_requirement(req_id)
        if not requirement:
            raise ValueError("需求不存在")

        if new_parent_id:
            parent = self.get_requirement(new_parent_id)
            if not parent:
                raise ValueError("父节点不存在")
            if parent["project_id"] != requirement["project_id"]:
                raise ValueError("父节点不属于当前项目")
            if not self._can_have_child(
                parent["requirement_type"], requirement["requirement_type"]
            ):
                raise ValueError("不符合层级规则")

            tree, _ = self.get_requirement_tree(requirement["project_id"])
            if self._is_descendant(tree, req_id, new_parent_id):
                raise ValueError("不能移动到自己的后代节点")

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE manage_requirements
                    SET parent_id = %s, order_index = %s, updated_by = %s, updated_at = NOW()
                    WHERE req_id = %s
                    """,
                    (new_parent_id, int(new_order), updated_by, req_id),
                )
                if cur.rowcount == 0:
                    raise ValueError("需求不存在")

    def delete_requirement(
        self, req_id: str, cascade: bool = False, updated_by: str = ""
    ) -> int:
        requirement = self.get_requirement(req_id)
        if not requirement:
            raise ValueError("需求不存在")

        targets = [req_id]
        if cascade:
            tree, _ = self.get_requirement_tree(
                requirement["project_id"], include_deleted=True
            )
            targets = self._collect_descendants(tree, req_id)

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE manage_requirements
                    SET deleted = TRUE, updated_by = %s, updated_at = NOW()
                    WHERE req_id = ANY(%s)
                    """,
                    (updated_by, targets),
                )
                return cur.rowcount

    def get_requirement_tree(
        self, project_id: str, include_deleted: bool = False
    ) -> Tuple[List[Dict[str, Any]], List[str]]:
        requirements = self.list_requirements(
            project_id, include_deleted=include_deleted
        )
        node_map: Dict[str, Dict[str, Any]] = {}
        for req in requirements:
            node_map[req["req_id"]] = {"requirement": req, "children": []}

        roots: List[Dict[str, Any]] = []
        orphans: List[str] = []
        for req in requirements:
            parent_id = req.get("parent_id")
            node = node_map[req["req_id"]]
            if parent_id and parent_id in node_map:
                node_map[parent_id]["children"].append(node)
            elif parent_id:
                orphans.append(req["req_id"])
                roots.append(node)
            else:
                roots.append(node)

        for node in node_map.values():
            node["children"].sort(key=lambda x: x["requirement"].get("order_index", 0))

        roots.sort(key=lambda x: x["requirement"].get("order_index", 0))
        return roots, orphans

    @staticmethod
    def _collect_descendants(tree: List[Dict[str, Any]], target_id: str) -> List[str]:
        result: List[str] = []

        def dfs(node: Dict[str, Any], collecting: bool = False) -> None:
            req_id = node["requirement"]["req_id"]
            is_target = req_id == target_id
            if collecting or is_target:
                result.append(req_id)
                collecting = True
            for child in node.get("children", []):
                dfs(child, collecting)

        for root in tree:
            dfs(root, False)
        return result

    @staticmethod
    def _is_descendant(
        tree: List[Dict[str, Any]], ancestor_id: str, maybe_descendant_id: str
    ) -> bool:
        found = False

        def dfs(node: Dict[str, Any]) -> bool:
            req_id = node["requirement"]["req_id"]
            if req_id == ancestor_id:
                return _search(node, maybe_descendant_id)
            for child in node.get("children", []):
                if dfs(child):
                    return True
            return False

        def _search(node: Dict[str, Any], target: str) -> bool:
            for child in node.get("children", []):
                if child["requirement"]["req_id"] == target:
                    return True
                if _search(child, target):
                    return True
            return False

        found = dfs({"requirement": {"req_id": ""}, "children": tree})
        return found

    # ----------------------
    # Import from Session
    # ----------------------
    def import_from_session(
        self,
        session_id: str,
        project_id: str,
        created_by: str = "",
        mapping_mode: str = "tree",
    ) -> Dict[str, Any]:
        level_map = {
            "L1": "top_level",
            "L2": "top_level",
            "L3": "top_level",
            "L4": "low_level",
            "L5": "task",
        }
        inserted_l123 = 0
        inserted_l4 = 0
        level_counts: Dict[str, int] = {}
        unlinked_l4 = 0
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, source_req_id, requirement_type, parent_id
                    FROM manage_requirements
                    WHERE project_id = %s AND deleted = FALSE
                    """,
                    (project_id,),
                )
                existing_rows = cur.fetchall()
                existing_by_source = {
                    row["source_req_id"]: row["req_id"]
                    for row in existing_rows
                    if row.get("source_req_id")
                }

                cur.execute(
                    """
                    SELECT req_id, level, text, created_at
                    FROM requirements_l123
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                )
                rows = cur.fetchall()

                for row in rows:
                    level = row.get("level") or ""
                    level_counts[level] = level_counts.get(level, 0) + 1

                for row in rows:
                    level = row.get("level") or ""
                    if level == "L4":
                        # L4 需求优先从 low_level_requirements 导入
                        continue

                    req_type = level_map.get(level, "low_level")
                    source_req_id = row["req_id"]
                    if source_req_id in existing_by_source:
                        continue

                    title = (row.get("text") or "").strip()
                    cur.execute(
                        """
                        INSERT INTO manage_requirements (
                            req_id, project_id, requirement_type, status, title, description,
                            priority, assignee, tags, due_date, parent_id, order_index,
                            source_req_id, source_level, custom_fields,
                            created_by, created_at, updated_by, updated_at, deleted
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s::jsonb, %s, %s, %s,
                            %s, %s, %s::jsonb,
                            %s, NOW(), %s, NOW(), FALSE
                        )
                        ON CONFLICT (req_id) DO NOTHING
                        """,
                        (
                            str(uuid.uuid4()),
                            project_id,
                            req_type,
                            "draft",
                            title,
                            "",
                            None,
                            None,
                            json.dumps([]),
                            None,
                            None,
                            0,
                            source_req_id,
                            level,
                            json.dumps({"source": "requirements_l123"}),
                            created_by,
                            created_by,
                        ),
                    )
                    if cur.rowcount > 0:
                        inserted_l123 += 1

                # 刷新 source_req_id -> manage req_id 映射（用于 L4 绑定）
                cur.execute(
                    """
                    SELECT req_id, source_req_id
                    FROM manage_requirements
                    WHERE project_id = %s AND deleted = FALSE AND source_req_id IS NOT NULL
                    """,
                    (project_id,),
                )
                existing_by_source = {
                    row["source_req_id"]: row["req_id"]
                    for row in cur.fetchall()
                    if row.get("source_req_id")
                }

                # 读取 L4 需求与映射关系
                cur.execute(
                    """
                    SELECT req_id, source_top_id, source_top_text, text, component, created_at
                    FROM low_level_requirements
                    WHERE session_id = %s
                    ORDER BY created_at ASC
                    """,
                    (session_id,),
                )
                l4_rows = cur.fetchall()
                level_counts["L4"] = len(l4_rows)

                cur.execute(
                    """
                    SELECT req_id, top_req_id
                    FROM low_level_requirement_links
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                link_rows = cur.fetchall()
                link_map: Dict[str, List[str]] = {}
                for row in link_rows:
                    link_map.setdefault(row["req_id"], []).append(row["top_req_id"])

                for row in l4_rows:
                    source_req_id = row["req_id"]
                    if source_req_id in existing_by_source:
                        # 尝试补齐 parent_id
                        if mapping_mode != "flat":
                            top_ids = link_map.get(source_req_id) or []
                            if not top_ids and row.get("source_top_id"):
                                top_ids = [row.get("source_top_id")]
                            parent_id = None
                            for top_id in top_ids:
                                parent_id = existing_by_source.get(top_id)
                                if parent_id:
                                    break
                            if parent_id:
                                cur.execute(
                                    """
                                    UPDATE manage_requirements
                                    SET parent_id = %s, updated_at = NOW()
                                    WHERE project_id = %s AND source_req_id = %s AND parent_id IS NULL
                                    """,
                                    (parent_id, project_id, source_req_id),
                                )
                            else:
                                unlinked_l4 += 1
                        continue

                    parent_id = None
                    if mapping_mode != "flat":
                        top_ids = link_map.get(source_req_id) or []
                        if not top_ids and row.get("source_top_id"):
                            top_ids = [row.get("source_top_id")]
                        for top_id in top_ids:
                            parent_id = existing_by_source.get(top_id)
                            if parent_id:
                                break
                        if not parent_id:
                            unlinked_l4 += 1

                    title = (row.get("text") or "").strip()
                    cur.execute(
                        """
                        INSERT INTO manage_requirements (
                            req_id, project_id, requirement_type, status, title, description,
                            priority, assignee, tags, due_date, parent_id, order_index,
                            source_req_id, source_level, custom_fields,
                            created_by, created_at, updated_by, updated_at, deleted
                        )
                        VALUES (
                            %s, %s, %s, %s, %s, %s,
                            %s, %s, %s::jsonb, %s, %s, %s,
                            %s, %s, %s::jsonb,
                            %s, NOW(), %s, NOW(), FALSE
                        )
                        ON CONFLICT (req_id) DO NOTHING
                        """,
                        (
                            str(uuid.uuid4()),
                            project_id,
                            "low_level",
                            "draft",
                            title,
                            "",
                            None,
                            None,
                            json.dumps([]),
                            None,
                            parent_id,
                            0,
                            source_req_id,
                            "L4",
                            json.dumps(
                                {
                                    "source": "low_level_requirements",
                                    "source_top_id": row.get("source_top_id"),
                                    "source_top_text": row.get("source_top_text"),
                                    "component": row.get("component"),
                                }
                            ),
                            created_by,
                            created_by,
                        ),
                    )
                    if cur.rowcount > 0:
                        inserted_l4 += 1
        l4_total = level_counts.get("L4", 0)
        top_level_total = sum(
            level_counts.get(level, 0) for level in ("L1", "L2", "L3")
        )
        total = sum(level_counts.values())
        return {
            "inserted": inserted_l123 + inserted_l4,
            "inserted_l123": inserted_l123,
            "inserted_l4": inserted_l4,
            "total": total,
            "mapping_mode": mapping_mode,
            "stats": {
                "by_level": level_counts,
                "top_level_total": top_level_total,
                "low_level_total": l4_total,
                "unlinked_l4": unlinked_l4,
            },
        }

    # Backward-compatible alias: historically named import_from_l123.
    def import_from_l123(
        self,
        session_id: str,
        project_id: str,
        created_by: str = "",
        mapping_mode: str = "tree",
    ) -> Dict[str, Any]:
        return self.import_from_session(
            session_id=session_id,
            project_id=project_id,
            created_by=created_by,
            mapping_mode=mapping_mode,
        )

    # ----------------------
    # Test cases & binding
    # ----------------------
    def create_test_case(
        self,
        project_id: str,
        title: str,
        description: str = "",
        status: str = "draft",
        source: str = "",
        created_by: str = "",
    ) -> Dict[str, Any]:
        test_case_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO manage_test_cases(test_case_id, project_id, title, description, status, source, created_by, created_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
                    RETURNING test_case_id, project_id, title, description, status, source, created_by, created_at::text AS created_at
                    """,
                    (
                        test_case_id,
                        project_id,
                        title,
                        description,
                        status,
                        source,
                        created_by,
                    ),
                )
                return dict(cur.fetchone())

    def list_test_cases(self, project_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT test_case_id, project_id, title, description, status, source, created_by, created_at::text AS created_at
                    FROM manage_test_cases
                    WHERE project_id = %s
                    ORDER BY created_at DESC
                    """,
                    (project_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def bind_test_case(
        self, requirement_id: str, test_case_id: str, link_type: str = "verification"
    ) -> None:
        req = self.get_requirement(requirement_id)
        if not req:
            raise ValueError("需求不存在")
        if req["requirement_type"] != "low_level":
            raise ValueError("仅允许绑定到底层需求")

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO manage_requirement_test_links(requirement_id, test_case_id, link_type, created_at)
                    VALUES (%s, %s, %s, NOW())
                    ON CONFLICT (requirement_id, test_case_id) DO NOTHING
                    """,
                    (requirement_id, test_case_id, link_type),
                )

    # ----------------------
    # Milestones
    # ----------------------
    def create_milestone(
        self,
        project_id: str,
        name: str,
        message: str,
        created_by: str,
        milestone_type: str = "regular",
        is_baseline: bool = False,
        sprint: Optional[str] = None,
        version: Optional[str] = None,
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
        branch_name: Optional[str] = None,
        parent_milestone_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        milestone_id = str(uuid.uuid4())
        tags_payload = json.dumps(tags or [])
        metadata_dict = dict(metadata or {})
        if branch_name:
            metadata_dict.setdefault("branch_name", branch_name)
        metadata_payload = json.dumps(metadata_dict)

        requirements = self.list_requirements(project_id, include_deleted=False)
        if not requirements:
            raise ValueError("当前项目没有可用需求")

        top_level_ids = {
            r["req_id"]
            for r in requirements
            if r.get("requirement_type") == "top_level"
        }
        low_level_reqs = [
            r for r in requirements if r.get("requirement_type") == "low_level"
        ]
        if not top_level_ids or not low_level_reqs:
            raise ValueError("里程碑至少需要包含顶层与底层需求")

        unlinked_l4 = [
            r for r in low_level_reqs if r.get("parent_id") not in top_level_ids
        ]
        if unlinked_l4:
            raise ValueError("存在未挂接到顶层需求的底层需求")

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if branch_name:
                    cur.execute(
                        """
                        SELECT ref_name, milestone_id
                        FROM manage_branch_refs
                        WHERE project_id = %s AND ref_name = %s
                        """,
                        (project_id, branch_name),
                    )
                    ref_row = cur.fetchone()
                    if not ref_row:
                        raise ValueError("分支不存在")
                    if not parent_milestone_id:
                        parent_milestone_id = ref_row["milestone_id"]

                if not parent_milestone_id:
                    cur.execute(
                        """
                        SELECT milestone_id
                        FROM manage_milestones
                        WHERE project_id = %s
                        ORDER BY created_at DESC
                        LIMIT 1
                        """,
                        (project_id,),
                    )
                    latest_row = cur.fetchone()
                    if latest_row:
                        parent_milestone_id = latest_row["milestone_id"]

                if is_baseline:
                    cur.execute(
                        """
                        UPDATE manage_milestones
                        SET is_baseline = FALSE
                        WHERE project_id = %s
                        """,
                        (project_id,),
                    )

                cur.execute(
                    """
                    INSERT INTO manage_milestones (
                        milestone_id, project_id, name, description, message,
                        milestone_type, is_baseline, sprint, version, tags, created_by, created_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, NOW(), %s::jsonb)
                    RETURNING milestone_id, project_id, name, description, message,
                              milestone_type, is_baseline, sprint, version, tags, created_by, created_at::text AS created_at, metadata
                    """,
                    (
                        milestone_id,
                        project_id,
                        name,
                        "",
                        message,
                        milestone_type,
                        is_baseline,
                        sprint,
                        version,
                        tags_payload,
                        created_by,
                        metadata_payload,
                    ),
                )
                milestone = dict(cur.fetchone())

                if parent_milestone_id:
                    cur.execute(
                        """
                        INSERT INTO manage_milestone_edges (
                            project_id, from_milestone_id, to_milestone_id, relation_type, message, created_by, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, NOW())
                        """,
                        (
                            project_id,
                            parent_milestone_id,
                            milestone_id,
                            "commit",
                            "branch-commit" if branch_name else "milestone-commit",
                            created_by,
                        ),
                    )

                if branch_name:
                    cur.execute(
                        """
                        UPDATE manage_branch_refs
                        SET milestone_id = %s, updated_at = NOW()
                        WHERE project_id = %s AND ref_name = %s
                        """,
                        (milestone_id, project_id, branch_name),
                    )

                for req in requirements:
                    snapshot_id = str(uuid.uuid4())
                    snapshot_data = json.dumps(req)
                    cur.execute(
                        """
                        INSERT INTO manage_milestone_nodes (
                            snapshot_id, milestone_id, requirement_id, requirement_type,
                            status, title, description, parent_id, order_index, snapshot_data, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                        """,
                        (
                            snapshot_id,
                            milestone_id,
                            req["req_id"],
                            req["requirement_type"],
                            req["status"],
                            req["title"],
                            req.get("description"),
                            req.get("parent_id"),
                            req.get("order_index", 0),
                            snapshot_data,
                        ),
                    )

                    if req.get("parent_id"):
                        cur.execute(
                            """
                            INSERT INTO manage_milestone_relations (milestone_id, parent_id, child_id, order_index)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (
                                milestone_id,
                                req["parent_id"],
                                req["req_id"],
                                req.get("order_index", 0),
                            ),
                        )

                return milestone

    def list_milestones(self, project_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT milestone_id, project_id, name, description, message,
                           milestone_type, is_baseline, sprint, version, tags, created_by, created_at::text AS created_at, metadata
                    FROM manage_milestones
                    WHERE project_id = %s
                    ORDER BY created_at DESC
                    """,
                    (project_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def get_milestone(
        self, milestone_id: str, include_nodes: bool = True
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT milestone_id, project_id, name, description, message,
                           milestone_type, is_baseline, sprint, version, tags, created_by, created_at::text AS created_at, metadata
                    FROM manage_milestones
                    WHERE milestone_id = %s
                    """,
                    (milestone_id,),
                )
                milestone = cur.fetchone()
                if not milestone:
                    return None

                result = dict(milestone)
                if include_nodes:
                    cur.execute(
                        """
                        SELECT snapshot_id, milestone_id, requirement_id, requirement_type,
                               status, title, description, parent_id, order_index, snapshot_data, created_at::text AS created_at
                        FROM manage_milestone_nodes
                        WHERE milestone_id = %s
                        ORDER BY order_index ASC
                        """,
                        (milestone_id,),
                    )
                    result["nodes"] = [dict(row) for row in cur.fetchall()]

                    cur.execute(
                        """
                        SELECT id, milestone_id, parent_id, child_id, order_index
                        FROM manage_milestone_relations
                        WHERE milestone_id = %s
                        ORDER BY order_index ASC
                        """,
                        (milestone_id,),
                    )
                    result["relations"] = [dict(row) for row in cur.fetchall()]

                return result

    def set_baseline(self, milestone_id: str) -> None:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    "SELECT project_id, is_baseline FROM manage_milestones WHERE milestone_id = %s",
                    (milestone_id,),
                )
                row = cur.fetchone()
                if not row:
                    raise ValueError("里程碑不存在")

                # Toggle logic: allow multiple baselines
                new_state = not row["is_baseline"]

                cur.execute(
                    "UPDATE manage_milestones SET is_baseline = %s WHERE milestone_id = %s",
                    (new_state, milestone_id),
                )

                # Optionally update type if it was regular, but preserving other types is better
                # We will rely on is_baseline flag for logic

    def compare_milestones(self, from_id: str, to_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT requirement_id, snapshot_data, parent_id, order_index
                    FROM manage_milestone_nodes
                    WHERE milestone_id = %s
                    """,
                    (from_id,),
                )
                from_rows = cur.fetchall()
                cur.execute(
                    """
                    SELECT requirement_id, snapshot_data, parent_id, order_index
                    FROM manage_milestone_nodes
                    WHERE milestone_id = %s
                    """,
                    (to_id,),
                )
                to_rows = cur.fetchall()

        from_map = {r["requirement_id"]: r for r in from_rows}
        to_map = {r["requirement_id"]: r for r in to_rows}

        added = list(to_map.keys() - from_map.keys())
        deleted = list(from_map.keys() - to_map.keys())
        modified: List[str] = []
        moved: List[str] = []
        changes: List[Dict[str, Any]] = []
        change_map: Dict[str, List[str]] = {}

        for rid in from_map.keys() & to_map.keys():
            from_snap = from_map[rid]
            to_snap = to_map[rid]
            if from_snap.get("snapshot_data") != to_snap.get("snapshot_data"):
                modified.append(rid)
                changes.append(
                    {
                        "type": "modified",
                        "requirement_id": rid,
                        "before": from_snap.get("snapshot_data"),
                        "after": to_snap.get("snapshot_data"),
                    }
                )
                change_map.setdefault(rid, []).append("modified")
            if from_snap.get("parent_id") != to_snap.get("parent_id") or from_snap.get(
                "order_index"
            ) != to_snap.get("order_index"):
                moved.append(rid)
                changes.append(
                    {
                        "type": "moved",
                        "requirement_id": rid,
                        "before_parent_id": from_snap.get("parent_id"),
                        "after_parent_id": to_snap.get("parent_id"),
                        "before_order": from_snap.get("order_index"),
                        "after_order": to_snap.get("order_index"),
                    }
                )
                change_map.setdefault(rid, []).append("moved")

        for rid in added:
            changes.append(
                {
                    "type": "added",
                    "requirement_id": rid,
                    "after": to_map[rid].get("snapshot_data"),
                }
            )
            change_map.setdefault(rid, []).append("added")
        for rid in deleted:
            changes.append(
                {
                    "type": "deleted",
                    "requirement_id": rid,
                    "before": from_map[rid].get("snapshot_data"),
                }
            )
            change_map.setdefault(rid, []).append("deleted")

        from_tree = self._build_tree_from_snapshot(from_rows)
        to_tree = self._build_tree_from_snapshot(to_rows)

        return {
            "from_milestone_id": from_id,
            "to_milestone_id": to_id,
            "summary": {
                "added": len(added),
                "deleted": len(deleted),
                "modified": len(modified),
                "moved": len(moved),
                "total": len(added) + len(deleted) + len(modified) + len(moved),
            },
            "added": added,
            "deleted": deleted,
            "modified": modified,
            "moved": moved,
            "changes": changes,
            "change_map": change_map,
            "from_tree": from_tree,
            "to_tree": to_tree,
        }

    def add_milestone_edge(
        self,
        project_id: str,
        from_milestone_id: str,
        to_milestone_id: str,
        relation_type: str,
        message: str,
        created_by: str,
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO manage_milestone_edges (
                        project_id, from_milestone_id, to_milestone_id, relation_type, message, created_by, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    RETURNING id, project_id, from_milestone_id, to_milestone_id, relation_type, message, created_by, created_at::text AS created_at
                    """,
                    (
                        project_id,
                        from_milestone_id,
                        to_milestone_id,
                        relation_type,
                        message,
                        created_by,
                    ),
                )
                return dict(cur.fetchone())

    def list_milestone_graph(self, project_id: str) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT milestone_id, project_id, name, description, message,
                           milestone_type, is_baseline, sprint, version, tags, created_by, created_at::text AS created_at, metadata
                    FROM manage_milestones
                    WHERE project_id = %s
                    ORDER BY created_at ASC
                    """,
                    (project_id,),
                )
                nodes = [dict(row) for row in cur.fetchall()]
                cur.execute(
                    """
                    SELECT id, project_id, from_milestone_id, to_milestone_id, relation_type, message, created_by, created_at::text AS created_at
                    FROM manage_milestone_edges
                    WHERE project_id = %s
                    ORDER BY created_at ASC
                    """,
                    (project_id,),
                )
                edges = [dict(row) for row in cur.fetchall()]
                return {"nodes": nodes, "edges": edges}

    # ----------------------
    # Branch (Ref) & Impact
    # ----------------------
    def create_branch(
        self, project_id: str, base_milestone_id: str, name: str, created_by: str
    ) -> Dict[str, Any]:
        if not base_milestone_id:
            raise ValueError("缺少 base_milestone_id")
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT milestone_id
                    FROM manage_milestones
                    WHERE milestone_id = %s AND project_id = %s
                    """,
                    (base_milestone_id, project_id),
                )
                if not cur.fetchone():
                    raise ValueError("基准里程碑不存在")

                cur.execute(
                    """
                    INSERT INTO manage_branch_refs (ref_id, project_id, ref_name, ref_type, milestone_id, created_by, created_at, updated_at)
                    VALUES (%s, %s, %s, 'branch', %s, %s, NOW(), NOW())
                    ON CONFLICT (project_id, ref_name) DO NOTHING
                    RETURNING ref_id, project_id, ref_name, ref_type, milestone_id, created_by, created_at::text AS created_at
                    """,
                    (
                        str(uuid.uuid4()),
                        project_id,
                        name,
                        base_milestone_id,
                        created_by,
                    ),
                )
                ref_row = cur.fetchone()
                if not ref_row:
                    raise ValueError("分支名称已存在")
                return dict(ref_row)

    def list_branches(self, project_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT r.ref_id, r.project_id, r.ref_name, r.ref_type, r.milestone_id,
                           r.created_by, r.created_at::text AS created_at,
                           m.name AS milestone_name, m.created_at::text AS milestone_created_at, m.is_baseline
                    FROM manage_branch_refs r
                    LEFT JOIN manage_milestones m ON m.milestone_id = r.milestone_id
                    WHERE r.project_id = %s AND r.ref_type = 'branch'
                    ORDER BY r.created_at DESC
                    """,
                    (project_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def update_branch_ref(
        self, project_id: str, ref_name: str, milestone_id: str
    ) -> None:
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE manage_branch_refs
                    SET milestone_id = %s, updated_at = NOW()
                    WHERE project_id = %s AND ref_name = %s
                    """,
                    (milestone_id, project_id, ref_name),
                )
                if cur.rowcount == 0:
                    raise ValueError("分支不存在")

    def merge_branches(
        self,
        project_id: str,
        source_branch: str,
        target_branch: str,
        created_by: str,
        message: str = "",
    ) -> Dict[str, Any]:
        if source_branch == target_branch:
            raise ValueError("源分支与目标分支不能相同")

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT ref_name, milestone_id
                    FROM manage_branch_refs
                    WHERE project_id = %s AND ref_name IN (%s, %s)
                    """,
                    (project_id, source_branch, target_branch),
                )
                refs = {row["ref_name"]: row["milestone_id"] for row in cur.fetchall()}

                source_milestone_id = refs.get(source_branch)
                target_milestone_id = refs.get(target_branch)
                if not source_milestone_id or not target_milestone_id:
                    raise ValueError("源分支或目标分支不存在，或尚未指向里程碑")

                def _load_nodes(mid: str) -> Dict[str, Dict[str, Any]]:
                    cur.execute(
                        """
                        SELECT requirement_id, requirement_type, status, title, description,
                               parent_id, order_index, snapshot_data
                        FROM manage_milestone_nodes
                        WHERE milestone_id = %s
                        """,
                        (mid,),
                    )
                    rows = cur.fetchall()
                    return {row["requirement_id"]: dict(row) for row in rows}

                source_nodes = _load_nodes(source_milestone_id)
                target_nodes = _load_nodes(target_milestone_id)

                conflicts: List[Dict[str, Any]] = []
                merged_nodes = dict(target_nodes)
                for req_id, src_row in source_nodes.items():
                    if req_id in merged_nodes:
                        if merged_nodes[req_id].get("snapshot_data") != src_row.get(
                            "snapshot_data"
                        ):
                            conflicts.append(
                                {
                                    "requirement_id": req_id,
                                    "source": src_row.get("snapshot_data"),
                                    "target": merged_nodes[req_id].get("snapshot_data"),
                                }
                            )
                        continue
                    merged_nodes[req_id] = src_row

                milestone_id = str(uuid.uuid4())
                merge_name = f"Merge {source_branch} -> {target_branch}"
                metadata = {
                    "source_branch": source_branch,
                    "target_branch": target_branch,
                    "source_milestone_id": source_milestone_id,
                    "target_milestone_id": target_milestone_id,
                    "conflict_count": len(conflicts),
                }

                cur.execute(
                    """
                    INSERT INTO manage_milestones (
                        milestone_id, project_id, name, description, message,
                        milestone_type, is_baseline, sprint, version, tags, created_by, created_at, metadata
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, FALSE, NULL, NULL, %s::jsonb, %s, NOW(), %s::jsonb)
                    RETURNING milestone_id, project_id, name, description, message,
                              milestone_type, is_baseline, sprint, version, tags, created_by, created_at::text AS created_at, metadata
                    """,
                    (
                        milestone_id,
                        project_id,
                        merge_name,
                        "",
                        message,
                        "merge",
                        json.dumps([]),
                        created_by,
                        json.dumps(metadata),
                    ),
                )
                milestone = dict(cur.fetchone())

                cur.execute(
                    """
                    INSERT INTO manage_milestone_edges (
                        project_id, from_milestone_id, to_milestone_id, relation_type, message, created_by, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        project_id,
                        target_milestone_id,
                        milestone_id,
                        "merge",
                        f"merge-target:{target_branch}",
                        created_by,
                    ),
                )
                cur.execute(
                    """
                    INSERT INTO manage_milestone_edges (
                        project_id, from_milestone_id, to_milestone_id, relation_type, message, created_by, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    """,
                    (
                        project_id,
                        source_milestone_id,
                        milestone_id,
                        "merge",
                        f"merge-source:{source_branch}",
                        created_by,
                    ),
                )

                for req_id, node in merged_nodes.items():
                    snapshot_data = node.get("snapshot_data")
                    cur.execute(
                        """
                        INSERT INTO manage_milestone_nodes (
                            snapshot_id, milestone_id, requirement_id, requirement_type,
                            status, title, description, parent_id, order_index, snapshot_data, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, NOW())
                        """,
                        (
                            str(uuid.uuid4()),
                            milestone_id,
                            req_id,
                            node.get("requirement_type"),
                            node.get("status"),
                            node.get("title"),
                            node.get("description"),
                            node.get("parent_id"),
                            node.get("order_index", 0),
                            (
                                json.dumps(snapshot_data)
                                if snapshot_data is not None
                                else json.dumps({})
                            ),
                        ),
                    )

                for req_id, node in merged_nodes.items():
                    parent_id = node.get("parent_id")
                    if parent_id and parent_id in merged_nodes:
                        cur.execute(
                            """
                            INSERT INTO manage_milestone_relations (milestone_id, parent_id, child_id, order_index)
                            VALUES (%s, %s, %s, %s)
                            """,
                            (
                                milestone_id,
                                parent_id,
                                req_id,
                                node.get("order_index", 0),
                            ),
                        )

                cur.execute(
                    """
                    UPDATE manage_branch_refs
                    SET milestone_id = %s, updated_at = NOW()
                    WHERE project_id = %s AND ref_name = %s
                    """,
                    (milestone_id, project_id, target_branch),
                )

        return {
            "milestone": milestone,
            "conflicts": conflicts,
            "conflict_count": len(conflicts),
            "source_branch": source_branch,
            "target_branch": target_branch,
        }

    @staticmethod
    def _build_tree_from_snapshot(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        node_map: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            node_map[row["requirement_id"]] = {
                "requirement": row.get("snapshot_data") or {},
                "children": [],
                "parent_id": row.get("parent_id"),
                "order_index": row.get("order_index", 0),
            }

        roots: List[Dict[str, Any]] = []
        for rid, node in node_map.items():
            parent_id = node.get("parent_id")
            if parent_id and parent_id in node_map:
                node_map[parent_id]["children"].append(node)
            else:
                roots.append(node)

        def sort_children(n: Dict[str, Any]) -> None:
            n["children"].sort(key=lambda x: x.get("order_index", 0))
            for child in n["children"]:
                sort_children(child)

        for root in roots:
            sort_children(root)
        roots.sort(key=lambda x: x.get("order_index", 0))
        return roots

    def add_change_set(
        self,
        branch_id: str,
        change_type: str,
        requirement_id: Optional[str],
        before_data: Optional[Dict[str, Any]],
        after_data: Optional[Dict[str, Any]],
        created_by: str,
    ) -> Dict[str, Any]:
        change_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO manage_change_sets (
                        change_id, branch_id, change_type, requirement_id, before_data, after_data, created_by, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s::jsonb, %s::jsonb, %s, NOW())
                    RETURNING change_id, branch_id, change_type, requirement_id, before_data, after_data, created_by, created_at::text AS created_at
                    """,
                    (
                        change_id,
                        branch_id,
                        change_type,
                        requirement_id,
                        json.dumps(before_data or {}),
                        json.dumps(after_data or {}),
                        created_by,
                    ),
                )
                return dict(cur.fetchone())

    def list_change_sets(self, branch_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT change_id, branch_id, change_type, requirement_id, before_data, after_data, created_by, created_at::text AS created_at
                    FROM manage_change_sets
                    WHERE branch_id = %s
                    ORDER BY created_at DESC
                    """,
                    (branch_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def create_impact_report(self, branch_id: str, created_by: str) -> Dict[str, Any]:
        report_id = str(uuid.uuid4())
        summary = "影响分析算法尚未实现，已预留接口"
        detail = {
            "status": "pending",
            "note": "impact analysis placeholder",
            "created_at": _utc_now_iso(),
        }
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO manage_impact_reports (report_id, branch_id, summary, detail_json, status, created_by, created_at)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s, NOW())
                    RETURNING report_id, branch_id, summary, detail_json, status, created_by, created_at::text AS created_at
                    """,
                    (
                        report_id,
                        branch_id,
                        summary,
                        json.dumps(detail),
                        "pending",
                        created_by,
                    ),
                )
                return dict(cur.fetchone())

    def create_merge_request(
        self, branch_id: str, target_milestone_id: str, created_by: str
    ) -> Dict[str, Any]:
        merge_id = str(uuid.uuid4())
        summary = "等待评审与冲突检查"
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO manage_merge_logs (merge_id, branch_id, target_milestone_id, status, summary, created_by, created_at)
                    VALUES (%s, %s, %s, 'pending', %s, %s, NOW())
                    RETURNING merge_id, branch_id, target_milestone_id, status, summary, created_by, created_at::text AS created_at
                    """,
                    (merge_id, branch_id, target_milestone_id, summary, created_by),
                )
                return dict(cur.fetchone())

    # ----------------------
    # Audit Logs
    # ----------------------
    def add_audit_log(
        self,
        project_id: Optional[str],
        actor: str,
        action: str,
        target_type: str,
        target_id: str,
        detail: Optional[Dict[str, Any]] = None,
    ) -> None:
        log_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO manage_audit_logs (log_id, project_id, product_id, actor, action, target_type, target_id, detail, created_at)
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

    def list_audit_logs(
        self, project_id: str, limit: int = 100
    ) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT log_id, project_id, actor, action, target_type, target_id, detail, created_at::text AS created_at
                    FROM manage_audit_logs
                    WHERE project_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (project_id, int(limit)),
                )
                return [dict(row) for row in cur.fetchall()]
