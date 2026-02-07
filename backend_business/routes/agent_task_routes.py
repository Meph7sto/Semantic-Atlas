"""
Agent pending tasks routes.

Handles task approval/rejection for agent actions.
"""

from flask import Blueprint, jsonify, request

from backend_business.services.agent_task_service import agent_task_service

agent_task_bp = Blueprint("agent_task", __name__)


def _get_actor() -> str:
    """Get current user from request headers."""
    return (
        request.headers.get("X-Actor", "")
        or request.args.get("actor", "")
        or "anonymous"
    )


# ========================
# Task Management
# ========================
@agent_task_bp.route("", methods=["GET"])
def list_tasks():
    """List pending tasks for current user."""
    if not agent_task_service:
        return jsonify({"success": False, "error": "Agent 任务服务未初始化"}), 500

    user_id = _get_actor()
    project_id = request.args.get("project_id")
    status = request.args.get("status")  # Optional: filter by status
    limit = request.args.get("limit", 50, type=int)

    try:
        if status:
            tasks = agent_task_service.list_all_tasks(
                user_id=user_id,
                project_id=project_id,
                status=status,
                limit=limit,
            )
        else:
            # Default to pending tasks only
            tasks = agent_task_service.list_pending_tasks(
                user_id=user_id,
                project_id=project_id,
                limit=limit,
            )
        return jsonify({"success": True, "tasks": tasks})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@agent_task_bp.route("", methods=["POST"])
def create_task():
    """Create a new pending task (usually called by agent)."""
    if not agent_task_service:
        return jsonify({"success": False, "error": "Agent 任务服务未初始化"}), 500

    user_id = _get_actor()
    payload = request.get_json(silent=True) or {}

    task_type = (payload.get("task_type") or "").strip()
    title = (payload.get("title") or "").strip()
    description = payload.get("description")
    task_payload = payload.get("payload")
    session_id = payload.get("session_id")
    project_id = payload.get("project_id")

    if not task_type:
        return jsonify({"success": False, "error": "缺少 task_type"}), 400
    if not title:
        return jsonify({"success": False, "error": "缺少 title"}), 400

    try:
        task = agent_task_service.create_task(
            user_id=user_id,
            task_type=task_type,
            title=title,
            description=description,
            payload=task_payload,
            session_id=session_id,
            project_id=project_id,
        )
        return jsonify({"success": True, "data": task})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@agent_task_bp.route("/<task_id>", methods=["GET"])
def get_task(task_id: str):
    """Get a specific task."""
    if not agent_task_service:
        return jsonify({"success": False, "error": "Agent 任务服务未初始化"}), 500

    try:
        task = agent_task_service.get_task(task_id)
        if not task:
            return jsonify({"success": False, "error": "任务不存在"}), 404
        return jsonify({"success": True, "data": task})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@agent_task_bp.route("/<task_id>/approve", methods=["POST"])
def approve_task(task_id: str):
    """Approve a pending task."""
    if not agent_task_service:
        return jsonify({"success": False, "error": "Agent 任务服务未初始化"}), 500

    user_id = _get_actor()

    try:
        task = agent_task_service.approve_task(task_id, user_id)
        return jsonify({"success": True, "data": task})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@agent_task_bp.route("/<task_id>/reject", methods=["POST"])
def reject_task(task_id: str):
    """Reject a pending task."""
    if not agent_task_service:
        return jsonify({"success": False, "error": "Agent 任务服务未初始化"}), 500

    user_id = _get_actor()

    try:
        task = agent_task_service.reject_task(task_id, user_id)
        return jsonify({"success": True, "data": task})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 400
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


# ========================
# Notification Counts
# ========================
@agent_task_bp.route("/pending-count", methods=["GET"])
def get_pending_count():
    """Get pending task count for current user."""
    if not agent_task_service:
        return jsonify({"success": False, "error": "Agent 任务服务未初始化"}), 500

    user_id = _get_actor()
    project_id = request.args.get("project_id")

    try:
        count = agent_task_service.get_pending_count(
            user_id=user_id,
            project_id=project_id,
        )
        return jsonify({"success": True, "count": count})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
