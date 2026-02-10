"""Agent collaboration monitor routes.

Provides read-only APIs for:
- agent roster
- channel list
- inter-agent messages
- derived action timeline
- approval task list
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from flask import Blueprint, jsonify, request

from backend_business.services.agent import agent_task_queue as agent_task_service
from backend_business.services.agent.messaging import message_bus
from backend_business.services.agent.messaging.channel import channel_manager
from backend_business.services.agent.registry import agent_registry

agent_monitor_bp = Blueprint("agent_monitor", __name__)


def _get_actor() -> str:
    return (
        request.headers.get("X-Actor", "")
        or request.args.get("actor", "")
        or "anonymous"
    )


def _parse_ts(value: Optional[str]) -> datetime:
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    try:
        # Handle "...Z"
        if value.endswith("Z"):
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        else:
            dt = datetime.fromisoformat(value)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.min.replace(tzinfo=timezone.utc)


def _extract_project_id(message_dict: Dict[str, Any]) -> Optional[str]:
    content = message_dict.get("content")
    if not isinstance(content, dict):
        return None
    if content.get("project_id"):
        return str(content.get("project_id"))

    # Some nested payloads may include project info.
    for key in ("task_context", "query_context", "result"):
        node = content.get(key)
        if isinstance(node, dict) and node.get("project_id"):
            return str(node.get("project_id"))
    return None


def _filter_messages_by_project(
    messages: List[Dict[str, Any]], project_id: Optional[str]
) -> List[Dict[str, Any]]:
    """Keep messages relevant to project, including replies in matched channels."""
    if not project_id:
        return messages

    matched = [m for m in messages if m.get("project_id") == project_id]
    if not matched:
        return []

    matched_channel_ids = {
        m.get("channel_id") for m in matched if m.get("channel_id")
    }
    return [
        m
        for m in messages
        if m.get("project_id") == project_id
        or (m.get("channel_id") and m.get("channel_id") in matched_channel_ids)
    ]


def _message_to_dict(message) -> Dict[str, Any]:
    data = message.to_dict()
    channel = channel_manager.get_channel(data.get("channel_id", ""))
    data["channel_type"] = channel.channel_type.value if channel else None
    data["channel_name"] = channel.name if channel else ""
    data["channel_members"] = channel.members if channel else []
    data["project_id"] = _extract_project_id(data) or (channel.project_id if channel else None)
    return data


def _build_message_event(message: Dict[str, Any]) -> Dict[str, Any]:
    content = message.get("content") if isinstance(message.get("content"), dict) else {}
    action = content.get("action") if isinstance(content, dict) else None

    summary = ""
    if action == "delegate_task":
        summary = content.get("task_description", "")
    elif action == "query":
        summary = content.get("query", "")
    elif action == "notification":
        summary = content.get("notification", "")

    return {
        "event_id": f"ev_msg_{message.get('message_id')}",
        "event_type": "action" if action else "message",
        "timestamp": message.get("timestamp"),
        "agent_id": message.get("sender_id"),
        "channel_id": message.get("channel_id"),
        "channel_type": message.get("channel_type"),
        "message_type": message.get("message_type"),
        "action": action,
        "summary": summary,
        "payload": message.get("content"),
    }


def _build_task_event(task: Dict[str, Any]) -> Dict[str, Any]:
    payload = task.get("payload") if isinstance(task.get("payload"), dict) else {}
    source = payload.get("source") if isinstance(payload.get("source"), dict) else {}
    source_agent_id = source.get("agent_id")
    return {
        "event_id": f"ev_task_{task.get('task_id')}_{task.get('status')}",
        "event_type": "task",
        "timestamp": task.get("resolved_at") or task.get("created_at"),
        "agent_id": source_agent_id,
        "channel_id": None,
        "channel_type": None,
        "message_type": None,
        "action": task.get("task_type"),
        "summary": task.get("title", ""),
        "payload": {
            "task_id": task.get("task_id"),
            "status": task.get("status"),
            "project_id": task.get("project_id"),
            "user_id": task.get("user_id"),
        },
    }


@agent_monitor_bp.route("/overview", methods=["GET"])
def overview():
    """Combined snapshot used by Alpha monitor UI."""
    user_id = _get_actor()
    project_id = request.args.get("project_id")
    limit_messages = request.args.get("limit_messages", 300, type=int)
    limit_tasks = request.args.get("limit_tasks", 200, type=int)
    limit_events = request.args.get("limit_events", 500, type=int)

    try:
        agents = [
            {
                "agent_id": a.agent_id,
                "name": a.name,
                "tool_names": a.tool_names,
                "child_agent_ids": a.child_agent_ids,
            }
            for a in agent_registry.list_agents()
        ]

        messages = [_message_to_dict(m) for m in message_bus.get_history(limit=limit_messages)]
        messages = _filter_messages_by_project(messages, project_id)

        visible_channel_ids = {m.get("channel_id") for m in messages if m.get("channel_id")}
        channels = []
        for c in channel_manager.list_channels():
            if project_id and c.project_id != project_id and c.channel_id not in visible_channel_ids:
                continue
            channels.append(c.to_dict())

        tasks: List[Dict[str, Any]] = []
        if agent_task_service:
            tasks = agent_task_service.list_all_tasks(
                user_id=user_id,
                project_id=project_id,
                status=None,
                limit=limit_tasks,
            )

        events = [_build_message_event(m) for m in messages]
        events.extend(_build_task_event(t) for t in tasks)
        events.sort(key=lambda e: _parse_ts(e.get("timestamp")), reverse=True)
        events = events[: max(1, min(2000, int(limit_events)))]

        return jsonify(
            {
                "success": True,
                "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "agents": agents,
                "channels": channels,
                "messages": messages,
                "tasks": tasks,
                "events": events,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@agent_monitor_bp.route("/channels/<channel_id>/messages", methods=["GET"])
def channel_messages(channel_id: str):
    """Messages for a single channel."""
    limit = request.args.get("limit", 200, type=int)
    project_id = request.args.get("project_id")

    try:
        data = [
            _message_to_dict(m)
            for m in message_bus.get_history(channel_id=channel_id, limit=limit)
        ]
        data = _filter_messages_by_project(data, project_id)
        return jsonify({"success": True, "messages": data})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
