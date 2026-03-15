"""Sidebar routing layer.

Sidebar only maintains static tool/container routing and request/response
delivery over the existing MessageBus. It does not do capability discovery,
health checks, or load balancing.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from backend_business.services.agent.messaging.bus import MessageBus

logger = logging.getLogger(__name__)


@dataclass
class RouteRequest:
    """A single routed tool invocation."""

    tool_name: str
    payload: Dict[str, Any]
    sender_id: str = "sidebar"
    channel_id: Optional[str] = None
    timeout: float = 30.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RouteResponse:
    """The routed result returned from the target container."""

    success: bool
    data: Any = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class Sidebar:
    """Static tool-to-container router built on top of MessageBus."""

    def __init__(self, message_bus: MessageBus):
        self.message_bus = message_bus
        self._tool_routes: Dict[str, str] = {}

    def register_tool(self, tool_name: str, container_id: str) -> None:
        self._tool_routes[tool_name] = container_id

    def unregister_tool(self, tool_name: str) -> None:
        self._tool_routes.pop(tool_name, None)

    def resolve_tool(self, tool_name: str) -> Optional[str]:
        return self._tool_routes.get(tool_name)

    async def send(self, request: RouteRequest) -> RouteResponse:
        container_id = self.resolve_tool(request.tool_name)
        if not container_id:
            return RouteResponse(
                success=False,
                error=f"Unmapped tool: {request.tool_name}",
                metadata={"tool_name": request.tool_name},
            )

        response = self.message_bus.request_and_wait(
            sender_id=request.sender_id,
            recipient_id=container_id,
            content=request.payload,
            channel_id=request.channel_id,
            metadata=request.metadata,
            timeout=request.timeout,
        )
        if response is None:
            logger.warning("Sidebar route timed out: tool=%s container=%s", request.tool_name, container_id)
            return RouteResponse(
                success=False,
                error="request timeout",
                metadata={"tool_name": request.tool_name, "container_id": container_id},
            )

        return RouteResponse(
            success=True,
            data=response.content,
            metadata={
                "tool_name": request.tool_name,
                "container_id": container_id,
                "message_id": response.message_id,
                "reply_to": response.reply_to,
            },
        )

    def get_stats(self) -> Dict[str, Any]:
        return {
            "routes": dict(self._tool_routes),
            "route_count": len(self._tool_routes),
        }

    def reset(self) -> None:
        self._tool_routes.clear()
