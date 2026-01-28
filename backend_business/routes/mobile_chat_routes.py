"""
Mobile chat bridge routes.
"""
from flask import Blueprint, Response, jsonify, request

from backend_business.services.mobile_chat_service import mobile_chat_service

mobile_chat_bp = Blueprint("mobile_chat", __name__)


@mobile_chat_bp.route("/sessions", methods=["GET"])
def list_sessions():
    if not mobile_chat_service:
        return jsonify({"success": False, "error": "移动端聊天服务未初始化"}), 500

    limit = request.args.get("limit", 200, type=int)
    try:
        sessions = mobile_chat_service.list_sessions(limit=limit)
        return jsonify({"success": True, "sessions": sessions})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@mobile_chat_bp.route("/messages", methods=["GET"])
def list_messages():
    if not mobile_chat_service:
        return jsonify({"success": False, "error": "移动端聊天服务未初始化"}), 500

    session_id = (request.args.get("session_id") or "").strip()
    limit = request.args.get("limit", 100, type=int)
    since = request.args.get("since")

    if not session_id:
        return jsonify({"success": False, "error": "缺少 session_id"}), 400

    try:
        messages = mobile_chat_service.list_messages(
            session_id=session_id,
            limit=limit,
            since=since,
        )
        return jsonify({"success": True, "messages": messages})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@mobile_chat_bp.route("/messages", methods=["POST"])
def create_message():
    if not mobile_chat_service:
        return jsonify({"success": False, "error": "移动端聊天服务未初始化"}), 500

    payload = request.get_json(silent=True) or {}
    session_id = (payload.get("session_id") or "").strip()
    sender = (payload.get("sender") or "").strip()
    content = (payload.get("content") or "").strip()

    if not session_id:
        return jsonify({"success": False, "error": "缺少 session_id"}), 400
    if not sender:
        return jsonify({"success": False, "error": "缺少 sender"}), 400
    if not content:
        return jsonify({"success": False, "error": "缺少 content"}), 400

    try:
        message = mobile_chat_service.create_message(
            session_id=session_id,
            sender=sender,
            content=content,
            metadata=payload.get("metadata"),
        )
        return jsonify({"success": True, "data": message})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@mobile_chat_bp.route("/messages/pending", methods=["GET"])
def get_pending_messages():
    if not mobile_chat_service:
        return jsonify({"success": False, "error": "移动端聊天服务未初始化"}), 500

    session_id = (request.args.get("session_id") or "").strip()
    since = request.args.get("since")
    limit = request.args.get("limit", 100, type=int)

    if not session_id:
        return jsonify({"success": False, "error": "缺少 session_id"}), 400

    try:
        messages = mobile_chat_service.list_messages(
            session_id=session_id,
            limit=limit,
            since=since,
        )
        return jsonify({"success": True, "messages": messages})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@mobile_chat_bp.route("/stream", methods=["GET"])
def sse_stream():
    if not mobile_chat_service:
        return jsonify({"success": False, "error": "移动端聊天服务未初始化"}), 500

    session_id = (request.args.get("session_id") or "").strip()
    if not session_id:
        return jsonify({"success": False, "error": "缺少 session_id"}), 400

    q = mobile_chat_service.subscribe(session_id)

    def generate():
        yield from mobile_chat_service.event_stream(q, session_id)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
