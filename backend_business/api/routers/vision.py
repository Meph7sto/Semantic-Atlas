"""
图生文回调与预览确认路由
"""

from datetime import datetime, timedelta, timezone
import hashlib
from threading import Lock
from typing import Any, Dict
from uuid import uuid4

import httpx
from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Request, UploadFile, status

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.api.routers.schemas.vision_schemas import (
    VisionAutoDLConfig,
    VisionCallbackPayload,
    VisionPreviewConfirmRequest,
)
from backend_business.config import settings
from backend_business.services.db_service import db_service
from backend_business.services.transcript_parser import parse_transcript_to_spans
from backend_business.services.vision_autodl_service import (
    VisionAutoDLError,
    run_caption as run_autodl_caption,
)


router = APIRouter(prefix="/api/v2/vision", tags=["vision"])

_PREVIEW_TTL_HOURS = 24
_previews: Dict[str, Dict[str, Any]] = {}
_preview_lock = Lock()


def _require_db_service():
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)
    return db_service


def _to_utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _to_iso(value: datetime) -> str:
    return value.isoformat()


def _cleanup_expired_previews(now: datetime) -> None:
    expired_ids = [
        preview_id
        for preview_id, item in _previews.items()
        if item.get("expires_at") and item["expires_at"] <= now
    ]
    for preview_id in expired_ids:
        _previews.pop(preview_id, None)


def _build_source_fingerprint(filename: str, transcript_text: str) -> str:
    raw = f"{filename}|{transcript_text}".encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def _save_preview(payload: VisionCallbackPayload, source: str) -> Dict[str, Any]:
    now = _to_utc_now()
    expires_at = now + timedelta(hours=_PREVIEW_TTL_HOURS)
    preview_id = str(uuid4())
    filename = (payload.filename or "").strip() or "unknown"
    fingerprint = _build_source_fingerprint(filename, payload.transcript_text)

    preview_record = {
        "preview_id": preview_id,
        "status": "pending",
        "created_at": now,
        "expires_at": expires_at,
        "confirmed_at": None,
        "session_id": None,
        "source": source,
        "source_fingerprint": fingerprint,
        "payload": payload.model_dump(),
    }

    with _preview_lock:
        _cleanup_expired_previews(now)
        _previews[preview_id] = preview_record

    return {
        "preview_id": preview_id,
        "status": "pending",
        "created_at": _to_iso(now),
        "expires_at": _to_iso(expires_at),
    }


def _verify_callback_source(
    x_vision_source: str | None,
    x_vision_source_token: str | None,
) -> None:
    expected_source = settings.VISION_CALLBACK_SOURCE
    expected_token = settings.VISION_CALLBACK_TOKEN
    if not expected_source or not expected_token:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="VISION_CALLBACK_SOURCE / VISION_CALLBACK_TOKEN 未配置",
        )

    if (x_vision_source or "").strip() != expected_source:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="非法来源",
        )
    if (x_vision_source_token or "").strip() != expected_token:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="来源校验失败",
        )


@router.post("/callback")
def receive_vision_callback(
    payload: VisionCallbackPayload,
    x_vision_source: str | None = Header(default=None),
    x_vision_source_token: str | None = Header(default=None),
):
    """
    AutoDL 回调入口：仅保存预览，不直接写入 spans。
    """
    _verify_callback_source(x_vision_source, x_vision_source_token)
    source = (x_vision_source or "").strip()
    preview_data = _save_preview(payload, source)
    return {"success": True, "data": preview_data}


@router.post("/caption")
async def caption_image_via_autodl(
    request: Request,
    file: UploadFile = File(...),
    prompt: str = Form("请详细描述图片内容，并总结关键信息。"),
    speaker: str = Form("vision_agent"),
    max_new_tokens: int | None = Form(default=None),
    autodl_config: str | None = Form(default=None),
    current_user: dict = Depends(get_current_user),
):
    _ = current_user
    if not file.content_type or not file.content_type.startswith("image/"):
        raise ErrorResponse("仅支持图片文件", 400)

    file_bytes = await file.read()
    if not file_bytes:
        raise ErrorResponse("空文件", 400)

    if not speaker.strip():
        raise ErrorResponse("speaker 不能为空", 400)
    if not prompt.strip():
        raise ErrorResponse("prompt 不能为空", 400)

    upstream_files = {
        "file": (
            file.filename or "upload.jpg",
            file_bytes,
            file.content_type or "application/octet-stream",
        )
    }
    upstream_data: Dict[str, Any] = {
        "prompt": prompt.strip(),
        "speaker": speaker.strip(),
    }
    if max_new_tokens is not None:
        if max_new_tokens <= 0:
            raise ErrorResponse("max_new_tokens 必须大于 0", 400)
        upstream_data["max_new_tokens"] = str(max_new_tokens)

    runtime_config: VisionAutoDLConfig | None = None
    if autodl_config and autodl_config.strip():
        try:
            runtime_config = VisionAutoDLConfig.from_json(autodl_config)
        except ValueError as exc:
            raise ErrorResponse(str(exc), 400)

    if runtime_config is not None:
        try:
            upstream_json = run_autodl_caption(
                runtime_config,
                filename=file.filename or "upload.jpg",
                content_type=file.content_type or "application/octet-stream",
                image_bytes=file_bytes,
                prompt=prompt.strip(),
                speaker=speaker.strip(),
                max_new_tokens=max_new_tokens,
                timeout_seconds=int(settings.VISION_CAPTION_TIMEOUT_SECONDS),
            )
        except VisionAutoDLError as exc:
            raise ErrorResponse(f"AutoDL 远端推理失败: {str(exc)}", 502)
        except Exception as exc:
            raise ErrorResponse(f"AutoDL 远端推理异常: {str(exc)}", 500)
    else:
        client = getattr(request.app.state, "http_client", None)
        if not isinstance(client, httpx.AsyncClient):
            raise ErrorResponse("HTTP 客户端未初始化", 500)

        try:
            upstream_resp = await client.post(
                settings.VISION_CAPTION_URL,
                data=upstream_data,
                files=upstream_files,
                timeout=settings.VISION_CAPTION_TIMEOUT_SECONDS,
            )
        except httpx.ConnectError:
            raise ErrorResponse(
                f"无法连接 AutoDL 图生文服务: {settings.VISION_CAPTION_URL}",
                503,
            )
        except httpx.TimeoutException:
            raise ErrorResponse("AutoDL 图生文服务超时", 504)
        except Exception as exc:
            raise ErrorResponse(f"调用 AutoDL 图生文服务失败: {str(exc)}", 500)

        try:
            upstream_json = upstream_resp.json()
        except ValueError:
            raise ErrorResponse(
                f"AutoDL 返回非 JSON 响应: {upstream_resp.text[:500]}",
                502,
            )

        if upstream_resp.status_code >= 400:
            detail = (
                upstream_json.get("detail")
                if isinstance(upstream_json, dict)
                else str(upstream_json)
            )
            raise ErrorResponse(
                f"AutoDL 图生文失败({upstream_resp.status_code}): {detail}",
                502,
            )

    try:
        payload = VisionCallbackPayload(
            success=bool(upstream_json.get("success", True)),
            filename=(upstream_json.get("filename") or file.filename or "upload.jpg"),
            speaker=(upstream_json.get("speaker") or speaker).strip(),
            prompt=(upstream_json.get("prompt") or prompt).strip(),
            caption=(upstream_json.get("caption") or "").strip(),
            transcript_text=(upstream_json.get("transcript_text") or "").strip(),
        )
    except Exception as exc:
        raise ErrorResponse(f"AutoDL 返回字段不完整: {str(exc)}", 502)

    preview_data = _save_preview(payload, source="local_upload")
    return {"success": True, "data": {"preview": preview_data, "result": payload.model_dump()}}


@router.get("/previews")
def list_vision_previews(current_user: dict = Depends(get_current_user)):
    _ = current_user
    now = _to_utc_now()

    with _preview_lock:
        _cleanup_expired_previews(now)
        items = []
        for item in _previews.values():
            payload = item["payload"]
            items.append(
                {
                    "preview_id": item["preview_id"],
                    "status": item["status"],
                    "created_at": _to_iso(item["created_at"]),
                    "expires_at": _to_iso(item["expires_at"]),
                    "confirmed_at": _to_iso(item["confirmed_at"])
                    if item["confirmed_at"]
                    else None,
                    "session_id": item["session_id"],
                    "filename": payload.get("filename"),
                    "speaker": payload.get("speaker"),
                    "prompt": payload.get("prompt"),
                    "caption": payload.get("caption"),
                    "transcript_text": payload.get("transcript_text"),
                }
            )

    items.sort(key=lambda x: x["created_at"], reverse=True)
    return {"success": True, "data": items}


@router.post("/previews/{preview_id}/confirm")
def confirm_vision_preview(
    preview_id: str,
    req: VisionPreviewConfirmRequest,
    current_user: dict = Depends(get_current_user),
):
    _ = current_user
    service = _require_db_service()
    now = _to_utc_now()

    with _preview_lock:
        _cleanup_expired_previews(now)
        preview = _previews.get(preview_id)
        if not preview:
            raise ErrorResponse("预览不存在或已过期", 404)
        if preview["status"] != "pending":
            raise ErrorResponse("该预览已确认入库", 409)

        payload = preview["payload"]
        session_id = req.session_id or str(uuid4())
        options = {
            "estimate_timestamps_if_missing": req.estimate_timestamps_if_missing,
            "default_span_ms": req.default_span_ms,
            "max_spans_returned": req.max_spans_returned,
        }

        spans, warnings, stats = parse_transcript_to_spans(
            payload["transcript_text"],
            session_id,
            options,
        )
        upsert_result = service.upsert_spans(spans)
        conflict_warnings = [
            f"span_id conflict: {conflict['span_id']}"
            for conflict in upsert_result.get("conflicts", [])
        ]
        all_warnings = warnings + conflict_warnings

        preview["status"] = "confirmed"
        preview["confirmed_at"] = now
        preview["session_id"] = session_id

    return {
        "success": True,
        "data": {
            "preview_id": preview_id,
            "session_id": session_id,
            "span_total": len(spans),
            "warnings": all_warnings,
            "spans_preview": spans[: req.max_spans_returned],
            "stats": stats,
        },
    }
