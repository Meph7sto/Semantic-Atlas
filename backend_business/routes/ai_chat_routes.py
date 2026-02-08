"""
AI Chat routes.

Handles AI chat sessions and messages with LLM integration.
"""

from flask import Blueprint, Response, jsonify, request

from backend_business.services.ai_chat_service import ai_chat_service
from backend_business.services.agent_tools_service import agent_stream_service

ai_chat_bp = Blueprint("ai_chat", __name__)


def _get_actor() -> str:
    """Get current user from request headers."""
    return (
        request.headers.get("X-Actor", "")
        or request.args.get("actor", "")
        or "anonymous"
    )


# ========================
# Session Management
# ========================
@ai_chat_bp.route("/sessions", methods=["GET"])
def list_sessions():
    """List chat sessions for current user."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    user_id = _get_actor()
    project_id = request.args.get("project_id")
    limit = request.args.get("limit", 50, type=int)

    try:
        sessions = ai_chat_service.list_sessions(
            user_id=user_id,
            project_id=project_id,
            limit=limit,
        )
        return jsonify({"success": True, "sessions": sessions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_chat_bp.route("/sessions", methods=["POST"])
def create_session():
    """Create a new chat session."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    user_id = _get_actor()
    payload = request.get_json(silent=True) or {}
    project_id = payload.get("project_id")
    title = payload.get("title")

    try:
        session = ai_chat_service.create_session(
            user_id=user_id,
            project_id=project_id,
            title=title,
        )
        return jsonify({"success": True, "data": session})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_chat_bp.route("/sessions/current", methods=["GET"])
def get_or_create_current_session():
    """Get or create the current session for user/project."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    user_id = _get_actor()
    project_id = request.args.get("project_id")

    try:
        session = ai_chat_service.get_or_create_session(
            user_id=user_id,
            project_id=project_id,
        )
        return jsonify({"success": True, "data": session})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_chat_bp.route("/sessions/<session_id>", methods=["GET"])
def get_session(session_id: str):
    """Get a specific session."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    user_id = _get_actor()

    try:
        session = ai_chat_service._ensure_session_access(
            session_id=session_id, user_id=user_id
        )
        return jsonify({"success": True, "data": session})
    except Exception as e:
        msg = str(e)
        if msg == "session not found":
            return jsonify({"success": False, "error": "会话不存在"}), 404
        return jsonify({"success": False, "error": msg}), 500


@ai_chat_bp.route("/sessions/<session_id>", methods=["PATCH"])
def update_session(session_id: str):
    """Update session title."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    payload = request.get_json(silent=True) or {}
    title = payload.get("title")

    user_id = _get_actor()

    try:
        ai_chat_service._ensure_session_access(session_id=session_id, user_id=user_id)
        success = ai_chat_service.update_session(session_id, title=title)
        if not success:
            return jsonify({"success": False, "error": "会话不存在"}), 404
        session = ai_chat_service.get_session(session_id)
        return jsonify({"success": True, "data": session})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_chat_bp.route("/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id: str):
    """Delete a session and all its messages."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    user_id = _get_actor()

    try:
        ai_chat_service._ensure_session_access(session_id=session_id, user_id=user_id)
        success = ai_chat_service.delete_session(session_id)
        if not success:
            return jsonify({"success": False, "error": "会话不存在"}), 404
        return jsonify({"success": True})
    except Exception as e:
        msg = str(e)
        if msg == "session not found":
            return jsonify({"success": False, "error": "会话不存在"}), 404
        return jsonify({"success": False, "error": msg}), 500


# ========================
# Message Management
# ========================
@ai_chat_bp.route("/sessions/<session_id>/messages", methods=["GET"])
def list_messages(session_id: str):
    """List messages in a session with pagination."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    limit = request.args.get("limit", 50, type=int)
    before = request.args.get("before")

    user_id = _get_actor()

    try:
        messages = ai_chat_service.list_messages(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
            before=before,
        )
        return jsonify({"success": True, "messages": messages})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_chat_bp.route("/sessions/<session_id>/messages", methods=["POST"])
def send_message(session_id: str):
    """Send a message and get AI reply (non-streaming)."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    system_prompt = payload.get("system_prompt")
    use_thinking = payload.get("use_thinking", False)

    user_id = _get_actor()

    if not content:
        return jsonify({"success": False, "error": "缺少 content"}), 400

    try:
        result = ai_chat_service.send_message_and_get_reply(
            session_id=session_id,
            user_id=user_id,
            user_content=content,
            system_prompt=system_prompt,
            use_thinking_mode=use_thinking,
        )
        return jsonify({"success": True, "data": result})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@ai_chat_bp.route("/sessions/<session_id>/messages/stream", methods=["POST"])
def send_message_stream(session_id: str):
    """Send a message and stream the AI reply."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    system_prompt = payload.get("system_prompt")
    use_thinking = payload.get("use_thinking", False)

    user_id = _get_actor()

    if not content:
        return jsonify({"success": False, "error": "缺少 content"}), 400

    def generate():
        try:
            yield from ai_chat_service.stream_message_reply(
                session_id=session_id,
                user_id=user_id,
                user_content=content,
                system_prompt=system_prompt,
                use_thinking_mode=use_thinking,
            )
        except Exception as e:
            import json

            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@ai_chat_bp.route("/sessions/<session_id>/messages/agent/stream", methods=["POST"])
def send_agent_message_stream(session_id: str):
    """
    Send a message and stream the AI agent reply with tool calling support.

    This endpoint:
    - Saves user message to database
    - Calls inference backend with tools definition
    - Streams tool_call, task_created, and content events
    - Creates pending tasks for write operations (require user approval)
    """
    if not agent_stream_service:
        return jsonify({"success": False, "error": "Agent 服务未初始化"}), 500

    payload = request.get_json(silent=True) or {}
    content = (payload.get("content") or "").strip()
    project_id = payload.get("project_id")

    user_id = _get_actor()

    if not content:
        return jsonify({"success": False, "error": "缺少 content"}), 400

    def generate():
        try:
            yield from agent_stream_service.stream_agent_reply(
                session_id=session_id,
                user_id=user_id,
                user_content=content,
                project_id=project_id,
            )
        except Exception as e:
            import json

            yield f"event: error\ndata: {json.dumps({'error': str(e)})}\n\n"

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@ai_chat_bp.route("/sessions/<session_id>/read", methods=["POST"])
def mark_read(session_id: str):
    """Mark all messages in a session as read."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    user_id = _get_actor()

    try:
        count = ai_chat_service.mark_messages_read(session_id, user_id=user_id)
        return jsonify({"success": True, "marked_count": count})
    except Exception as e:
        msg = str(e)
        if msg == "session not found":
            return jsonify({"success": False, "error": "会话不存在"}), 404
        return jsonify({"success": False, "error": msg}), 500


# ========================
# Notification Counts
# ========================
@ai_chat_bp.route("/unread-count", methods=["GET"])
def get_unread_count():
    """Get unread message count for current user."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    user_id = _get_actor()
    project_id = request.args.get("project_id")

    try:
        count = ai_chat_service.get_unread_count(
            user_id=user_id,
            project_id=project_id,
        )
        return jsonify({"success": True, "count": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ========================
# SSE Real-time Updates
# ========================
@ai_chat_bp.route("/sessions/<session_id>/stream", methods=["GET"])
def sse_stream(session_id: str):
    """SSE stream for real-time message updates."""
    if not ai_chat_service:
        return jsonify({"success": False, "error": "AI 聊天服务未初始化"}), 500

    q = ai_chat_service.subscribe(session_id)

    def generate():
        yield from ai_chat_service.event_stream(q, session_id)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
