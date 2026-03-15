"""
RequirementActor API 路由

提供基于 Actor 模型的需求生命周期管理 API
"""

import asyncio
import json
import logging
import os
import socket
from collections.abc import Generator
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query, Request, WebSocket, WebSocketDisconnect

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.http.sse import sse_response_raw
from backend_business.config import settings
from backend_business.services.actor.dev_trace import subscribe, unsubscribe

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/requirement-actor", tags=["requirement-actor"])
internals_router = APIRouter(prefix="/api/v2/_internals/actors", tags=["requirement-actor-internals"])

# 延迟初始化以避免循环导入
_actor_manager = None
_event_store = None
_projection = None


def _get_instance_id() -> str:
    configured = settings.ACTOR_INSTANCE_ID
    if configured:
        return configured
    host = os.environ.get("HOSTNAME") or socket.gethostname() or "unknown-host"
    return f"{host}:{os.getpid()}"


def _get_actor_manager():
    """获取 ActorManager 单例"""
    global _actor_manager
    if _actor_manager is None:
        from backend_business.services.event_store.event_store import EventStore
        from backend_business.services.actor.actor_manager import ActorManager
        from backend_business.services.agent.coordinator.distributed_coordinator import (
            DistributedActorCoordinator,
        )

        event_store = EventStore(settings.POSTGRES_DSN)
        coordinator = None
        if settings.REDIS_URL:
            coordinator = DistributedActorCoordinator(
                redis_url=settings.REDIS_URL,
                instance_id=_get_instance_id(),
            )
        _actor_manager = ActorManager(event_store, coordinator=coordinator)
    return _actor_manager


def _get_actor(request: Request, current_user: Optional[dict] = None) -> str:
    """获取操作者标识 - 遵循现有模式"""
    if current_user:
        return current_user.get("user_id", "system")

    actor = request.headers.get("X-Actor", "")
    if actor:
        return actor

    return "system"


def _sse_event(event: str, data: Any) -> str:
    """生成 SSE 事件格式"""
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _get_requirement_projection():
    """获取读模型投影服务单例。"""
    global _projection
    if _projection is None:
        from backend_business.services.read_projections.requirement_projection import (
            RequirementProjection,
        )

        _projection = RequirementProjection(settings.POSTGRES_DSN)
    return _projection


def _raise_actor_error(exc: Exception, action: str):
    """统一 Actor 链路错误到 HTTP 语义。"""
    from backend_business.services.actor.actors.requirement_actor import (
        DomainException,
        InfrastructureException,
    )

    if isinstance(exc, DomainException):
        raise ErrorResponse(str(exc), 409)
    if isinstance(exc, InfrastructureException):
        raise ErrorResponse(str(exc), 503)
    if isinstance(exc, ValueError):
        raise ErrorResponse(str(exc), 400)

    logger.error(f"{action} failed: {exc}", exc_info=True)
    raise ErrorResponse(str(exc), 500)


# ========================
# 命令端点
# ========================

@router.post("/command")
async def submit_command(
    requirement_id: str,
    command: dict,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """
    提交通用命令到 Actor

    命令格式:
    {
        "type": "UpdateRequirementContent" | "ChangeStatus" | "AddQualityMarker" | "CreateRequirement",
        "source": "agent_id | user_id",
        "metadata": {"graph_id": "...", "call_node_id": "..."},
        ... 其他字段
    }
    """
    actor = _get_actor(request, current_user)
    command["source"] = actor

    manager = _get_actor_manager()

    try:
        result = await manager.send_command(requirement_id, command)
        return result
    except Exception as e:
        _raise_actor_error(e, "Command processing")


@router.post("/command/create")
async def create_requirement(
    requirement_id: str,
    content: dict,
    request: Request,
    status: str = "Draft",
    priority: str = "medium",
    metadata: Optional[dict] = None,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """创建需求"""
    command = {
        "type": "CreateRequirement",
        "content": content,
        "status": status,
        "priority": priority,
        "metadata": metadata or {}
    }
    command["source"] = _get_actor(request, current_user)

    manager = _get_actor_manager()

    try:
        result = await manager.send_command(requirement_id, command)
        return result
    except Exception as e:
        _raise_actor_error(e, "Create requirement")


@router.post("/command/update-content")
async def update_content(
    requirement_id: str,
    payload: dict,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """更新需求内容（兼容嵌套/非嵌套请求体）"""
    if "updates" in payload:
        updates = payload.get("updates")
        if not isinstance(updates, dict):
            raise ErrorResponse("updates 必须是对象", 400)

        metadata = payload.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ErrorResponse("metadata 必须是对象", 400)
    else:
        # 兼容历史调用：直接将请求体作为 updates
        updates = payload
        metadata = {}

    command = {
        "type": "UpdateRequirementContent",
        "updates": updates,
        "metadata": metadata,
    }
    command["source"] = _get_actor(request, current_user)

    manager = _get_actor_manager()

    try:
        result = await manager.send_command(requirement_id, command)
        return result
    except Exception as e:
        _raise_actor_error(e, "Update content")


@router.post("/command/change-status")
async def change_status(
    requirement_id: str,
    new_status: str,
    request: Request,
    metadata: Optional[dict] = None,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """变更需求状态"""
    command = {
        "type": "ChangeStatus",
        "new_status": new_status,
        "metadata": metadata or {}
    }
    command["source"] = _get_actor(request, current_user)

    manager = _get_actor_manager()

    try:
        result = await manager.send_command(requirement_id, command)
        return result
    except Exception as e:
        _raise_actor_error(e, "Change status")


@router.post("/command/add-quality-marker")
async def add_quality_marker(
    requirement_id: str,
    marker_type: str,
    marker_value: Any,
    request: Request,
    metadata: Optional[dict] = None,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """添加质量标记"""
    command = {
        "type": "AddQualityMarker",
        "marker_type": marker_type,
        "marker_value": marker_value,
        "metadata": metadata or {}
    }
    command["source"] = _get_actor(request, current_user)

    manager = _get_actor_manager()

    try:
        result = await manager.send_command(requirement_id, command)
        return result
    except Exception as e:
        _raise_actor_error(e, "Add quality marker")


@router.post("/command/query-state")
async def query_state(
    requirement_id: str,
    request: Request,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """Actor Ask - 直接查询 Actor 内存状态（内部特权）"""
    command = {
        "type": "QueryState",
        "source": _get_actor(request, current_user)
    }

    manager = _get_actor_manager()

    try:
        result = await manager.send_command(requirement_id, command)
        return result
    except Exception as e:
        _raise_actor_error(e, "Query state")


# ========================
# 查询端点
# ========================

@router.get("/query")
async def query_requirement(
    requirement_id: str,
    min_version: Optional[int] = Query(default=None, ge=0),
    timeout: int = Query(default=5, ge=1, le=60),
):
    """
    查询需求，带版本栅栏

    如果读模型版本低于 min_version，会阻塞等待直到追上或超时
    超时返回 503 Service Unavailable
    """
    projection = _get_requirement_projection()

    try:
        if min_version is not None:
            is_caught_up = await projection.wait_for_version(
                requirement_id=requirement_id,
                min_version=min_version,
                timeout=float(timeout),
            )
            if not is_caught_up:
                raise ErrorResponse("查询超时 - 读模型尚未追上指定版本", 503)

        requirement = projection.get_requirement(requirement_id)
        if not requirement:
            raise ErrorResponse("需求不存在", 404)

        return {
            "status": "success",
            "source": "read_model",
            "requirement": requirement,
        }
    except ValueError as e:
        raise ErrorResponse(str(e), 400)
    except ErrorResponse:
        raise
    except Exception as e:
        logger.error(f"Query requirement failed: {e}", exc_info=True)
        raise ErrorResponse(str(e), 500)


@router.get("/events/{requirement_id}")
async def get_events(
    requirement_id: str,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
):
    """获取需求的事件历史"""
    from backend_business.services.event_store.event_store import EventStore

    event_store = EventStore(settings.POSTGRES_DSN)

    try:
        events = event_store.get_events_by_requirement(
            requirement_id, limit=limit, offset=offset
        )
        return {
            "requirement_id": requirement_id,
            "events": events,
            "total": len(events)
        }
    except Exception as e:
        logger.error(f"Get events failed: {e}", exc_info=True)
        raise ErrorResponse(str(e), 500)


@router.get("/snapshot/{requirement_id}")
async def get_snapshot(
    requirement_id: str,
):
    """获取需求的最新快照"""
    from backend_business.services.event_store.event_store import EventStore

    event_store = EventStore(settings.POSTGRES_DSN)

    try:
        snapshot = event_store.get_latest_snapshot(requirement_id)
        if not snapshot:
            raise ErrorResponse("快照不存在", 404)
        return snapshot
    except ErrorResponse:
        raise
    except Exception as e:
        logger.error(f"Get snapshot failed: {e}", exc_info=True)
        raise ErrorResponse(str(e), 500)


# ========================
# 监控端点
# ========================

@router.get("/health/{requirement_id}")
async def get_actor_health(requirement_id: str):
    """获取单个 Actor 健康状态"""
    manager = _get_actor_manager()
    stats = manager.get_stats()

    is_active = requirement_id in stats.get("actor_ids", [])
    mailbox_size = stats.get("mailbox_sizes", {}).get(requirement_id, 0)

    return {
        "requirement_id": requirement_id,
        "active": is_active,
        "mailbox_size": mailbox_size,
        "status": "active" if is_active else "inactive"
    }


@router.get("/stats")
async def get_actor_stats():
    """获取全局 Actor 统计信息"""
    manager = _get_actor_manager()
    return manager.get_stats()


@internals_router.get("/stats")
async def get_actor_internals_stats():
    """特权巡检：透出 ActorManager 内部状态。"""
    manager = _get_actor_manager()
    return manager.get_stats()


@internals_router.websocket("/ws")
async def actor_dev_trace_ws(websocket: WebSocket):
    """
    调试 WebSocket：广播 actor_dev_trace 生命周期事件。
    """
    await websocket.accept()
    queue = subscribe()
    await websocket.send_json(
        {
            "event": "actor_dev_trace",
            "data": {
                "stage": "connected",
                "message": "actor dev trace connected",
            },
        }
    )

    try:
        while True:
            message = await queue.get()
            await websocket.send_json({"event": "actor_dev_trace", "data": message})
    except WebSocketDisconnect:
        pass
    finally:
        unsubscribe(queue)


@router.get("/events/stream/{requirement_id}")
async def stream_events(requirement_id: str):
    """
    SSE 事件流 - 实时更新

    遵循现有 SSE 模式：sse_response_raw
    """
    def generate() -> Generator[str, None, None]:
        """生成 SSE 事件流"""
        # 发送连接确认
        yield _sse_event("connected", {"requirement_id": requirement_id})

        # 心跳
        import time
        start_time = time.time()

        while time.time() - start_time < 300:  # 5 分钟超时
            yield _sse_event("heartbeat", {
                "timestamp": time.time(),
                "requirement_id": requirement_id
            })
            time.sleep(30)  # 每 30 秒发送心跳

        yield _sse_event("timeout", {"message": "连接超时"})

    return sse_response_raw(generate())


# ========================
# 管理端点
# ========================

@router.post("/force-activate/{requirement_id}")
async def force_activate(requirement_id: str):
    """强制激活 Actor"""
    manager = _get_actor_manager()

    try:
        await manager.activate_actor(requirement_id)
        return {
            "status": "activated",
            "requirement_id": requirement_id
        }
    except Exception as e:
        logger.error(f"Force activate failed: {e}", exc_info=True)
        raise ErrorResponse(str(e), 500)


@router.post("/force-passivate/{requirement_id}")
async def force_passivate(requirement_id: str):
    """强制休眠 Actor"""
    manager = _get_actor_manager()

    try:
        await manager.force_passivate(requirement_id)
        return {
            "status": "passivated",
            "requirement_id": requirement_id
        }
    except Exception as e:
        logger.error(f"Force passivate failed: {e}", exc_info=True)
        raise ErrorResponse(str(e), 500)


@router.post("/cleanup")
async def cleanup_idle_actors(
    idle_timeout: int = Query(default=600, ge=60, le=3600)
):
    """清理空闲的 Actor"""
    manager = _get_actor_manager()

    try:
        await manager.passivate_idle_actors(idle_timeout)
        stats = manager.get_stats()
        return {
            "status": "cleanup_complete",
            "idle_timeout": idle_timeout,
            "stats": stats
        }
    except Exception as e:
        logger.error(f"Cleanup failed: {e}", exc_info=True)
        raise ErrorResponse(str(e), 500)


@router.get("/transitions")
async def get_transitions():
    """获取所有允许的状态转换"""
    from backend_business.services.actor.actors.state_machine import (
        RequirementStatus, RequirementStateMachine
    )

    state_machine = RequirementStateMachine()
    transitions = {}

    for status in RequirementStatus:
        transitions[status.value] = [
            {
                "to": to_status.value,
                "condition": state_machine.get_transition_condition(status, to_status)
            }
            for to_status in state_machine.get_allowed_transitions(status)
        ]

    return {
        "status_enum": [s.value for s in RequirementStatus],
        "transitions": transitions
    }


# ========================
# 回放端点
# ========================

@router.get("/versions/{requirement_id}")
async def get_version_history(
    requirement_id: str,
    limit: int = Query(default=50, ge=1, le=1000),
):
    """
    获取需求的版本历史列表

    返回每个事件的基本信息（版本号、事件类型、时间戳、来源）
    """
    from backend_business.services.event_store.event_store import EventStore

    event_store = EventStore(settings.POSTGRES_DSN)

    try:
        events = event_store.get_events_by_requirement(
            requirement_id, limit=limit, offset=0
        )

        versions = [
            {
                "version": e["event_sequence"],
                "event_type": e["event_type"],
                "occurred_at": e["occurred_at"].isoformat() if e.get("occurred_at") else None,
                "source": e.get("source", "system"),
                "event_id": e["event_id"]
            }
            for e in events
        ]

        return {
            "requirement_id": requirement_id,
            "versions": versions,
            "total": len(versions)
        }
    except Exception as e:
        logger.error(f"Get version history failed: {e}", exc_info=True)
        raise ErrorResponse(str(e), 500)


@router.get("/replay/{requirement_id}/{version}")
async def replay_to_version(
    requirement_id: str,
    version: int,
    use_snapshot: bool = Query(default=True),
):
    """
    重放事件到指定版本

    Args:
        version: 目标版本号
        use_snapshot: 是否使用快照优化

    Returns:
        重建的需求状态
    """
    from backend_business.services.event_store.event_store import EventStore
    from backend_business.services.actor.actors.state_machine import RequirementStatus

    event_store = EventStore(settings.POSTGRES_DSN)

    try:
        # 获取所有事件
        all_events = event_store.get_events_by_requirement(
            requirement_id, limit=10000, offset=0
        )

        if not all_events:
            raise ErrorResponse("需求不存在或无事件历史", 404)

        max_version = all_events[-1]["event_sequence"]
        if version < 0 or version > max_version:
            raise ErrorResponse(f"版本号超出范围 (0-{max_version})", 400)

        # 过滤到指定版本的事件
        events_to_replay = [e for e in all_events if e["event_sequence"] <= version]

        # 初始状态
        requirement_state = {
            "requirement_id": requirement_id,
            "title": "",
            "description": "",
            "status": "Draft",
            "priority": "medium",
            "quality_markers": {},
            "created_at": None,
            "updated_at": None,
            "version": version
        }

        # 应用每个事件
        for event in events_to_replay:
            event_type = event["event_type"]
            event_data = event.get("event_data", {})

            if event_type == "RequirementCreated":
                requirement_state.update({
                    "title": event_data.get("title", ""),
                    "description": event_data.get("description", ""),
                    "status": event_data.get("status", "Draft"),
                    "priority": event_data.get("priority", "medium"),
                    "created_at": event.get("occurred_at"),
                })

            elif event_type == "RequirementContentUpdated":
                updates = event_data.get("updates", {})
                requirement_state.update(updates)

            elif event_type == "RequirementStatusChanged":
                requirement_state["status"] = event_data.get("new_status", requirement_state["status"])

            elif event_type == "RequirementQualityMarkerAdded":
                markers = requirement_state.get("quality_markers", {})
                markers[event_data.get("marker_type", "")] = event_data.get("marker_value", "")
                requirement_state["quality_markers"] = markers

            elif event_type == "RequirementPriorityChanged":
                requirement_state["priority"] = event_data.get("new_priority", requirement_state["priority"])

            elif event_type == "RequirementEvidenceLinkAdded":
                # Handle evidence links if needed
                pass

            requirement_state["updated_at"] = event.get("occurred_at")

        # 格式化时间
        if requirement_state.get("created_at"):
            requirement_state["created_at"] = requirement_state["created_at"].isoformat()
        if requirement_state.get("updated_at"):
            requirement_state["updated_at"] = requirement_state["updated_at"].isoformat()

        return {
            "requirement_id": requirement_id,
            "version": version,
            "max_version": max_version,
            "state": requirement_state,
            "events_count": len(events_to_replay)
        }
    except ErrorResponse:
        raise
    except Exception as e:
        logger.error(f"Replay to version failed: {e}", exc_info=True)
        raise ErrorResponse(str(e), 500)
