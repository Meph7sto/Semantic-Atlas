"""
推送通知路由
"""

from collections.abc import Generator
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.sse import sse_response_raw
from backend_business.services.requirement_change_approval_service import (
    RequirementChangeApprovalService,
    requirement_change_approval_service,
)
from backend_business.services.push_service import PushService, push_service

router = APIRouter(prefix="/api/v2/push", tags=["push"])


def _error_response(message: str, status_code: int) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": message},
    )


def _parse_int(value: str | None, default: int) -> int:
    try:
        return int(value) if value is not None else default
    except (TypeError, ValueError):
        return default


def _require_push_service() -> PushService | None:
    return push_service


def _require_approval_service() -> RequirementChangeApprovalService | None:
    return requirement_change_approval_service


@router.get("/messages")
def list_messages(
    message_type: str | None = Query(default=None),
    pushed: str | None = Query(default=None),
    page: str | None = Query(default="1"),
    per_page: str | None = Query(default="20"),
):
    service = _require_push_service()
    if not service:
        return _error_response("推送服务未初始化", 500)

    pushed_bool = None
    if pushed is not None:
        pushed_bool = pushed.lower() in ("true", "1", "yes")

    try:
        result = service.list_messages(
            message_type=message_type,
            pushed=pushed_bool,
            page=_parse_int(page, 1),
            per_page=_parse_int(per_page, 20),
        )
        return {"success": True, **result}
    except Exception as exc:
        return _error_response(str(exc), 500)


@router.post("/messages")
async def create_message(request: Request):
    service = _require_push_service()
    if not service:
        return _error_response("推送服务未初始化", 500)

    payload: dict[str, Any] = {}
    try:
        incoming = await request.json()
        if isinstance(incoming, dict):
            payload = incoming
    except Exception:
        payload = {}

    message_type = str(payload.get("message_type", "")).strip()
    title = str(payload.get("title", "")).strip()

    if not message_type:
        return _error_response("缺少 message_type", 400)
    if not title:
        return _error_response("缺少 title", 400)

    try:
        message = service.create_message(
            message_type=message_type,
            title=title,
            content=payload.get("content"),
            source=payload.get("source"),
            priority=payload.get("priority", "medium"),
            ai_suggestion=payload.get("ai_suggestion"),
            metadata=payload.get("metadata"),
        )
        return {"success": True, "data": message}
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except Exception as exc:
        return _error_response(str(exc), 500)


@router.get("/messages/pending")
def get_pending_messages(
    message_type: str | None = Query(default=None),
    since: str | None = Query(default=None),
):
    service = _require_push_service()
    if not service:
        return _error_response("推送服务未初始化", 500)

    try:
        messages = service.get_pending_messages(
            message_type=message_type,
            since=since,
        )
        return {"success": True, "messages": messages}
    except Exception as exc:
        return _error_response(str(exc), 500)


@router.get("/messages/{message_id}")
def get_message(message_id: str):
    service = _require_push_service()
    if not service:
        return _error_response("推送服务未初始化", 500)

    message = service.get_message(message_id)
    if not message:
        return _error_response("消息不存在", 404)

    return {"success": True, "data": message}


@router.post("/messages/{message_id}/push")
def push_message(message_id: str):
    service = _require_push_service()
    if not service:
        return _error_response("推送服务未初始化", 500)

    try:
        success = service.push_message(message_id)
        if not success:
            return _error_response("消息不存在", 404)
        return {"success": True, "message": "消息已推送"}
    except Exception as exc:
        return _error_response(str(exc), 500)


@router.post("/messages/{message_id}/read")
def mark_read(message_id: str):
    service = _require_push_service()
    if not service:
        return _error_response("推送服务未初始化", 500)

    success = service.mark_read(message_id)
    if not success:
        return _error_response("消息不存在", 404)

    return {"success": True, "message": "已标记为已读"}


@router.post("/messages/{message_id}/approve")
def approve_message(message_id: str, current_user: dict = Depends(get_current_user)):
    approval_service = _require_approval_service()
    if not approval_service:
        return _error_response("审批服务未初始化", 500)

    try:
        result = approval_service.approve_from_push_message(
            push_message_id=message_id,
            approved_by=current_user["user_id"],
        )
        return {"success": True, "data": result}
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except Exception as exc:
        return _error_response(str(exc), 500)


@router.post("/messages/{message_id}/reject")
def reject_message(message_id: str, current_user: dict = Depends(get_current_user)):
    approval_service = _require_approval_service()
    if not approval_service:
        return _error_response("审批服务未初始化", 500)

    try:
        result = approval_service.reject_from_push_message(
            push_message_id=message_id,
            rejected_by=current_user["user_id"],
        )
        return {"success": True, "data": result}
    except ValueError as exc:
        return _error_response(str(exc), 400)
    except Exception as exc:
        return _error_response(str(exc), 500)


@router.delete("/messages/{message_id}")
def delete_message(message_id: str):
    service = _require_push_service()
    if not service:
        return _error_response("推送服务未初始化", 500)

    success = service.delete_message(message_id)
    if not success:
        return _error_response("消息不存在", 404)

    return {"success": True, "message": "消息已删除"}


@router.get("/stream")
def sse_stream():
    service = _require_push_service()
    if not service:
        return _error_response("推送服务未初始化", 500)

    q = service.subscribe()

    def generate() -> Generator[str, None, None]:
        yield from service.event_stream(q)

    return sse_response_raw(generate())
