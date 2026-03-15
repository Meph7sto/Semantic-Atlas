"""
读模型投影 - 事件流投影到读视图

将事件流投影到读模型（如 manage_requirements 表），
用于查询和版本栅栏
"""

import asyncio
import logging
from typing import Dict, List, Optional

import psycopg2
import psycopg2.extras

from backend_business.services.db_service_parts.base import DBServiceBase

logger = logging.getLogger(__name__)


class RequirementProjection(DBServiceBase):
    """需求读模型投影"""

    def __init__(self, dsn: str):
        super().__init__(dsn)
        self.dsn = dsn

    def apply_event(self, event: Dict):
        """
        应用事件到读模型

        Args:
            event: 事件字典
        """
        event_type = event["event_type"]

        if event_type == "RequirementCreated":
            self._on_created(event)
        elif event_type == "RequirementContentUpdated":
            self._on_content_updated(event)
        elif event_type == "RequirementStatusChanged":
            self._on_status_changed(event)
        elif event_type == "RequirementDeleted":
            self._on_deleted(event)
        else:
            # 其他事件类型不更新读模型
            pass

    def _on_created(self, event: Dict):
        """处理需求创建事件"""
        with self._connect() as conn:
            with conn.cursor() as cur:
                # 更新或插入 manage_requirements 表
                cur.execute("""
                    INSERT INTO manage_requirements (req_id, title, status, current_version, last_event_id, actor_status)
                    VALUES (%s, %s, %s, %s, %s, 'active')
                    ON CONFLICT (req_id) DO UPDATE SET
                        title = COALESCE(EXCLUDED.title, manage_requirements.title),
                        status = COALESCE(EXCLUDED.status, manage_requirements.status),
                        current_version = EXCLUDED.current_version,
                        last_event_id = EXCLUDED.last_event_id,
                        actor_status = 'active'
                """, (
                    event["requirement_id"],
                    event["event_data"].get("title", ""),
                    event["event_data"].get("status", "Draft"),
                    event["event_sequence"],
                    event["event_id"]
                ))
                conn.commit()
                logger.debug(f"Applied RequirementCreated event to read model: {event['requirement_id']}")

    def _on_content_updated(self, event: Dict):
        """处理内容更新事件"""
        with self._connect() as conn:
            with conn.cursor() as cur:
                updates = event["event_data"].get("updates", {})

                cur.execute("""
                    UPDATE manage_requirements
                    SET
                        title = COALESCE(%s, title),
                        content = COALESCE(%s, content),
                        priority = COALESCE(%s, priority),
                        current_version = %s,
                        last_event_id = %s,
                        actor_status = 'active',
                        updated_at = NOW()
                    WHERE req_id = %s
                """, (
                    updates.get("title"),
                    psycopg2.extras.Json(updates.get("content")) if "content" in updates else None,
                    updates.get("priority"),
                    event["event_sequence"],
                    event["event_id"],
                    event["requirement_id"]
                ))
                conn.commit()
                logger.debug(f"Applied RequirementContentUpdated event to read model: {event['requirement_id']}")

    def _on_status_changed(self, event: Dict):
        """处理状态变更事件"""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE manage_requirements
                    SET
                        status = %s,
                        current_version = %s,
                        last_event_id = %s,
                        actor_status = 'active',
                        updated_at = NOW()
                    WHERE req_id = %s
                """, (
                    event["event_data"]["new_status"],
                    event["event_sequence"],
                    event["event_id"],
                    event["requirement_id"]
                ))
                conn.commit()
                logger.debug(f"Applied RequirementStatusChanged event to read model: {event['requirement_id']}")

    def _on_deleted(self, event: Dict):
        """处理删除事件"""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE manage_requirements
                    SET
                        is_deleted = TRUE,
                        current_version = %s,
                        actor_status = 'inactive',
                        updated_at = NOW()
                    WHERE req_id = %s
                """, (event["event_sequence"], event["requirement_id"]))
                conn.commit()
                logger.debug(f"Applied RequirementDeleted event to read model: {event['requirement_id']}")

    def get_current_version(self, requirement_id: str) -> int:
        """
        获取读模型当前版本

        Args:
            requirement_id: 需求 ID

        Returns:
            当前版本号
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(current_version, 0) as version
                    FROM manage_requirements
                    WHERE req_id = %s
                """, (requirement_id,))
                row = cur.fetchone()
                return row[0] if row else 0

    async def wait_for_version(self, requirement_id: str, min_version: int,
                            timeout: float = 5.0) -> bool:
        """
        等待读模型追上指定版本

        Args:
            requirement_id: 需求 ID
            min_version: 最低版本号
            timeout: 超时时间（秒）

        Returns:
            True 如果版本已追上，False 如果超时
        """
        start_time = asyncio.get_event_loop().time()
        check_interval = 0.1  # 100ms 轮询

        while True:
            current_version = self.get_current_version(requirement_id)
            if current_version >= min_version:
                logger.debug(f"Read model caught up: {requirement_id} v{current_version} >= v{min_version}")
                return True

            if asyncio.get_event_loop().time() - start_time > timeout:
                logger.warning(f"Read model timeout: {requirement_id} v{current_version} < v{min_version}")
                return False

            await asyncio.sleep(check_interval)

    def rebuild_from_events(self, requirement_id: str):
        """
        从事件流重建投影

        Args:
            requirement_id: 需求 ID
        """
        from backend_business.services.event_store.event_store import EventStore

        event_store = EventStore(self.dsn)
        events = event_store.replay_events(requirement_id)

        logger.info(f"Rebuilding projection for {requirement_id} from {len(events)} events")

        # 先标记为删除
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    UPDATE manage_requirements
                    SET is_deleted = TRUE
                    WHERE req_id = %s
                """, (requirement_id,))
                conn.commit()

        # 重新应用所有事件
        for event in events:
            try:
                self.apply_event(event)
            except Exception as e:
                logger.error(f"Error applying event during rebuild: {e}")

        logger.info(f"Projection rebuild complete for {requirement_id}")

    def get_requirement(self, requirement_id: str) -> Optional[Dict]:
        """
        从读模型获取需求

        Args:
            requirement_id: 需求 ID

        Returns:
            需求数据，或 None
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM manage_requirements
                    WHERE req_id = %s
                """, (requirement_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def get_requirements_by_project(self, project_id: str, status: Optional[str] = None,
                                page: int = 1, per_page: int = 50) -> Dict:
        """
        按项目获取需求列表

        Args:
            project_id: 项目 ID
            status: 状态过滤（可选）
            page: 页码
            per_page: 每页数量

        Returns:
            分页结果
        """
        offset = (page - 1) * per_page

        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:

                # 构建 WHERE 条件
                where_clauses = ["project_id = %s"]
                params = [project_id]

                if status:
                    where_clauses.append("status = %s")
                    params.append(status)

                where_sql = " AND ".join(where_clauses)

                # 获取总数
                cur.execute(f"""
                    SELECT COUNT(*) as total FROM manage_requirements
                    WHERE {where_sql}
                """, params)
                total = cur.fetchone()["total"]

                # 获取分页数据
                params.append(per_page)
                params.append(offset)
                cur.execute(f"""
                    SELECT * FROM manage_requirements
                    WHERE {where_sql}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                """, params)

                requirements = [dict(row) for row in cur.fetchall()]

                return {
                    "requirements": requirements,
                    "total": total,
                    "page": page,
                    "per_page": per_page,
                    "pages": (total + per_page - 1) // per_page
                }
