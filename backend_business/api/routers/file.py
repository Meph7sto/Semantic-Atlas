"""
文件上传/下载路由 - FastAPI 版本
对应历史蓝图: file_bp (url_prefix="/api/v2")
"""

import csv
import io
import json
import os
import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response
from werkzeug.utils import secure_filename

from backend_business.api.http.errors import ErrorResponse
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service

router = APIRouter(prefix="/api/v2", tags=["file"])

# 文件上传配置
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "uploads")
ALLOWED_EXTENSIONS = {
    "txt",
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "csv",
    "json",
    "xml",
    "zip",
}

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 内存缓存：存储上传文件的元数据
_uploaded_files_cache: dict[str, dict[str, Any]] = {}


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_file_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def _guess_mime_type(ext: str) -> str:
    mime_map = {
        "txt": "text/plain",
        "pdf": "application/pdf",
        "png": "image/png",
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "gif": "image/gif",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "csv": "text/csv",
        "json": "application/json",
        "xml": "application/xml",
        "zip": "application/zip",
    }
    return mime_map.get(ext.lower(), "application/octet-stream")


def _uniq(xs: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in xs:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out


@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    description: str = Form(default=""),
):
    """
    通用文件上传端点（供移动端使用）。
    """
    if not file.filename:
        raise ErrorResponse("No file selected", 400)

    original_filename = file.filename
    if not _allowed_file(original_filename):
        allowed_types = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ErrorResponse(f"File type not allowed. Allowed types: {allowed_types}", 400)

    ext = _get_file_extension(original_filename)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    raw_base = original_filename.rsplit(".", 1)[0] if "." in original_filename else original_filename
    safe_base = secure_filename(raw_base)
    safe_base = safe_base[:50] if len(safe_base) > 50 else safe_base
    saved_filename = f"{timestamp}_{unique_id}_{safe_base}.{ext}" if ext else f"{timestamp}_{unique_id}_{safe_base}"

    file_path = os.path.join(UPLOAD_FOLDER, saved_filename)

    try:
        content = await file.read()
        with open(file_path, "wb") as f:
            f.write(content)

        file_size = os.path.getsize(file_path)
        upload_time = datetime.utcnow().isoformat() + "Z"

        _uploaded_files_cache[saved_filename] = {
            "filename": saved_filename,
            "originalFilename": original_filename,
            "fileSize": file_size,
            "uploadTime": upload_time,
            "mimeType": file.content_type or "application/octet-stream",
            "extension": ext,
            "description": description,
        }

        return {
            "success": True,
            "message": "Upload successful",
            "filename": saved_filename,
            "originalFilename": original_filename,
            "fileSize": file_size,
            "uploadTime": upload_time,
        }
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(f"Failed to save file: {str(exc)}", 500)


@router.get("/uploads")
def list_uploaded_files():
    """
    获取已上传文件列表。
    """
    files: list[dict[str, Any]] = []

    if os.path.exists(UPLOAD_FOLDER):
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            if not os.path.isfile(file_path):
                continue

            if filename in _uploaded_files_cache:
                files.append(_uploaded_files_cache[filename])
                continue

            stat = os.stat(file_path)
            ext = _get_file_extension(filename)
            file_info = {
                "filename": filename,
                "originalFilename": filename,
                "fileSize": stat.st_size,
                "uploadTime": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
                "mimeType": _guess_mime_type(ext),
                "extension": ext,
                "description": "",
            }
            _uploaded_files_cache[filename] = file_info
            files.append(file_info)

    files.sort(key=lambda x: x["uploadTime"], reverse=True)

    return {
        "success": True,
        "files": files,
        "total": len(files),
    }


@router.get("/uploads/{filename}")
def download_uploaded_file(
    filename: str,
    download: bool = Query(default=False),
):
    """
    下载/预览已上传文件。

    GET /api/v2/uploads/{filename}
    可选参数：?download=true 强制下载（而非预览）
    """
    safe_filename = secure_filename(filename)
    file_path = os.path.join(UPLOAD_FOLDER, safe_filename)

    if not os.path.exists(file_path):
        raise ErrorResponse("File not found", 404)

    ext = _get_file_extension(safe_filename)
    mime = _guess_mime_type(ext)
    if download:
        return FileResponse(
            path=file_path,
            media_type=mime,
            filename=safe_filename,
            content_disposition_type="attachment",
        )

    return FileResponse(path=file_path, media_type=mime)


@router.delete("/uploads/{filename}")
def delete_uploaded_file(filename: str):
    """
    删除已上传文件。
    """
    safe_filename = secure_filename(filename)
    file_path = os.path.join(UPLOAD_FOLDER, safe_filename)

    if not os.path.exists(file_path):
        raise ErrorResponse("File not found", 404)

    try:
        os.remove(file_path)
        _uploaded_files_cache.pop(safe_filename, None)
        return {
            "success": True,
            "message": "File deleted successfully",
        }
    except Exception as exc:
        raise ErrorResponse(f"Failed to delete file: {str(exc)}", 500)


@router.post("/upload_csv")
async def upload_csv(
    file: UploadFile = File(...),
    save_to_db: bool = Form(default=False),
    max_new_tokens: int = Form(default=1600),
):
    """
    上传 CSV 并进行批量追溯分析。
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    reader = csv.DictReader(io.StringIO(text))
    highs: list[str] = []
    lows: list[str] = []

    for row in reader:
        high = (row.get("high_level_requirement") or row.get("high") or row.get("A") or "").strip()
        low = (row.get("low_level_requirement") or row.get("low") or row.get("B") or "").strip()
        if high and low:
            highs.append(high)
            lows.append(low)

    if not highs or not lows:
        raise ErrorResponse("CSV 中未解析到有效的 high/low 需求对", 400)

    highs_u = _uniq(highs)
    lows_u = _uniq(lows)

    try:
        result = ai_proxy.trace_batch(highs_u, lows_u, max_new_tokens=max_new_tokens)
        record_id = None
        if save_to_db:
            if db_service is None:
                raise ErrorResponse("数据库服务未初始化", 500)
            record_id = db_service.save_batch(highs_u, lows_u, result)

        return {"success": True, "data": result, "record_id": record_id}
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(str(exc), 500)


@router.get("/download_result")
def download_result(record_id: int = Query(alias="id")):
    """
    下载某条分析记录的 output_json（作为 .json 文件）。
    GET /api/v2/download_result?id=123
    """
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)

    detail = db_service.get_requirement_detail(record_id)
    if not detail:
        raise ErrorResponse("资源未找到", 404)

    output = detail.get("output", {})
    data = json.dumps(output, ensure_ascii=False, indent=2).encode("utf-8")
    headers = {
        "Content-Disposition": f'attachment; filename="trace_result_{record_id}.json"'
    }
    return Response(
        content=data,
        media_type="application/json; charset=utf-8",
        headers=headers,
    )
