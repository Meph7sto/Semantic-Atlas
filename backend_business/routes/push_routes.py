"""
消息推送 API 路由

提供消息管理和 SSE 实时推送接口
"""
from flask import Blueprint, Response, jsonify, request

from backend_business.services.push_service import push_service

push_bp = Blueprint("push", __name__)


@push_bp.route("/messages", methods=["GET"])
def list_messages():
    """获取消息列表"""
    if not push_service:
        return jsonify({"success": False, "error": "推送服务未初始化"}), 500

    message_type = request.args.get("message_type")
    pushed = request.args.get("pushed")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    # 解析 pushed 参数
    pushed_bool = None
    if pushed is not None:
        pushed_bool = pushed.lower() in ("true", "1", "yes")

    try:
        result = push_service.list_messages(
            message_type=message_type,
            pushed=pushed_bool,
            page=page,
            per_page=per_page,
        )
        return jsonify({"success": True, **result})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@push_bp.route("/messages", methods=["POST"])
def create_message():
    """创建新消息"""
    if not push_service:
        return jsonify({"success": False, "error": "推送服务未初始化"}), 500

    payload = request.get_json(silent=True) or {}

    message_type = payload.get("message_type", "").strip()
    title = payload.get("title", "").strip()

    if not message_type:
        return jsonify({"success": False, "error": "缺少 message_type"}), 400
    if not title:
        return jsonify({"success": False, "error": "缺少 title"}), 400

    try:
        message = push_service.create_message(
            message_type=message_type,
            title=title,
            content=payload.get("content"),
            source=payload.get("source"),
            priority=payload.get("priority", "medium"),
            ai_suggestion=payload.get("ai_suggestion"),
            metadata=payload.get("metadata"),
        )
        return jsonify({"success": True, "data": message})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@push_bp.route("/messages/<message_id>", methods=["GET"])
def get_message(message_id: str):
    """获取单条消息"""
    if not push_service:
        return jsonify({"success": False, "error": "推送服务未初始化"}), 500

    message = push_service.get_message(message_id)
    if not message:
        return jsonify({"success": False, "error": "消息不存在"}), 404

    return jsonify({"success": True, "data": message})


@push_bp.route("/messages/<message_id>/push", methods=["POST"])
def push_message(message_id: str):
    """推送消息到客户端"""
    if not push_service:
        return jsonify({"success": False, "error": "推送服务未初始化"}), 500

    try:
        success = push_service.push_message(message_id)
        if not success:
            return jsonify({"success": False, "error": "消息不存在"}), 404
        return jsonify({"success": True, "message": "消息已推送"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@push_bp.route("/messages/<message_id>/read", methods=["POST"])
def mark_read(message_id: str):
    """标记消息为已读"""
    if not push_service:
        return jsonify({"success": False, "error": "推送服务未初始化"}), 500

    success = push_service.mark_read(message_id)
    if not success:
        return jsonify({"success": False, "error": "消息不存在"}), 404

    return jsonify({"success": True, "message": "已标记为已读"})


@push_bp.route("/messages/<message_id>", methods=["DELETE"])
def delete_message(message_id: str):
    """删除消息"""
    if not push_service:
        return jsonify({"success": False, "error": "推送服务未初始化"}), 500

    success = push_service.delete_message(message_id)
    if not success:
        return jsonify({"success": False, "error": "消息不存在"}), 404

    return jsonify({"success": True, "message": "消息已删除"})


@push_bp.route("/messages/pending", methods=["GET"])
def get_pending_messages():
    """
    获取待处理消息（轮询降级方案）

    用于 SSE 不可用时的降级方案
    """
    if not push_service:
        return jsonify({"success": False, "error": "推送服务未初始化"}), 500

    message_type = request.args.get("message_type")
    since = request.args.get("since")

    try:
        messages = push_service.get_pending_messages(
            message_type=message_type,
            since=since,
        )
        return jsonify({"success": True, "messages": messages})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@push_bp.route("/stream", methods=["GET"])
def sse_stream():
    """
    SSE 实时消息流

    客户端连接此端点后，将实时接收推送消息
    支持的事件类型：
    - connected: 连接成功
    - message: 新消息推送
    - heartbeat: 心跳保活
    """
    if not push_service:
        return jsonify({"success": False, "error": "推送服务未初始化"}), 500

    # 订阅消息流
    q = push_service.subscribe()

    def generate():
        yield from push_service.event_stream(q)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",  # 禁用 Nginx 缓冲
        },
    )
