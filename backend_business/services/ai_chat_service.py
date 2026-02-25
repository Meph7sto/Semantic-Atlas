"""
AI Chat service.

Manages AI chat sessions and messages with project/user association.
Supports streaming responses from LLM and SSE for real-time updates.
"""

import json
import queue
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, Generator, List, Optional, Tuple

import requests
from psycopg2.extras import RealDictCursor

from backend_business.config import settings
from backend_business.services.db_service import db_service
from backend_business.services.db_service_parts.utils import _utc_now_iso


class SessionAccessError(Exception):
    """Raised when a session is missing or not accessible by the actor."""


def _inference_base_url() -> str:
    return (settings.INFERENCE_BASE_URL or "http://localhost:8000").rstrip("/")


class AiChatService:
    def __init__(self) -> None:
        self._subscribers: List[Tuple[str, queue.Queue]] = []
        self._lock = threading.Lock()

    # ========================
    # Session Management
    # ========================
    def _ensure_session_access(self, session_id: str, user_id: str) -> Dict[str, Any]:
        if not session_id:
            raise SessionAccessError("session_id is required")
        if not user_id:
            raise SessionAccessError("user_id is required")

        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        session_id, project_id, user_id, title,
                        to_char(created_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS created_at,
                        to_char(updated_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS updated_at
                    FROM ai_chat_sessions
                    WHERE session_id = %s AND user_id = %s
                    """,
                    (session_id, user_id),
                )
                row = cur.fetchone()

        if not row:
            raise SessionAccessError("session not found")
        return dict(row)

    def create_session(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        title: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a new chat session."""
        if not user_id:
            raise ValueError("user_id is required")

        session_id = f"aisess_{uuid.uuid4().hex[:12]}"
        now = _utc_now_iso(timespec="milliseconds")

        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ai_chat_sessions (
                        session_id, project_id, user_id, title, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s::timestamptz, %s::timestamptz)
                    """,
                    (session_id, project_id, user_id, title, now, now),
                )

        return {
            "session_id": session_id,
            "project_id": project_id,
            "user_id": user_id,
            "title": title,
            "created_at": now,
            "updated_at": now,
        }

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get a session by ID."""
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT
                        session_id, project_id, user_id, title,
                        to_char(created_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS created_at,
                        to_char(updated_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS updated_at
                    FROM ai_chat_sessions
                    WHERE session_id = %s
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
        return dict(row) if row else None

    def get_or_create_session(
        self,
        user_id: str,
        project_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Get the latest session for user/project or create a new one."""
        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                # Find the most recent session for this user/project
                if project_id:
                    cur.execute(
                        """
                        SELECT
                            session_id, project_id, user_id, title,
                            to_char(created_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS created_at,
                            to_char(updated_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS updated_at
                        FROM ai_chat_sessions
                        WHERE user_id = %s AND project_id = %s
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """,
                        (user_id, project_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT
                            session_id, project_id, user_id, title,
                            to_char(created_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS created_at,
                            to_char(updated_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS updated_at
                        FROM ai_chat_sessions
                        WHERE user_id = %s AND project_id IS NULL
                        ORDER BY updated_at DESC
                        LIMIT 1
                        """,
                        (user_id,),
                    )
                row = cur.fetchone()

        if row:
            return dict(row)
        return self.create_session(user_id=user_id, project_id=project_id)

    def list_sessions(
        self,
        user_id: str,
        project_id: Optional[str] = None,
        limit: int = 50,
    ) -> List[Dict[str, Any]]:
        """List sessions for a user, optionally filtered by project."""
        limit = max(1, min(200, int(limit)))
        params: List[Any] = [user_id]
        where_clause = "WHERE user_id = %s"

        if project_id:
            where_clause += " AND project_id = %s"
            params.append(project_id)

        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT
                        s.session_id, s.project_id, s.user_id, s.title,
                        to_char(s.created_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS created_at,
                        to_char(s.updated_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS updated_at,
                        (SELECT COUNT(*) FROM ai_chat_messages m WHERE m.session_id = s.session_id) AS message_count,
                        (SELECT COUNT(*) FROM ai_chat_messages m WHERE m.session_id = s.session_id AND m.is_read = FALSE AND m.role = 'assistant') AS unread_count
                    FROM ai_chat_sessions s
                    {where_clause}
                    ORDER BY s.updated_at DESC
                    LIMIT %s
                    """,
                    params + [limit],
                )
                rows = cur.fetchall()

        return [dict(row) for row in rows]

    def update_session(
        self,
        session_id: str,
        title: Optional[str] = None,
    ) -> bool:
        """Update session title and updated_at timestamp."""
        now = _utc_now_iso(timespec="milliseconds")
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                if title is not None:
                    cur.execute(
                        """
                        UPDATE ai_chat_sessions
                        SET title = %s, updated_at = %s::timestamptz
                        WHERE session_id = %s
                        """,
                        (title, now, session_id),
                    )
                else:
                    cur.execute(
                        """
                        UPDATE ai_chat_sessions
                        SET updated_at = %s::timestamptz
                        WHERE session_id = %s
                        """,
                        (now, session_id),
                    )
                return cur.rowcount > 0

    def delete_session(self, session_id: str) -> bool:
        """Delete a session and all its messages."""
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM ai_chat_sessions WHERE session_id = %s",
                    (session_id,),
                )
                return cur.rowcount > 0

    # ========================
    # Message Management
    # ========================
    def create_message(
        self,
        session_id: str,
        user_id: Optional[str],
        role: str,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        is_read: bool = False,
    ) -> Dict[str, Any]:
        """Create a new message in a session."""
        if role not in ("user", "assistant", "system"):
            raise ValueError("role must be 'user', 'assistant', or 'system'")
        if not session_id:
            raise ValueError("session_id is required")
        if not content:
            raise ValueError("content is required")

        if user_id:
            # Prevent cross-user access / data pollution.
            self._ensure_session_access(session_id=session_id, user_id=user_id)

        message_id = f"aimsg_{uuid.uuid4().hex[:12]}"
        created_at = _utc_now_iso(timespec="milliseconds")

        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO ai_chat_messages (
                        message_id, session_id, role, content, metadata, is_read, created_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s::timestamptz)
                    """,
                    (
                        message_id,
                        session_id,
                        role,
                        content,
                        json.dumps(metadata, ensure_ascii=False) if metadata else None,
                        is_read,
                        created_at,
                    ),
                )

        # Update session's updated_at
        self.update_session(session_id)

        message = {
            "message_id": message_id,
            "session_id": session_id,
            "role": role,
            "content": content,
            "metadata": metadata,
            "is_read": is_read,
            "created_at": created_at,
        }

        # Broadcast to SSE subscribers
        self._broadcast(message)
        return message

    def list_messages(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        limit: int = 50,
        before: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """List messages in a session with pagination."""
        if user_id:
            self._ensure_session_access(session_id=session_id, user_id=user_id)

        limit = max(1, min(500, int(limit)))
        params: List[Any] = [session_id]
        where_clause = "WHERE session_id = %s"

        if before:
            where_clause += " AND created_at < %s"
            params.append(before)

        with db_service._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    f"""
                    SELECT
                        message_id, session_id, role, content, metadata, is_read,
                        to_char(created_at AT TIME ZONE 'utc', 'YYYY-MM-DD"T"HH24:MI:SS.MS"Z"') AS created_at
                    FROM ai_chat_messages
                    {where_clause}
                    ORDER BY created_at DESC
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

        # Return in chronological order
        messages.reverse()
        return messages

    def mark_messages_read(self, session_id: str, user_id: Optional[str] = None) -> int:
        """Mark all assistant messages in a session as read."""
        if user_id:
            self._ensure_session_access(session_id=session_id, user_id=user_id)

        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE ai_chat_messages
                    SET is_read = TRUE
                    WHERE session_id = %s AND role = 'assistant' AND is_read = FALSE
                    """,
                    (session_id,),
                )
                return cur.rowcount

    def get_unread_count(
        self,
        user_id: str,
        project_id: Optional[str] = None,
    ) -> int:
        """Get count of unread assistant messages for a user."""
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                if project_id:
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM ai_chat_messages m
                        JOIN ai_chat_sessions s ON m.session_id = s.session_id
                        WHERE s.user_id = %s AND s.project_id = %s
                          AND m.role = 'assistant' AND m.is_read = FALSE
                        """,
                        (user_id, project_id),
                    )
                else:
                    cur.execute(
                        """
                        SELECT COUNT(*)
                        FROM ai_chat_messages m
                        JOIN ai_chat_sessions s ON m.session_id = s.session_id
                        WHERE s.user_id = %s
                          AND m.role = 'assistant' AND m.is_read = FALSE
                        """,
                        (user_id,),
                    )
                result = cur.fetchone()
                return result[0] if result else 0

    # ========================
    # LLM Integration
    # ========================
    def send_message_and_get_reply(
        self,
        session_id: str,
        user_id: str,
        user_content: str,
        system_prompt: Optional[str] = None,
        use_thinking_mode: bool = False,
    ) -> Dict[str, Any]:
        """
        Send a user message and get AI reply.
        This is a non-streaming version that waits for full response.
        """
        # Save user message first
        user_msg = self.create_message(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=user_content,
            is_read=True,  # User's own message is always read
        )

        # Get conversation history for context
        history = self.list_messages(session_id, user_id=user_id, limit=20)

        # Build prompt with context
        context_prompt = ""
        for msg in history[:-1]:  # Exclude the message we just added
            role_label = "User" if msg["role"] == "user" else "Assistant"
            context_prompt += f"{role_label}: {msg['content']}\n\n"
        context_prompt += f"User: {user_content}"

        # Call inference backend
        try:
            response = requests.post(
                f"{_inference_base_url()}/chat/stream",
                json={
                    "prompt": context_prompt,
                    "system_prompt": system_prompt
                    or "You are a helpful AI assistant for requirements engineering.",
                    "max_new_tokens": 2000,
                    "use_thinking_mode": use_thinking_mode,
                    "use_async_client": False,
                },
                stream=True,
                timeout=120,
            )
            response.raise_for_status()

            # Parse streaming response
            full_content = ""
            thinking_content = ""

            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                    if data.get("type") == "token":
                        full_content += data.get("content", "")
                    elif data.get("type") == "thinking":
                        thinking_content += data.get("content", "")
                    elif data.get("type") == "result":
                        full_content = data.get("data", {}).get("answer", full_content)
                except json.JSONDecodeError:
                    continue

            # Save assistant message
            metadata = (
                {"thinking_content": thinking_content} if thinking_content else None
            )
            assistant_msg = self.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=full_content or "Sorry, I could not generate a response.",
                metadata=metadata,
                is_read=False,
            )

            return {
                "user_message": user_msg,
                "assistant_message": assistant_msg,
            }

        except requests.RequestException as e:
            # Save error message
            error_msg = self.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=f"Sorry, an error occurred: {str(e)}",
                metadata={"error": True},
                is_read=False,
            )
            return {
                "user_message": user_msg,
                "assistant_message": error_msg,
                "error": str(e),
            }

    def stream_message_reply(
        self,
        session_id: str,
        user_id: str,
        user_content: str,
        system_prompt: Optional[str] = None,
        use_thinking_mode: bool = False,
    ) -> Generator[str, None, None]:
        """
        Send a user message and stream the AI reply.
        Yields SSE-formatted events.
        """
        # Save user message first
        user_msg = self.create_message(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=user_content,
            is_read=True,
        )

        yield f"event: user_message\ndata: {json.dumps(user_msg, ensure_ascii=False)}\n\n"

        # Get conversation history for context
        history = self.list_messages(session_id, user_id=user_id, limit=20)

        # Build prompt with context
        context_prompt = ""
        for msg in history[:-1]:
            role_label = "User" if msg["role"] == "user" else "Assistant"
            context_prompt += f"{role_label}: {msg['content']}\n\n"
        context_prompt += f"User: {user_content}"

        try:
            response = requests.post(
                f"{_inference_base_url()}/chat/stream",
                json={
                    "prompt": context_prompt,
                    "system_prompt": system_prompt
                    or "You are a helpful AI assistant for requirements engineering.",
                    "max_new_tokens": 2000,
                    "use_thinking_mode": use_thinking_mode,
                    "use_async_client": False,
                },
                stream=True,
                timeout=120,
            )
            response.raise_for_status()

            full_content = ""
            thinking_content = ""

            for line in response.iter_lines():
                if not line:
                    continue
                try:
                    data = json.loads(line.decode("utf-8"))
                    if data.get("type") == "token":
                        token = data.get("content", "")
                        full_content += token
                        yield f"event: token\ndata: {json.dumps({'content': token}, ensure_ascii=False)}\n\n"
                    elif data.get("type") == "thinking":
                        thinking = data.get("content", "")
                        thinking_content += thinking
                        yield f"event: thinking\ndata: {json.dumps({'content': thinking}, ensure_ascii=False)}\n\n"
                    elif data.get("type") == "result":
                        final_answer = data.get("data", {}).get("answer", "")
                        if final_answer and final_answer != full_content:
                            full_content = final_answer
                except json.JSONDecodeError:
                    continue

            # Save assistant message
            metadata = (
                {"thinking_content": thinking_content} if thinking_content else None
            )
            assistant_msg = self.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=full_content or "Sorry, I could not generate a response.",
                metadata=metadata,
                is_read=False,
            )

            yield f"event: assistant_message\ndata: {json.dumps(assistant_msg, ensure_ascii=False)}\n\n"
            yield f"event: done\ndata: {json.dumps({'status': 'completed'})}\n\n"

        except requests.RequestException as e:
            error_msg = self.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=f"Sorry, an error occurred: {str(e)}",
                metadata={"error": True},
                is_read=False,
            )
            yield f"event: error\ndata: {json.dumps({'error': str(e), 'message': error_msg}, ensure_ascii=False)}\n\n"

    # ========================
    # SSE Real-time Updates
    # ========================
    def subscribe(self, session_id: str) -> queue.Queue:
        """Subscribe to real-time updates for a session."""
        q: queue.Queue = queue.Queue()
        with self._lock:
            self._subscribers.append((session_id, q))
        return q

    def unsubscribe(self, q: queue.Queue) -> None:
        """Unsubscribe from real-time updates."""
        with self._lock:
            for item in list(self._subscribers):
                if item[1] is q:
                    self._subscribers.remove(item)

    def _broadcast(self, message: Dict[str, Any]) -> None:
        """Broadcast a message to all subscribers of its session."""
        event_data = json.dumps(message, ensure_ascii=False)
        with self._lock:
            dead_items = []
            for session_id, q in self._subscribers:
                if session_id != message.get("session_id"):
                    continue
                try:
                    q.put_nowait(event_data)
                except queue.Full:
                    dead_items.append((session_id, q))
            for item in dead_items:
                if item in self._subscribers:
                    self._subscribers.remove(item)

    def event_stream(
        self, q: queue.Queue, session_id: str
    ) -> Generator[str, None, None]:
        """Generate SSE events for a session subscription."""
        yield f"event: connected\ndata: {json.dumps({'status': 'connected', 'session_id': session_id})}\n\n"
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


ai_chat_service = AiChatService() if db_service else None
