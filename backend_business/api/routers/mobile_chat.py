"""
移动端对话路由（FastAPI）
对应历史蓝图: mobile_chat_bp (url_prefix="/api/v2/mobile")
"""

from typing import Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field, field_validator

from backend_business.api.http.errors import ErrorResponse
from backend_business.api.http.sse import sse_response_raw
from backend_business.services.mobile_chat_service import mobile_chat_service

router = APIRouter(prefix="/api/v2/mobile", tags=["mobile-chat"])


class CreateMessageRequest(BaseModel):
    session_id: str = Field(min_length=1)
    sender: str = Field(min_length=1)
    content: str = Field(min_length=1)
    user_id: str | None = None
    metadata: Any = None

    @field_validator("session_id", "sender", "content")
    @classmethod
    def _validate_required_text(cls, value: str) -> str:
        text = value.strip()
        if not text:
            raise ValueError("字段不能为空")
        return text

    @field_validator("user_id")
    @classmethod
    def _normalize_user_id(cls, value: str | None) -> str | None:
        if value is None:
            return None
        text = value.strip()
        return text or None


def _require_mobile_service():
    if not mobile_chat_service:
        raise ErrorResponse("移动端聊天服务未初始化", 500)
    return mobile_chat_service


def _resolve_user_id(
    request: Request,
    payload_user_id: str | None = None,
    query_user_id: str | None = None,
) -> str:
    if payload_user_id:
        payload_user_id = payload_user_id.strip()
        if payload_user_id:
            return payload_user_id

    if query_user_id:
        query_user_id = query_user_id.strip()
        if query_user_id:
            return query_user_id

    actor = (request.headers.get("X-Actor") or "").strip()
    if actor:
        return actor

    return "anonymous"


@router.get("/sessions")
def list_sessions(
    request: Request,
    user_id: str | None = Query(default=None),
    limit: int = Query(default=200),
):
    service = _require_mobile_service()
    resolved_user_id = _resolve_user_id(request=request, query_user_id=user_id)

    try:
        sessions = service.list_sessions(user_id=resolved_user_id, limit=limit)
        return {"success": True, "sessions": sessions}
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/messages")
def list_messages(
    request: Request,
    session_id: str = Query(min_length=1),
    user_id: str | None = Query(default=None),
    limit: int = Query(default=100),
    since: str | None = Query(default=None),
):
    service = _require_mobile_service()
    resolved_user_id = _resolve_user_id(request=request, query_user_id=user_id)
    normalized_session_id = session_id.strip()

    try:
        messages = service.list_messages(
            user_id=resolved_user_id,
            session_id=normalized_session_id,
            limit=limit,
            since=since,
        )
        return {"success": True, "messages": messages}
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.post("/messages")
def create_message(request: Request, payload: CreateMessageRequest):
    service = _require_mobile_service()
    resolved_user_id = _resolve_user_id(
        request=request,
        payload_user_id=payload.user_id,
    )

    try:
        message = service.create_message(
            user_id=resolved_user_id,
            session_id=payload.session_id,
            sender=payload.sender,
            content=payload.content,
            metadata=payload.metadata,
        )
        return {"success": True, "data": message}
    except ValueError as exc:
        raise ErrorResponse(str(exc), 400)
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/messages/pending")
def get_pending_messages(
    request: Request,
    session_id: str = Query(min_length=1),
    user_id: str | None = Query(default=None),
    since: str | None = Query(default=None),
    limit: int = Query(default=100),
):
    service = _require_mobile_service()
    resolved_user_id = _resolve_user_id(request=request, query_user_id=user_id)
    normalized_session_id = session_id.strip()

    try:
        messages = service.list_messages(
            user_id=resolved_user_id,
            session_id=normalized_session_id,
            limit=limit,
            since=since,
        )
        return {"success": True, "messages": messages}
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/stream")
def sse_stream(
    request: Request,
    session_id: str = Query(min_length=1),
    user_id: str | None = Query(default=None),
):
    service = _require_mobile_service()
    resolved_user_id = _resolve_user_id(request=request, query_user_id=user_id)
    normalized_session_id = session_id.strip()

    q = service.subscribe(user_id=resolved_user_id, session_id=normalized_session_id)

    def generate():
        yield from service.event_stream(q, resolved_user_id, normalized_session_id)

    return sse_response_raw(generate())
