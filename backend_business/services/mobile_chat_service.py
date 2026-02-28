"""
Mobile chat bridge service.

Stores and broadcasts messages between mobile and web clients via SSE.
"""
import json
import queue
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, Generator, List, Optional, Tuple

from psycopg2.extras import RealDictCursor

from backend_business.services.db_service import db_service


class MobileChatService:
    def __init__(self) -> None:
        self._subscribers: List[Tuple[str, str, queue.Queue]] = []
        self._lock = threading.Lock()

    def create_message(
        self,
        user_id: str,
        session_id: str,
        sender: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        if sender not in ("web", "mobile"):
            raise ValueError("sender must be 'web' or 'mobile'")
        if not user_id:
            raise ValueError("user_id is required")
        if not session_id:
            raise ValueError("session_id is required")
        if not content:
            raise ValueError("content is required")

        message_id = f"mchat_{uuid.uuid4().hex[:12]}"
        created_at = datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")

        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO mobile_chat_messages (
                        message_id, user_id, session_id, sender, content, metadata, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        message_id,
                        user_id,
                        session_id,
                        sender,
                        content,
                        json.dumps(metadata, ensure_ascii=False) if metadata else None,
                        created_at,
                    ),
                )

        message = {
            "message_id": message_id,
            "user_id": user_id,
            "session_id": session_id,
            "sender": sender,
            "content": content,
            "metadata": metadata,
            "created_at": created_at,
        }

        self._broadcast(message)
        return message

    def list_messages(
        self,
        user_id: str,
        session_id: str,
        limit: int = 100,
        since: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        limit = max(1, min(500, int(limit)))
        params: List[Any] = [user_id, session_id]
        where_clause = "WHERE user_id = %s AND session_id = %s"

        if since:
            where_clause += " AND created_at > %s"
            params.append(since)

        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT
                        message_id, user_id, session_id, sender, content, metadata,
                        created_at::text AS created_at
                    FROM mobile_chat_messages
                    {where_clause}
                    ORDER BY created_at ASC
                    LIMIT %s
                    """,
                    params + [limit],
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

    def list_sessions(self, user_id: str, limit: int = 200) -> List[Dict[str, Any]]:
        limit = max(1, min(1000, int(limit)))
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        user_id,
                        session_id,
                        COUNT(1) AS message_count,
                        MAX(created_at)::text AS last_message_at
                    FROM mobile_chat_messages
                    WHERE user_id = %s
                    GROUP BY user_id, session_id
                    ORDER BY MAX(created_at) DESC
                    LIMIT %s
                    """,
                    (user_id, limit),
                )
                rows = cur.fetchall()
        return [dict(row) for row in rows]

    # ========================
    # SSE
    # ========================
    def subscribe(self, user_id: str, session_id: str) -> queue.Queue:
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.append((user_id, session_id, q))
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        with self._lock:
            for item in list(self._subscribers):
                if item[2] is q:
                    self._subscribers.remove(item)

    def _broadcast(self, message: Dict[str, Any]) -> None:
        event_data = json.dumps(message, ensure_ascii=False)
        with self._lock:
            dead_items = []
            for user_id, session_id, q in self._subscribers:
                if user_id != message.get("user_id"):
                    continue
                if session_id != message.get("session_id"):
                    continue
                try:
                    q.put_nowait(event_data)
                except queue.Full:
                    dead_items.append((user_id, session_id, q))
            for item in dead_items:
                if item in self._subscribers:
                    self._subscribers.remove(item)

    def event_stream(self, q: queue.Queue, user_id: str, session_id: str) -> Generator[str, None, None]:
        yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'user_id': user_id, 'session_id': session_id})}\n\n"
        try:
            while True:
                try:
                    data = q.get(timeout=25)
                    yield f"event: message\ndata: {data}\n\n"
                except queue.Empty:
                    yield f"event: heartbeat\ndata: {json.dumps({'type': 'ping'})}\n\n"
        except GeneratorExit:
            pass
        finally:
            self.unsubscribe(q)


mobile_chat_service = MobileChatService() if db_service else None
