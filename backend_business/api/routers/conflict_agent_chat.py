"""Conflict detection agent chat router."""

from __future__ import annotations

import json
from typing import Any, Optional

from fastapi import APIRouter, Depends, Query

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.http.sse import sse_response_raw
from backend_business.api.routers.schemas.agent_chat_schemas import (
    AgentChatSessionRequest,
    AgentChatSessionUpdateRequest,
)
from backend_business.services.db_service import db_service
from backend_business.services.agent.agents.conflict_detection_agent import (
    conflict_detection_agent_service,
)

router = APIRouter(prefix="/api/v2/conflict-agent-chat", tags=["conflict-agent-chat"])


from pydantic import BaseModel, ConfigDict, Field, field_validator


class ConflictAgentMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    execution_mode: str = Field(default="classic")

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
        normalized = value.strip().lower()
        if normalized not in ("classic", "graph"):
            return "classic"
        return normalized


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
        kwargs = {
            "user_id": current_user["user_id"],
            "project_id": payload.project_id,
        }
        if payload.prompt_payload_format is not None:
            kwargs["prompt_payload_format"] = payload.prompt_payload_format
        if payload.context_mode is not None:
            kwargs["context_mode"] = payload.context_mode
        return conflict_detection_agent_service.create_or_get_session(**kwargs)
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
        sessions = conflict_detection_agent_service.list_sessions(
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
        kwargs = {
            "user_id": current_user["user_id"],
            "project_id": payload.project_id,
            "title": payload.title,
        }
        if payload.prompt_payload_format is not None:
            kwargs["prompt_payload_format"] = payload.prompt_payload_format
        if payload.context_mode is not None:
            kwargs["context_mode"] = payload.context_mode
        return conflict_detection_agent_service.create_session(**kwargs)
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
        return conflict_detection_agent_service.update_session(
            session_id=session_id,
            user_id=current_user["user_id"],
            title=payload.title,
            prompt_payload_format=payload.prompt_payload_format,
            context_mode=payload.context_mode,
        )
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.delete("/sessions/{session_id}")
def delete_session(
    session_id: str,
    current_user: Optional[dict] = Depends(get_current_user),
):
    try:
        deleted = conflict_detection_agent_service.delete_session(
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
        messages = conflict_detection_agent_service.list_messages(
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
        return conflict_detection_agent_service.list_session_graph_chain(
            session_id=session_id,
            user_id=current_user["user_id"],
        )
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/sessions/{session_id}/messages/stream")
def stream_message(
    session_id: str,
    payload: ConflictAgentMessageRequest,
    current_user: Optional[dict] = Depends(get_current_user),
):
    _require_project_access(payload.project_id, current_user)

    def generate():
        try:
            for event in conflict_detection_agent_service.stream_conflict_agent_reply(
                session_id=session_id,
                user_id=current_user["user_id"],
                project_id=payload.project_id,
                user_message=payload.message,
                execution_mode=payload.execution_mode,
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
        graph = conflict_detection_agent_service.get_graph(graph_id)
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
        detail = conflict_detection_agent_service.get_graph_detail(graph_id)
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
