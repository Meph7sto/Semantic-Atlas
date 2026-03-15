"""
消息推送服务层

提供消息 CRUD 和 SSE 实时推送功能
"""
import json
import queue
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional

from psycopg2.extras import RealDictCursor

from backend_business.services.db_service import db_service


class PushService:
    """消息推送服务"""

    def __init__(self):
        # SSE 客户端订阅列表
        self._subscribers: List[queue.Queue] = []
        self._lock = threading.Lock()

    def create_message(
        self,
        message_type: str,
        title: str,
        content: Optional[str] = None,
        source: Optional[str] = None,
        priority: str = "medium",
        ai_suggestion: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        创建新消息

        Args:
            message_type: 消息类型 ('review' | 'change')
            title: 消息标题
            content: 消息内容
            source: 消息来源
            priority: 优先级 ('low' | 'medium' | 'high')
            ai_suggestion: AI 建议
            metadata: 元数据

        Returns:
            创建的消息对象
        """
        if message_type not in ("review", "change"):
            raise ValueError("message_type must be 'review' or 'change'")
        if priority not in ("low", "medium", "high"):
            raise ValueError("priority must be 'low', 'medium', or 'high'")

        message_id = f"msg_{uuid.uuid4().hex[:12]}"
        created_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO push_messages (
                        message_id, message_type, title, content, source,
                        priority, ai_suggestion, metadata, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        message_id,
                        message_type,
                        title,
                        content,
                        source,
                        priority,
                        ai_suggestion,
                        json.dumps(metadata, ensure_ascii=False) if metadata else None,
                        created_at,
                    ),
                )

        return {
            "message_id": message_id,
            "message_type": message_type,
            "title": title,
            "content": content,
            "source": source,
            "priority": priority,
            "ai_suggestion": ai_suggestion,
            "metadata": metadata,
            "created_at": created_at,
            "read": False,
            "pushed": False,
            "pushed_at": None,
        }

    def list_messages(
        self,
        message_type: Optional[str] = None,
        pushed: Optional[bool] = None,
        page: int = 1,
        per_page: int = 20,
    ) -> Dict[str, Any]:
        """
        获取消息列表

        Args:
            message_type: 筛选消息类型
            pushed: 筛选是否已推送
            page: 页码
            per_page: 每页数量

        Returns:
            分页消息列表
        """
        page = max(1, int(page))
        per_page = max(1, min(100, int(per_page)))
        offset = (page - 1) * per_page

        conditions = []
        params = []

        if message_type:
            conditions.append("message_type = %s")
            params.append(message_type)

        if pushed is not None:
            conditions.append("pushed = %s")
            params.append(pushed)

        where_clause = ""
        if conditions:
            where_clause = "WHERE " + " AND ".join(conditions)

        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"SELECT COUNT(1) AS c FROM push_messages {where_clause}",
                    params,
                )
                total = cur.fetchone()["c"]

                cur.execute(
                    f"""
                    SELECT
                        message_id, message_type, title, content, source,
                        priority, ai_suggestion, metadata,
                        created_at::text AS created_at,
                        read, pushed, pushed_at::text AS pushed_at
                    FROM push_messages
                    {where_clause}
                    ORDER BY created_at DESC
                    LIMIT %s OFFSET %s
                    """,
                    params + [per_page, offset],
                )
                rows = cur.fetchall()

        messages = []
        for row in rows:
            msg = dict(row)
            if msg.get("metadata") and isinstance(msg["metadata"], str):
                try:
                    msg["metadata"] = json.loads(msg["metadata"])
                except Exception:
                    pass
            messages.append(msg)

        return {
            "messages": messages,
            "total": total,
            "pages": (total + per_page - 1) // per_page if total else 0,
            "current_page": page,
        }

    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """获取单条消息"""
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        message_id, message_type, title, content, source,
                        priority, ai_suggestion, metadata,
                        created_at::text AS created_at,
                        read, pushed, pushed_at::text AS pushed_at
                    FROM push_messages
                    WHERE message_id = %s
                    """,
                    (message_id,),
                )
                row = cur.fetchone()

        if not row:
            return None

        msg = dict(row)
        if msg.get("metadata") and isinstance(msg["metadata"], str):
            try:
                msg["metadata"] = json.loads(msg["metadata"])
            except Exception:
                pass
        return msg

    def push_message(self, message_id: str) -> bool:
        """
        推送消息到所有 SSE 客户端

        Args:
            message_id: 消息 ID

        Returns:
            是否推送成功
        """
        message = self.get_message(message_id)
        if not message:
            return False

        pushed_at = datetime.utcnow().isoformat(timespec="seconds") + "Z"

        # 更新数据库中的推送状态
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE push_messages
                    SET pushed = TRUE, pushed_at = %s
                    WHERE message_id = %s
                    """,
                    (pushed_at, message_id),
                )

        message["pushed"] = True
        message["pushed_at"] = pushed_at

        # 广播到所有 SSE 客户端
        self._broadcast(message)
        return True

    def mark_read(self, message_id: str) -> bool:
        """标记消息为已读"""
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE push_messages SET read = TRUE WHERE message_id = %s",
                    (message_id,),
                )
                return cur.rowcount > 0

    def delete_message(self, message_id: str) -> bool:
        """删除消息"""
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM push_messages WHERE message_id = %s",
                    (message_id,),
                )
                return cur.rowcount > 0

    def get_pending_messages(
        self,
        message_type: Optional[str] = None,
        since: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """
        获取待推送的消息（轮询降级方案）

        Args:
            message_type: 筛选消息类型
            since: 只返回此时间之后的消息 (ISO 格式)

        Returns:
            未读消息列表
        """
        conditions = ["pushed = TRUE", "read = FALSE"]
        params = []

        if message_type:
            conditions.append("message_type = %s")
            params.append(message_type)

        if since:
            conditions.append("pushed_at > %s")
            params.append(since)

        where_clause = "WHERE " + " AND ".join(conditions)

        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT
                        message_id, message_type, title, content, source,
                        priority, ai_suggestion, metadata,
                        created_at::text AS created_at,
                        read, pushed, pushed_at::text AS pushed_at
                    FROM push_messages
                    {where_clause}
                    ORDER BY pushed_at ASC
                    LIMIT 50
                    """,
                    params,
                )
                rows = cur.fetchall()

        messages = []
        for row in rows:
            msg = dict(row)
            if msg.get("metadata") and isinstance(msg["metadata"], str):
                try:
                    msg["metadata"] = json.loads(msg["metadata"])
                except Exception:
                    pass
            messages.append(msg)

        return messages

    # ========================
    # SSE 相关方法
    # ========================

    def subscribe(self) -> queue.Queue:
        """
        订阅 SSE 事件流

        Returns:
            事件队列，用于接收推送消息
        """
        q = queue.Queue()
        with self._lock:
            self._subscribers.append(q)
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """取消订阅"""
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def _broadcast(self, message: Dict[str, Any]) -> None:
        """广播消息到所有订阅者"""
        event_data = json.dumps(message, ensure_ascii=False)
        with self._lock:
            dead_queues = []
            for q in self._subscribers:
                try:
                    q.put_nowait(event_data)
                except queue.Full:
                    dead_queues.append(q)
            # 清理已满的队列
            for q in dead_queues:
                self._subscribers.remove(q)

    def event_stream(self, q: queue.Queue) -> Generator[str, None, None]:
        """
        生成 SSE 事件流

        Args:
            q: 订阅队列

        Yields:
            SSE 格式的事件数据
        """
        # 发送连接成功事件
        yield f"event: connected\ndata: {json.dumps({'status': 'connected'})}\n\n"

        try:
            while True:
                try:
                    # 设置超时以支持心跳
                    data = q.get(timeout=30)
                    yield f"event: message\ndata: {data}\n\n"
                except queue.Empty:
                    # 发送心跳保持连接
                    yield f"event: heartbeat\ndata: {json.dumps({'type': 'ping'})}\n\n"
        except GeneratorExit:
            pass
        finally:
            self.unsubscribe(q)


# 全局实例
push_service = PushService() if db_service else None
