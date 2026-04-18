"""Session controller agent chat router."""

from __future__ import annotations

import json
import logging
import threading
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.http.sse import sse_response_raw
from backend_business.api.routers.schemas.agent_chat_schemas import (
    AgentChatSessionRequest,
    AgentChatSessionUpdateRequest,
)
from backend_business.config import settings
from backend_business.services.db_service import db_service
from backend_business.services.requirements_manage_service import (
    RequirementsManageService,
)
from backend_business.services.agent.agents.session_controller import (
    session_controller_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v2/session-controller", tags=["session-controller"])


def _default_execution_mode_value() -> str:
    return "graph"


def _session_controller_capabilities() -> dict[str, Any]:
    return {
        "graph_execution_enabled": True,
        "default_execution_mode": "graph",
        "allowed_execution_modes": ["graph"],
    }


def _normalize_execution_mode_value(value: str) -> str:
    text = value.strip().lower()
    if text != "graph":
        raise ValueError("execution_mode 仅支持 graph")
    return text


class SessionControllerMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    execution_mode: str = Field(default_factory=_default_execution_mode_value)
    use_thinking_mode: bool = True
    delegated_max_tool_call_rounds: int = Field(default=15, ge=1, le=50)

    @field_validator("project_id", "message")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("字段不能为空")
        return text

    @field_validator("execution_mode")
    @classmethod
    def normalize_execution_mode(cls, value: str) -> str:
        return _normalize_execution_mode_value(value)


def _require_project_access(project_id: str, current_user: dict) -> None:
    if db_service is None:
        return
    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)
    if not user:
        raise ErrorResponse("用户不存在", 404)
    if not db_service.can_access_project(project_id, user_id, user):
        raise ErrorResponse("Permission denied", 403)


def _sse_event(event: str, data: Any) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.post("/sessions")
def create_or_get_session(
    payload: AgentChatSessionRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if payload.project_id:
        _require_project_access(payload.project_id, current_user)
    try:
        return session_controller_service.create_or_get_session(
            user_id=current_user["user_id"],
            project_id=payload.project_id,
        )
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/sessions")
def list_sessions(
    project_id: Optional[str] = Query(default=None),
    limit: int = Query(default=100, ge=1, le=200),
    current_user: Optional[dict] = Depends(get_current_user),
):
    if project_id:
        _require_project_access(project_id, current_user)
    try:
        sessions = session_controller_service.list_sessions(
            user_id=current_user["user_id"],
            project_id=project_id,
            limit=limit,
        )
        return {"sessions": sessions}
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/sessions/new")
def create_session(
    payload: AgentChatSessionRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if payload.project_id:
        _require_project_access(payload.project_id, current_user)
    try:
        return session_controller_service.create_session(
            user_id=current_user["user_id"],
            project_id=payload.project_id,
            title=payload.title,
        )
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.patch("/sessions/{session_id}")
def update_session(
    session_id: str,
    payload: AgentChatSessionUpdateRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    if payload.title is None and payload.prompt_payload_format is None and payload.context_mode is None:
        raise ErrorResponse("至少提供一个可更新字段", 400)
    try:
        return session_controller_service.update_session(
            session_id=session_id,
            user_id=current_user["user_id"],
            title=payload.title,
        )
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    try:
        deleted = session_controller_service.delete_session(
            session_id=session_id,
            user_id=current_user["user_id"],
        )
        if not deleted:
            raise ErrorResponse("会话不存在或已删除", 404)
        return {"ok": True}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/sessions/{session_id}/messages")
def list_messages(
    session_id: str,
    limit: int = Query(default=100, ge=1, le=200),
    current_user: Optional[dict] = Depends(get_current_user),
):
    try:
        messages = session_controller_service.list_messages(
            session_id=session_id,
            user_id=current_user["user_id"],
            limit=limit,
        )
        return {"messages": messages}
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/sessions/{session_id}/graph-chain")
def get_session_graph_chain(
    session_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    try:
        return session_controller_service.list_session_graph_chain(
            session_id=session_id,
            user_id=current_user["user_id"],
        )
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/capabilities")
def get_capabilities(
    current_user: Optional[dict] = Depends(get_current_user),
):
    return _session_controller_capabilities()


@router.post("/sessions/{session_id}/messages/stream")
def stream_message(
    session_id: str,
    payload: SessionControllerMessageRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    _require_project_access(payload.project_id, current_user)

    def generate():
        try:
            for event in session_controller_service.stream_session_controller_reply(
                session_id=session_id,
                user_id=current_user["user_id"],
                project_id=payload.project_id,
                user_message=payload.message,
                execution_mode=payload.execution_mode,
                use_thinking_mode=payload.use_thinking_mode,
                delegated_max_tool_call_rounds=payload.delegated_max_tool_call_rounds,
            ):
                yield _sse_event(event["event"], event.get("data", {}))
        except Exception as exc:
            yield _sse_event("error", {"error": str(exc)})

    return sse_response_raw(generate())


@router.get("/graphs/{graph_id}")
def get_graph(
    graph_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    try:
        graph = session_controller_service.get_graph(graph_id)
        if not graph:
            raise ErrorResponse("图不存在或已删除", 404)
        project_id = graph.get("project_id")
        if project_id:
            _require_project_access(project_id, current_user)
        return graph
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/graphs/{graph_id}/detail")
def get_graph_detail(
    graph_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    try:
        detail = session_controller_service.get_graph_detail(graph_id)
        graph = detail.get("graph")
        if not graph:
            raise ErrorResponse("图不存在或已删除", 404)
        project_id = graph.get("project_id")
        if project_id:
            _require_project_access(project_id, current_user)
        return detail
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


# ---- Mobile-friendly endpoints ----


class MobileMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    execution_mode: str = Field(default_factory=_default_execution_mode_value)
    use_thinking_mode: bool = True
    delegated_max_tool_call_rounds: int = Field(default=15, ge=1, le=50)

    @field_validator("project_id", "message")
    @classmethod
    def normalize_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("字段不能为空")
        return text

    @field_validator("execution_mode")
    @classmethod
    def normalize_mobile_execution_mode(cls, value: str) -> str:
        return _normalize_execution_mode_value(value)


def _run_agent_in_background(
    *,
    session_id: str,
    user_id: str,
    project_id: str,
    user_message: str,
    execution_mode: str,
    use_thinking_mode: bool,
    delegated_max_tool_call_rounds: int,
) -> None:
    """Fire-and-forget agent processing.  The reply is automatically
    persisted to ``ai_chat_messages`` by the service layer."""
    try:
        stream = session_controller_service.stream_session_controller_reply(
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            user_message=user_message,
            execution_mode=execution_mode,
            use_thinking_mode=use_thinking_mode,
            delegated_max_tool_call_rounds=delegated_max_tool_call_rounds,
            skip_user_message_creation=True,
        )
        # Drain the generator so every side-effect (message storage, graph
        # creation, etc.) is executed.
        for _event in stream:
            pass
    except Exception:
        logger.exception(
            "Background agent processing failed session=%s user=%s",
            session_id,
            user_id,
        )


@router.post("/sessions/{session_id}/messages")
def send_message_async(
    session_id: str,
    payload: MobileMessageRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    """Non-streaming message endpoint for mobile clients.

    Stores the user message immediately, kicks off agent processing in a
    background thread, and returns ``{ user_message, status }`` right away.
    The mobile client should poll ``GET /sessions/{id}/messages`` to pick up
    the agent's reply once it is ready.
    """
    _require_project_access(payload.project_id, current_user)

    if not session_controller_service.chat_storage:
        raise ErrorResponse("AI chat storage not initialized", 500)

    # Persist user message synchronously so the caller can display it.
    user_record = session_controller_service.chat_storage.create_message(
        session_id=session_id,
        user_id=current_user["user_id"],
        role="user",
        content=payload.message,
        metadata={},
        is_read=True,
    )
    session_controller_service.chat_storage.update_session(session_id=session_id)

    # Kick off agent in background thread.
    thread = threading.Thread(
        target=_run_agent_in_background,
        kwargs={
            "session_id": session_id,
            "user_id": current_user["user_id"],
            "project_id": payload.project_id,
            "user_message": payload.message,
            "execution_mode": payload.execution_mode,
            "use_thinking_mode": payload.use_thinking_mode,
            "delegated_max_tool_call_rounds": payload.delegated_max_tool_call_rounds,
        },
        daemon=True,
    )
    thread.start()

    return {"user_message": user_record, "status": "processing"}


@router.get("/projects")
def list_projects_for_mobile(
    current_user: Optional[dict] = Depends(get_current_user),
):
    """Lightweight project list for mobile companion app."""
    manage_service = RequirementsManageService(dsn=settings.POSTGRES_DSN)

    if db_service is None:
        return {"projects": manage_service.list_projects()}

    user_id = current_user["user_id"]
    user = db_service.get_user_by_id(user_id)
    if not user:
        raise ErrorResponse("用户不存在", 404)

    projects = manage_service.list_projects()
    if user.get("role") == "super_admin":
        return {"projects": projects}

    accessible = set(db_service.get_accessible_projects(user_id, user=user))
    return {"projects": [p for p in projects if p.get("project_id") in accessible]}
