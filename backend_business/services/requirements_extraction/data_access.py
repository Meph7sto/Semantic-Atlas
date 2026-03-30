"""
Data access layer for requirements extraction service
"""

from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor


class RequirementsDataAccess:
    """Database operations for requirements extraction"""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _connect(self) -> psycopg2.extensions.connection:
        """Create database connection"""
        return psycopg2.connect(self.dsn)

    def get_spans_by_session(self, session_id: str) -> List[Dict[str, Any]]:
        """
        获取指定 session 的所有 spans，按 start_ms 排序
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT span_id, session_id, start_ms, end_ms, speaker, text, asr_confidence, meta_json
                    FROM spans
                    WHERE session_id = %s
                    ORDER BY start_ms ASC, span_id ASC
                    """,
                    (session_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def get_edges_by_run(self, context_run_id: str) -> List[Dict[str, Any]]:
        """
        获取指定 context_run 的所有关联边
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT source_span_id, target_span_id, relation_type, strength
                    FROM span_links
                    WHERE context_run_id = %s
                    """,
                    (context_run_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def get_all_requirements_for_session(self, session_id: str) -> List[Dict[str, Any]]:
        """
        获取指定 session 的所有 L1-L3 需求（无分页，用于历史感知注入）

        Args:
            session_id: 会话 ID

        Returns:
            需求列表，每项包含 req_id, level, text, fingerprint, created_at
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, session_id, level, text, fingerprint, anchor_span_id, r, 
                           created_at::text AS created_at
                    FROM requirements_l123
                    WHERE session_id = %s
                    ORDER BY level ASC, created_at ASC
                    """,
                    (session_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def update_requirement(
        self,
        req_id: str,
        new_text: str,
        new_fingerprint: str,
        new_level: Optional[str] = None,
        update_reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        更新已存在的需求条目

        Args:
            req_id: 需求 ID
            new_text: 更新后的需求文本
            new_fingerprint: 更新后的指纹
            new_level: 新的需求层级（可选，None 则保持不变）
            update_reason: 更新原因（用于日志记录）

        Returns:
            操作结果，包含 success, old_text, new_text, update_reason 等信息
        """
        result = {
            "success": False,
            "req_id": req_id,
            "old_text": None,
            "old_level": None,
            "new_text": new_text,
            "new_level": new_level,
            "update_reason": update_reason,
            "error": None,
        }

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 先获取原有记录
                cur.execute(
                    """
                    SELECT req_id, session_id, level, text, fingerprint
                    FROM requirements_l123
                    WHERE req_id = %s
                    """,
                    (req_id,),
                )
                row = cur.fetchone()

                if not row:
                    result["error"] = f"Requirement not found: {req_id}"
                    return result

                result["old_text"] = row["text"]
                result["old_level"] = row["level"]

                # 构建更新语句
                if new_level and new_level != row["level"]:
                    cur.execute(
                        """
                        UPDATE requirements_l123
                        SET text = %s, fingerprint = %s, level = %s
                        WHERE req_id = %s
                        """,
                        (new_text, new_fingerprint, new_level, req_id),
                    )
                    result["new_level"] = new_level
                else:
                    cur.execute(
                        """
                        UPDATE requirements_l123
                        SET text = %s, fingerprint = %s
                        WHERE req_id = %s
                        """,
                        (new_text, new_fingerprint, req_id),
                    )
                    result["new_level"] = row["level"]

                if cur.rowcount > 0:
                    result["success"] = True
                    conn.commit()
                else:
                    result["error"] = "Update failed: no rows affected"

        return result

    def find_requirement_by_short_id(
        self, session_id: str, short_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        通过短 ID（前缀）查找需求

        Args:
            session_id: 会话 ID
            short_id: 需求 ID 的前缀（如前 8 位）

        Returns:
            匹配的需求记录，如果找不到或有多个匹配则返回 None
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 使用 LIKE 进行前缀匹配
                cur.execute(
                    """
                    SELECT req_id, session_id, level, text, fingerprint, anchor_span_id, r,
                           created_at::text AS created_at
                    FROM requirements_l123
                    WHERE session_id = %s AND req_id LIKE %s
                    """,
                    (session_id, f"{short_id}%"),
                )
                rows = cur.fetchall()

                if len(rows) == 1:
                    return dict(rows[0])
                return None

    def get_requirements_by_session(
        self,
        session_id: str,
        level: Optional[str] = None,
        page: int = 1,
        per_page: int = 50,
    ) -> Dict[str, Any]:
        """
        查询指定 session 的需求

        Args:
            session_id: 会话 ID
            level: 需求层级过滤（可选）
            page: 页码
            per_page: 每页数量

        Returns:
            需求列表和分页信息
        """
        page = max(1, page)
        per_page = max(1, min(200, per_page))
        offset = (page - 1) * per_page

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # 计数
                if level:
                    cur.execute(
                        "SELECT COUNT(1) AS c FROM requirements_l123 WHERE session_id = %s AND level = %s",
                        (session_id, level),
                    )
                else:
                    cur.execute(
                        "SELECT COUNT(1) AS c FROM requirements_l123 WHERE session_id = %s",
                        (session_id,),
                    )
                total = cur.fetchone()["c"]

                # 查询
                if level:
                    cur.execute(
                        """
                        SELECT req_id, session_id, level, text, fingerprint, anchor_span_id, r, created_at::text AS created_at
                        FROM requirements_l123
                        WHERE session_id = %s AND level = %s
                        ORDER BY created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (session_id, level, per_page, offset),
                    )
                else:
                    cur.execute(
                        """
                        SELECT req_id, session_id, level, text, fingerprint, anchor_span_id, r, created_at::text AS created_at
                        FROM requirements_l123
                        WHERE session_id = %s
                        ORDER BY level ASC, created_at DESC
                        LIMIT %s OFFSET %s
                        """,
                        (session_id, per_page, offset),
                    )

                requirements = [dict(row) for row in cur.fetchall()]

        return {
            "requirements": requirements,
            "total": total,
            "pages": (total + per_page - 1) // per_page,
            "current_page": page,
            "per_page": per_page,
        }

    def get_requirement_detail(self, req_id: str) -> Optional[Dict[str, Any]]:
        """
        获取需求详情
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, session_id, level, text, fingerprint, anchor_span_id, r, created_at::text AS created_at
                    FROM requirements_l123
                    WHERE req_id = %s
                    """,
                    (req_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def delete_requirement(self, req_id: str) -> bool:
        """
        删除需求
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM requirements_l123 WHERE req_id = %s", (req_id,)
                )
                return cur.rowcount > 0

    def clear_requirements_for_session(self, session_id: str) -> int:
        """
        清理指定 session 的全部 L1-L3 需求（用于重跑前重置）
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM requirements_l123 WHERE session_id = %s",
                    (session_id,),
                )
                return cur.rowcount

    def get_statistics(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        获取需求统计信息
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                if session_id:
                    cur.execute(
                        "SELECT COUNT(1) AS c FROM requirements_l123 WHERE session_id = %s",
                        (session_id,),
                    )
                    total = cur.fetchone()["c"]
                    cur.execute(
                        """
                        SELECT level, COUNT(1) AS c
                        FROM requirements_l123
                        WHERE session_id = %s
                        GROUP BY level
                        ORDER BY level
                        """,
                        (session_id,),
                    )
                else:
                    cur.execute("SELECT COUNT(1) AS c FROM requirements_l123")
                    total = cur.fetchone()["c"]
                    cur.execute(
                        """
                        SELECT level, COUNT(1) AS c
                        FROM requirements_l123
                        GROUP BY level
                        ORDER BY level
                        """
                    )

                level_stats = {row["level"]: row["c"] for row in cur.fetchall()}

        return {
            "total": total,
            "by_level": level_stats,
        }
