"""Messaging tools for inter-agent communication.

All three tools (delegate_task, query_agent, broadcast_notification) route
messages through the MessageBus. The request-response path is:

- Channel creation/lookup
- Message persistence & history
- Middleware pipeline (logging, rate limit, metrics)
- Recipient resolution via Router
- Synchronous request-response lifecycle
"""

import logging
import threading
import uuid
from typing import Any, Dict, List, Optional

from backend_business.services.agent.context import AgentContext
from backend_business.services.agent.messaging import ChannelType, message_bus, MessageType
from backend_business.services.agent.messaging.channel import channel_manager
from backend_business.services.agent.registry import agent_registry
from backend_business.services.agent.tools.base import ToolDefinition, tool_registry
from backend_business.services.agent.messaging.message import AgentMessage

logger = logging.getLogger(__name__)


# ======================================================================
# Tool schemas (OpenAI function-calling format)
# ======================================================================

_DELEGATE_TASK_SCHEMA = {
    "type": "function",
    "function": {
        "name": "delegate_task",
        "description": "Delegate a task to another child agent and wait for its result.",
        "parameters": {
            "type": "object",
            "properties": {
                "target_agent_id": {
                    "type": "string",
                    "description": "ID of the child agent to delegate to.",
                },
                "task_description": {
                    "type": "string",
                    "description": "Clear natural-language description of what should be done.",
                },
                "task_context": {
                    "type": "object",
                    "description": "Optional structured context for the delegated task.",
                },
            },
            "required": ["target_agent_id", "task_description"],
        },
    },
}

_QUERY_AGENT_SCHEMA = {
    "type": "function",
    "function": {
        "name": "query_agent",
        "description": "Query another child agent (read-only delegation).",
        "parameters": {
            "type": "object",
            "properties": {
                "target_agent_id": {
                    "type": "string",
                    "description": "ID of the child agent to query.",
                },
                "query": {
                    "type": "string",
                    "description": "Question or information request for the target agent.",
                },
                "query_context": {
                    "type": "object",
                    "description": "Optional structured context for the query.",
                },
            },
            "required": ["target_agent_id", "query"],
        },
    },
}

_BROADCAST_NOTIFICATION_SCHEMA = {
    "type": "function",
    "function": {
        "name": "broadcast_notification",
        "description": "Broadcast a notification to all agents in current project context.",
        "parameters": {
            "type": "object",
            "properties": {
                "notification": {
                    "type": "string",
                    "description": "Notification content.",
                },
                "notification_type": {
                    "type": "string",
                    "enum": ["info", "warning", "alert"],
                    "description": "Notification severity/type.",
                },
            },
            "required": ["notification"],
        },
    },
}


# ======================================================================
# Permission helpers
# ======================================================================

def _validate_child_agent_permission(sender_id: str, target_agent_id: str) -> Optional[str]:
    sender_def = agent_registry.get(sender_id)
    if not sender_def:
        return f"Unknown sender agent: {sender_id}"

    target_def = agent_registry.get(target_agent_id)
    if not target_def:
        return f"Unknown target agent: {target_agent_id}"

    if target_agent_id not in sender_def.child_agent_ids:
        return f"Agent {sender_id} is not allowed to delegate to {target_agent_id}"

    return None


def _read_only_tool_names(agent_id: str) -> List[str]:
    agent_def = agent_registry.get(agent_id)
    if not agent_def:
        return []
    return [name for name in agent_def.tool_names if not tool_registry.is_write(name)]


def _run_target_agent(
    target_agent_id: str,
    request_message: AgentMessage,
    parent_context: AgentContext,
    tool_names_override: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Execute target agent for a bus request (compatibility seam for tests)."""
    from backend_business.services.agent.runner import AgentRunner

    runner = AgentRunner()
    return runner.handle_bus_request(
        target_agent_id=target_agent_id,
        request_message=request_message,
        parent_context=parent_context,
        tool_names_override=tool_names_override,
    )


# ======================================================================
# Core: send REQUEST via bus → runner handles → RESPONSE comes back
# ======================================================================

def _send_request_via_bus(
    sender_id: str,
    target_agent_id: str,
    ctx: AgentContext,
    content: Dict[str, Any],
    tool_names_override: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Send a REQUEST through the message bus and wait for target execution.

    Flow:
    1. Create/get direct channel between sender and target
    2. Register a temporary bus handler for target agent execution
    3. Send REQUEST via ``send_request``
    4. Wait for handler completion (or use compatibility fallback)
    4. Return response payload
    """
    channel = channel_manager.get_or_create_direct_channel(
        sender_id, target_agent_id, project_id=ctx.project_id
    )

    # Enrich content with session/project info
    content.setdefault("user_id", ctx.user_id)
    content.setdefault("session_id", ctx.session_id)
    content.setdefault("project_id", ctx.project_id)

    dispatch_id = f"dispatch_{uuid.uuid4().hex[:12]}"
    done = threading.Event()
    state: Dict[str, Any] = {
        "handled": False,
        "result": None,
        "response_message_id": None,
    }

    def _auto_execute_request(msg: AgentMessage) -> None:
        # Only process this specific request dispatch.
        if msg.message_type != MessageType.REQUEST:
            return
        if msg.channel_id != channel.channel_id:
            return
        if msg.sender_id != sender_id:
            return
        if (msg.metadata or {}).get("dispatch_id") != dispatch_id:
            return

        state["handled"] = True
        try:
            result = _run_target_agent(
                target_agent_id=target_agent_id,
                request_message=msg,
                parent_context=ctx,
                tool_names_override=tool_names_override,
            )
            state["result"] = result
            response_message_id = result.get("response_message_id")
            if not response_message_id:
                response_message_id = message_bus.send_response(
                    sender_id=target_agent_id,
                    channel_id=msg.channel_id,
                    reply_to=msg.message_id,
                    content={
                        "status": "completed" if not result.get("errors") else "completed_with_errors",
                        "result": result,
                        "project_id": ctx.project_id,
                        "session_id": ctx.session_id,
                    },
                )
            state["response_message_id"] = response_message_id
        except Exception as e:
            logger.exception("Failed to auto-execute request %s for %s", msg.message_id, target_agent_id)
            state["response_message_id"] = message_bus.send_response(
                sender_id=target_agent_id,
                channel_id=msg.channel_id,
                reply_to=msg.message_id,
                content={
                    "status": "failed",
                    "error": str(e),
                    "project_id": ctx.project_id,
                    "session_id": ctx.session_id,
                },
            )
            state["result"] = {"error": str(e)}
        finally:
            done.set()

    message_bus.subscribe(target_agent_id, _auto_execute_request)
    try:
        request_message_id = message_bus.send_request(
            sender_id=sender_id,
            recipient_id=target_agent_id,
            content=content,
            channel_id=channel.channel_id,
            metadata={"dispatch_id": dispatch_id, "target_agent_id": target_agent_id},
        )
        request_message = message_bus.get_message(request_message_id)

        if request_message is None and not state["handled"]:
            # Compatibility fallback (e.g., unit tests mocking send_request):
            request_message = AgentMessage(
                message_id=request_message_id,
                channel_id=channel.channel_id,
                sender_id=sender_id,
                message_type=MessageType.REQUEST,
                content=content,
                metadata={"dispatch_id": dispatch_id, "target_agent_id": target_agent_id},
            )
            result = _run_target_agent(
                target_agent_id=target_agent_id,
                request_message=request_message,
                parent_context=ctx,
                tool_names_override=tool_names_override,
            )
            state["result"] = result
            if not state["response_message_id"]:
                state["response_message_id"] = result.get("response_message_id") or message_bus.send_response(
                    sender_id=target_agent_id,
                    channel_id=channel.channel_id,
                    reply_to=request_message.message_id,
                    content={
                        "status": "completed" if not result.get("errors") else "completed_with_errors",
                        "result": result,
                        "project_id": ctx.project_id,
                        "session_id": ctx.session_id,
                    },
                )
        else:
            completed = done.wait(timeout=180.0)
            if completed:
                pass
            elif not state["handled"]:
                return {
                    "request_message_id": request_message_id,
                    "response_message_id": None,
                    "channel_id": channel.channel_id,
                    "target_agent": target_agent_id,
                    "error": "request timeout",
                }
            else:
                return {
                    "request_message_id": request_message_id,
                    "response_message_id": None,
                    "channel_id": channel.channel_id,
                    "target_agent": target_agent_id,
                    "error": "target execution did not complete in time",
                }
        if state["result"] is None and not state["handled"]:
            return {
                "request_message_id": request_message_id,
                "response_message_id": None,
                "channel_id": channel.channel_id,
                "target_agent": target_agent_id,
                "error": "request timeout",
            }
    finally:
        message_bus.unsubscribe(target_agent_id, _auto_execute_request)

    return {
        "request_message_id": request_message_id,
        "response_message_id": state["response_message_id"],
        "channel_id": channel.channel_id,
        "target_agent": target_agent_id,
        "result": state["result"] or {},
    }


# ======================================================================
# Tool handlers
# ======================================================================

def _delegate_task(args: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    target_agent_id = args.get("target_agent_id")
    task_description = args.get("task_description")
    task_context = args.get("task_context", {})

    if not target_agent_id:
        return {"error": "target_agent_id is required"}
    if not task_description:
        return {"error": "task_description is required"}
    if not ctx.execution or not ctx.execution.agent_id:
        return {"error": "execution.agent_id is required in context"}

    sender_id = ctx.execution.agent_id
    perm_error = _validate_child_agent_permission(sender_id, target_agent_id)
    if perm_error:
        return {"error": perm_error}

    try:
        bus_result = _send_request_via_bus(
            sender_id=sender_id,
            target_agent_id=target_agent_id,
            ctx=ctx,
            content={
                "action": "delegate_task",
                "task_description": task_description,
                "task_context": task_context,
            },
        )
        return {
            "status": "delegated",
            **bus_result,
        }
    except Exception as e:
        # Send failure notification through the bus
        channel = channel_manager.get_or_create_direct_channel(
            sender_id, target_agent_id, project_id=ctx.project_id
        )
        message_bus.send_notify(
            sender_id=sender_id,
            channel_id=channel.channel_id,
            content={
                "status": "delegation_failed",
                "error": str(e),
                "target_agent": target_agent_id,
            },
        )
        return {
            "status": "delegation_failed",
            "channel_id": channel.channel_id,
            "target_agent": target_agent_id,
            "error": str(e),
        }


def _query_agent(args: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    target_agent_id = args.get("target_agent_id")
    query = args.get("query")
    query_context = args.get("query_context", {})

    if not target_agent_id:
        return {"error": "target_agent_id is required"}
    if not query:
        return {"error": "query is required"}
    if not ctx.execution or not ctx.execution.agent_id:
        return {"error": "execution.agent_id is required in context"}

    sender_id = ctx.execution.agent_id
    perm_error = _validate_child_agent_permission(sender_id, target_agent_id)
    if perm_error:
        return {"error": perm_error}

    # For queries, restrict target agent to read-only tools
    read_only_tools = _read_only_tool_names(target_agent_id)
    if not read_only_tools:
        channel = channel_manager.get_or_create_direct_channel(
            sender_id, target_agent_id, project_id=ctx.project_id
        )
        message_bus.send_notify(
            sender_id=target_agent_id,
            channel_id=channel.channel_id,
            content={
                "status": "failed",
                "error": f"Target agent {target_agent_id} has no readable tools",
                "read_only": True,
            },
        )
        return {
            "error": f"Target agent {target_agent_id} has no readable tools",
            "channel_id": channel.channel_id,
        }

    try:
        bus_result = _send_request_via_bus(
            sender_id=sender_id,
            target_agent_id=target_agent_id,
            ctx=ctx,
            content={
                "action": "query",
                "query": query,
                "query_context": query_context,
            },
            tool_names_override=read_only_tools,
        )
        return {
            "status": "query_completed",
            **bus_result,
        }
    except Exception as e:
        channel = channel_manager.get_or_create_direct_channel(
            sender_id, target_agent_id, project_id=ctx.project_id
        )
        message_bus.send_notify(
            sender_id=sender_id,
            channel_id=channel.channel_id,
            content={
                "status": "query_failed",
                "error": str(e),
                "target_agent": target_agent_id,
                "read_only": True,
            },
        )
        return {
            "status": "query_failed",
            "channel_id": channel.channel_id,
            "target_agent": target_agent_id,
            "error": str(e),
        }


def _broadcast_notification(args: Dict[str, Any], ctx: AgentContext) -> Dict[str, Any]:
    notification = args.get("notification")
    notification_type = args.get("notification_type", "info")

    if not notification:
        return {"error": "notification is required"}
    if not ctx.execution or not ctx.execution.agent_id:
        return {"error": "execution.agent_id is required in context"}

    sender_id = ctx.execution.agent_id
    project_id = ctx.project_id

    # Get or create a project-level broadcast channel
    channel = channel_manager.create_channel(
        channel_type=ChannelType.BROADCAST,
        created_by=sender_id,
        name=f"broadcast_{project_id}",
        project_id=project_id,
        members=[agent_def.agent_id for agent_def in agent_registry.list_agents()],
    )

    # Send through the bus (routed to all members via broadcast channel)
    message_id = message_bus.send_notify(
        sender_id=sender_id,
        channel_id=channel.channel_id,
        content={
            "notification": notification,
            "notification_type": notification_type,
            "project_id": project_id,
        },
    )

    return {
        "status": "broadcasted",
        "message_id": message_id,
        "channel_id": channel.channel_id,
        "notification_type": notification_type,
    }


# ======================================================================
# Register tools
# ======================================================================

tool_registry.register(
    ToolDefinition(
        name="delegate_task",
        openai_schema=_DELEGATE_TASK_SCHEMA,
        handler=_delegate_task,
        is_write=False,
    )
)

tool_registry.register(
    ToolDefinition(
        name="query_agent",
        openai_schema=_QUERY_AGENT_SCHEMA,
        handler=_query_agent,
        is_write=False,
    )
)

tool_registry.register(
    ToolDefinition(
        name="broadcast_notification",
        openai_schema=_BROADCAST_NOTIFICATION_SCHEMA,
        handler=_broadcast_notification,
        is_write=False,
    )
)
