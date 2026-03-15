"""
Executor for requirements deduplication operations.

Handles merge and delete operations with database transactions.
"""

import hashlib
import logging
import re
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from .models import MergeResult

logger = logging.getLogger(__name__)


class DeduplicationExecutor:
    """
    去重操作执行器

    负责执行合并、删除等数据库操作，确保事务原子性
    """

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _connect(self) -> psycopg2.extensions.connection:
        """创建数据库连接"""
        return psycopg2.connect(self.dsn)

    @staticmethod
    def _compute_fingerprint(session_id: str, level: str, text: str) -> str:
        """
        计算需求指纹（与 requirements_executor 保持一致）

        Args:
            session_id: 会话ID
            level: 需求层级
            text: 需求文本

        Returns:
            SHA256 指纹
        """
        normalized = re.sub(r"\s+", " ", text.strip()).lower()
        raw = f"{session_id}|{level}|{normalized}"
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def merge_requirements(
        self,
        session_id: str,
        primary_req_id: str,
        to_delete_req_ids: List[str],
        merged_text: str,
        merged_level: str,
        reason: str = "",
    ) -> MergeResult:
        """
        合并需求：更新主需求文本，删除其他需求

        Args:
            session_id: 会话ID
            primary_req_id: 保留的主需求ID
            to_delete_req_ids: 要删除的需求ID列表
            merged_text: 合并后的需求文本
            merged_level: 合并后的需求层级
            reason: 合并原因（用于日志）

        Returns:
            MergeResult 操作结果
        """
        result = MergeResult(
            success=False,
            primary_req_id=primary_req_id,
            deleted_count=0,
            old_text="",
            new_text=merged_text,
            reason=reason,
        )

        # 验证参数
        if not primary_req_id:
            result.error = "primary_req_id 不能为空"
            return result

        if not merged_text or len(merged_text.strip()) < 10:
            result.error = "merged_text 不能为空且长度需 >= 10"
            return result

        if merged_level not in ("L1", "L2", "L3"):
            result.error = f"无效的 merged_level: {merged_level}"
            return result

        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 1. 获取主需求的原文本
                    cur.execute(
                        """
                        SELECT text, level FROM requirements_l123
                        WHERE req_id = %s AND session_id = %s
                        """,
                        (primary_req_id, session_id),
                    )
                    row = cur.fetchone()

                    if not row:
                        result.error = f"主需求不存在: {primary_req_id}"
                        return result

                    result.old_text = row["text"]

                    # 2. 计算新的指纹
                    new_fingerprint = self._compute_fingerprint(
                        session_id, merged_level, merged_text.strip()
                    )

                    # 3. 更新主需求
                    cur.execute(
                        """
                        UPDATE requirements_l123
                        SET text = %s, level = %s, fingerprint = %s
                        WHERE req_id = %s AND session_id = %s
                        """,
                        (
                            merged_text.strip(),
                            merged_level,
                            new_fingerprint,
                            primary_req_id,
                            session_id,
                        ),
                    )

                    if cur.rowcount == 0:
                        result.error = "更新主需求失败"
                        return result

                    # 4. 删除其他需求
                    if to_delete_req_ids:
                        # 过滤掉主需求ID（防止误删）
                        safe_delete_ids = [
                            rid for rid in to_delete_req_ids if rid != primary_req_id
                        ]

                        if safe_delete_ids:
                            cur.execute(
                                """
                                DELETE FROM requirements_l123
                                WHERE req_id = ANY(%s) AND session_id = %s
                                """,
                                (safe_delete_ids, session_id),
                            )
                            result.deleted_count = cur.rowcount

                    # 5. 提交事务
                    conn.commit()
                    result.success = True

                    logger.info(
                        f"合并完成: primary={primary_req_id[:8]}, "
                        f"deleted={result.deleted_count}, reason={reason}"
                    )

        except Exception as e:
            logger.exception("合并需求时发生错误")
            result.error = str(e)

        return result

    def delete_requirements(
        self,
        session_id: str,
        req_ids: List[str],
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        批量删除需求

        Args:
            session_id: 会话ID
            req_ids: 要删除的需求ID列表
            reason: 删除原因（用于日志）

        Returns:
            操作结果 {"success": bool, "deleted_count": int, "error": str}
        """
        result: Dict[str, Any] = {
            "success": False,
            "deleted_count": 0,
            "reason": reason,
            "error": None,
        }

        if not req_ids:
            result["error"] = "req_ids 不能为空"
            return result

        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM requirements_l123
                        WHERE req_id = ANY(%s) AND session_id = %s
                        """,
                        (req_ids, session_id),
                    )
                    result["deleted_count"] = cur.rowcount
                    conn.commit()
                    result["success"] = True

                    logger.info(
                        f"批量删除完成: count={result['deleted_count']}, "
                        f"reason={reason}"
                    )

        except Exception as e:
            logger.exception("批量删除需求时发生错误")
            result["error"] = str(e)

        return result

    def update_requirement_text(
        self,
        session_id: str,
        req_id: str,
        new_text: str,
        new_level: Optional[str] = None,
        reason: str = "",
    ) -> Dict[str, Any]:
        """
        更新单个需求的文本

        Args:
            session_id: 会话ID
            req_id: 需求ID
            new_text: 新的需求文本
            new_level: 新的需求层级（可选，None则保持不变）
            reason: 更新原因

        Returns:
            操作结果
        """
        result: Dict[str, Any] = {
            "success": False,
            "req_id": req_id,
            "old_text": None,
            "new_text": new_text,
            "old_level": None,
            "new_level": new_level,
            "reason": reason,
            "error": None,
        }

        try:
            with self._connect() as conn:
                with conn.cursor(cursor_factory=RealDictCursor) as cur:
                    # 获取原记录
                    cur.execute(
                        """
                        SELECT text, level FROM requirements_l123
                        WHERE req_id = %s AND session_id = %s
                        """,
                        (req_id, session_id),
                    )
                    row = cur.fetchone()

                    if not row:
                        result["error"] = f"需求不存在: {req_id}"
                        return result

                    result["old_text"] = row["text"]
                    result["old_level"] = row["level"]

                    # 确定最终层级
                    final_level = new_level if new_level else row["level"]
                    result["new_level"] = final_level

                    # 计算新指纹
                    new_fingerprint = self._compute_fingerprint(
                        session_id, final_level, new_text.strip()
                    )

                    # 更新
                    cur.execute(
                        """
                        UPDATE requirements_l123
                        SET text = %s, level = %s, fingerprint = %s
                        WHERE req_id = %s AND session_id = %s
                        """,
                        (
                            new_text.strip(),
                            final_level,
                            new_fingerprint,
                            req_id,
                            session_id,
                        ),
                    )

                    if cur.rowcount > 0:
                        conn.commit()
                        result["success"] = True
                    else:
                        result["error"] = "更新失败：未影响任何行"

        except Exception as e:
            logger.exception("更新需求文本时发生错误")
            result["error"] = str(e)

        return result

    def get_requirements_by_ids(
        self,
        session_id: str,
        req_ids: List[str],
    ) -> List[Dict[str, Any]]:
        """
        根据ID列表获取需求详情

        Args:
            session_id: 会话ID
            req_ids: 需求ID列表

        Returns:
            需求列表
        """
        if not req_ids:
            return []

        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT req_id, session_id, level, text, fingerprint,
                           anchor_span_id, r, created_at::text AS created_at
                    FROM requirements_l123
                    WHERE req_id = ANY(%s) AND session_id = %s
                    """,
                    (req_ids, session_id),
                )
                return [dict(row) for row in cur.fetchall()]
