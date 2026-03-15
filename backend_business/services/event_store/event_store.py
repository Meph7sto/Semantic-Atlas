"""
事件存储服务 - 追加写、重放、快照

Event Sourcing 模式的核心实现：
- 事件仅追加，不可修改
- 通过事件重放重建状态
- 快照优化性能
"""

import logging
import psycopg2
import psycopg2.extras
from typing import List, Dict, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class EventStore:
    """事件存储服务 - 仅追加写"""

    def __init__(self, dsn: str):
        self.dsn = dsn

    def _connect(self) -> psycopg2.extensions.connection:
        """创建数据库连接"""
        return psycopg2.connect(self.dsn)

    def append_event(self, event: Dict) -> tuple[str, int]:
        """
        追加事件到存储

        Args:
            event: 事件字典，必须包含:
                - requirement_id: 需求 ID
                - event_type: 事件类型
                - event_data: 事件数据 (JSONB)
                - source: 来源 (agent_id, user_id, 或 system)
                - metadata: 元数据 (可选)

        Returns:
            (event_id, sequence): 事件 ID 和序列号
        """
        requirement_id = event["requirement_id"]
        event_type = event["event_type"]

        # 验证事件类型
        valid_types = {
            "RequirementContentUpdated",
            "RequirementStatusChanged",
            "RequirementQualityMarkerAdded",
            "RequirementEvidenceLinkAdded",
            "RequirementPriorityChanged",
            "RequirementCreated",
            "RequirementDeleted",
        }
        if event_type not in valid_types:
            raise ValueError(f"Invalid event type: {event_type}")

        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                # 获取下一个序列号
                cur.execute("""
                    SELECT COALESCE(MAX(event_sequence), 0) + 1 AS next_sequence
                    FROM requirement_events
                    WHERE requirement_id = %s
                """, (requirement_id,))
                row = cur.fetchone()
                next_sequence = row["next_sequence"] if row and row["next_sequence"] is not None else 1

                event_id = f"{requirement_id}_{event_type}_{next_sequence}"
                occurred_at = event.get("occurred_at", datetime.utcnow())

                cur.execute("""
                    INSERT INTO requirement_events
                    (event_id, requirement_id, event_type, event_sequence, event_data, occurred_at, source, metadata)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """, (
                    event_id,
                    requirement_id,
                    event_type,
                    next_sequence,
                    psycopg2.extras.Json(event["event_data"]),
                    occurred_at,
                    event.get("source", "system"),
                    psycopg2.extras.Json(event.get("metadata", {}))
                ))

                # 更新 manage_requirements 表的版本信息
                cur.execute("""
                    UPDATE manage_requirements
                    SET
                        current_version = %s,
                        last_event_id = %s,
                        actor_status = 'active'
                    WHERE req_id = %s
                """, (next_sequence, event_id, requirement_id))

                conn.commit()
                logger.debug(f"Appended event {event_id} for {requirement_id}, sequence={next_sequence}")
                return event_id, next_sequence

    def replay_events(self, requirement_id: str, from_version: int = 0) -> List[Dict]:
        """
        重放事件流，重建状态

        Args:
            requirement_id: 需求 ID
            from_version: 起始版本号（0 表示从头开始）

        Returns:
            事件列表，按序列号升序排列
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM requirement_events
                    WHERE requirement_id = %s AND event_sequence > %s
                    ORDER BY event_sequence ASC
                """, (requirement_id, from_version))
                events = [dict(row) for row in cur.fetchall()]
                logger.debug(f"Replayed {len(events)} events for {requirement_id} from version {from_version}")
                return events

    def get_latest_snapshot(self, requirement_id: str) -> Optional[Dict]:
        """
        获取最新快照

        Args:
            requirement_id: 需求 ID

        Returns:
            快照数据字典，或 None
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM requirement_snapshots
                    WHERE requirement_id = %s
                    ORDER BY version DESC
                    LIMIT 1
                """, (requirement_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def save_snapshot(self, requirement_id: str, version: int, state_data: Dict,
                   reason: str = "manual") -> str:
        """
        保存快照

        Args:
            requirement_id: 需求 ID
            version: 当前版本号
            state_data: 完整状态数据
            reason: 快照原因

        Returns:
            snapshot_id: 快照 ID
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                snapshot_id = f"{requirement_id}_snapshot_{version}"

                # 获取从上一个快照以来的事件数（近似值）
                prev_snapshot = self.get_latest_snapshot(requirement_id)
                from_version = prev_snapshot["version"] if prev_snapshot else 0

                cur.execute("""
                    SELECT COUNT(*) as event_count FROM requirement_events
                    WHERE requirement_id = %s AND event_sequence > %s AND event_sequence <= %s
                """, (requirement_id, from_version, version))
                row = cur.fetchone()
                event_count = row["event_count"]

                cur.execute("""
                    INSERT INTO requirement_snapshots
                    (snapshot_id, requirement_id, version, snapshot_data, snapshot_reason, event_count)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    ON CONFLICT (snapshot_id) DO UPDATE SET
                        snapshot_data = EXCLUDED.snapshot_data,
                        created_at = NOW()
                """, (
                    snapshot_id,
                    requirement_id,
                    version,
                    psycopg2.extras.Json(state_data),
                    reason,
                    event_count
                ))

                # 更新 manage_requirements 表的快照 ID
                cur.execute("""
                    UPDATE manage_requirements
                    SET last_snapshot_id = %s
                    WHERE req_id = %s
                """, (snapshot_id, requirement_id))

                conn.commit()
                logger.info(f"Saved snapshot {snapshot_id} for {requirement_id}, version={version}, reason={reason}")
                return snapshot_id

    def get_event_by_id(self, event_id: str) -> Optional[Dict]:
        """根据事件 ID 获取事件"""
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM requirement_events
                    WHERE event_id = %s
                """, (event_id,))
                row = cur.fetchone()
                return dict(row) if row else None

    def get_events_by_requirement(self, requirement_id: str, limit: int = 100,
                                offset: int = 0) -> List[Dict]:
        """
        分页获取需求的事件历史

        Args:
            requirement_id: 需求 ID
            limit: 每页数量
            offset: 偏移量

        Returns:
            事件列表，按序列号升序排列
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
                cur.execute("""
                    SELECT * FROM requirement_events
                    WHERE requirement_id = %s
                    ORDER BY event_sequence ASC
                    LIMIT %s OFFSET %s
                """, (requirement_id, limit, offset))
                return [dict(row) for row in cur.fetchall()]

    def get_current_version(self, requirement_id: str) -> int:
        """获取需求当前版本号"""
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT COALESCE(MAX(event_sequence), 0) as version
                    FROM requirement_events
                    WHERE requirement_id = %s
                """, (requirement_id,))
                row = cur.fetchone()
                return row[0] if row[0] is not None else 0

    def log_command(self, requirement_id: str, command_type: str, command_data: Dict,
                  submitted_by: str, status: str = "pending") -> str:
        """
        记录命令到审计日志

        Args:
            requirement_id: 需求 ID
            command_type: 命令类型
            command_data: 命令数据
            submitted_by: 提交者
            status: 状态

        Returns:
            queue_id: 队列 ID
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                queue_id = f"{requirement_id}_cmd_{command_type}_{datetime.utcnow().timestamp()}"

                cur.execute("""
                    INSERT INTO requirement_command_queue
                    (queue_id, requirement_id, command_type, command_data, submitted_by, status)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (
                    queue_id,
                    requirement_id,
                    command_type,
                    psycopg2.extras.Json(command_data),
                    submitted_by,
                    status
                ))
                conn.commit()
                return queue_id

    def update_command_status(self, queue_id: str, status: str,
                           error_message: str = None):
        """
        更新命令状态

        Args:
            queue_id: 队列 ID
            status: 新状态
            error_message: 错误消息（可选）
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                if status in ("started", "completed"):
                    cur.execute("""
                        UPDATE requirement_command_queue
                        SET status = %s, started_at = NOW()
                        WHERE queue_id = %s AND started_at IS NULL
                    """, (status, queue_id))
                elif status == "completed":
                    cur.execute("""
                        UPDATE requirement_command_queue
                        SET status = %s, completed_at = NOW()
                        WHERE queue_id = %s AND completed_at IS NULL
                    """, (status, queue_id))
                else:
                    cur.execute("""
                        UPDATE requirement_command_queue
                        SET status = %s, error_message = %s
                        WHERE queue_id = %s
                    """, (status, error_message, queue_id))
                conn.commit()
