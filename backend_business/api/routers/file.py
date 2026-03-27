"""
文件上传/下载路由 - FastAPI 版本
对应历史蓝图: file_bp (url_prefix="/api/v2")
"""

import csv
import io
import json
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from fastapi.responses import FileResponse, Response

from backend_business.api.deps.auth import get_current_user, require_admin
from backend_business.api.http.errors import ErrorResponse
from backend_business.config import settings
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service
from backend_business.services.file_service import FileService

router = APIRouter(prefix="/api/v2", tags=["file"])

file_service = FileService(settings.UPLOAD_FOLDER)


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
    folder: str = Form(default=""),
    import_time: str = Form(default=""),
    capture_time: str = Form(default=""),
    current_user: dict = Depends(get_current_user),
):
    """
    通用文件上传端点（供移动端使用）。
    可选 folder 参数指定子文件夹。
    """
    user_id = current_user["user_id"]

    try:
        content = await file.read()
        saved_file = file_service.save_uploaded_file(
            user_id=user_id,
            original_filename=file.filename or "",
            content=content,
            description=description,
            content_type=file.content_type,
            folder=folder.strip() if folder else "",
            import_time=import_time,
            capture_time=capture_time,
        )

        return {
            "success": True,
            "message": "Upload successful",
            "filename": saved_file["filename"],
            "originalFilename": saved_file["originalFilename"],
            "fileSize": saved_file["fileSize"],
            "uploadTime": saved_file["uploadTime"],
            "folder": saved_file.get("folder", ""),
            "checksum": saved_file.get("checksum"),
        }
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(f"Failed to save file: {str(exc)}", 500)


@router.get("/uploads")
async def list_uploaded_files(current_user: dict = Depends(get_current_user)):
    """
    获取已上传文件列表。
    """
    user_id = current_user["user_id"]
    files: list[dict[str, Any]] = file_service.list_uploaded_files(user_id)

    return {
        "success": True,
        "files": files,
        "total": len(files),
    }


@router.get("/uploads/tree")
async def list_user_file_tree(current_user: dict = Depends(get_current_user)):
    """
    获取当前用户的文件树结构（文件夹 -> 文件）。
    """
    user_id = current_user["user_id"]
    tree = file_service.list_user_file_tree(user_id)
    return {
        "success": True,
        **tree,
    }


@router.get("/uploads/content")
async def preview_or_download_my_file(
    path: str = Query(...),
    download: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    """
    通过相对路径预览或下载当前用户自己的文件。
    """
    user_id = current_user["user_id"]
    file_path, mime, safe_filename = file_service.resolve_user_file_by_relative_path(
        user_id, path
    )
    if download:
        return FileResponse(
            path=file_path,
            media_type=mime,
            filename=safe_filename.rsplit("/", 1)[-1],
            content_disposition_type="attachment",
        )
    return FileResponse(path=file_path, media_type=mime)


@router.get("/folders")
async def list_user_folders(current_user: dict = Depends(get_current_user)):

    """
    获取用户的文件夹列表。
    """
    user_id = current_user["user_id"]
    folders = file_service.list_user_folders(user_id)
    return {
        "success": True,
        "folders": folders,
    }


@router.get("/folders/{folder_name}/files")
async def list_folder_files(
    folder_name: str,
    current_user: dict = Depends(get_current_user),
):
    """
    获取指定文件夹内的文件列表。
    """
    user_id = current_user["user_id"]
    files = file_service.list_folder_files(user_id, folder_name)
    return {
        "success": True,
        "files": files,
        "total": len(files),
    }


@router.get("/uploads/{filename}")
async def download_uploaded_file(
    filename: str,
    download: bool = Query(default=False),
    current_user: dict = Depends(get_current_user),
):
    """
    下载/预览已上传文件。

    GET /api/v2/uploads/{filename}
    可选参数：?download=true 强制下载（而非预览）
    """
    user_id = current_user["user_id"]
    file_path, mime, safe_filename = file_service.resolve_accessible_file(
        user_id, filename
    )
    if download:
        return FileResponse(
            path=file_path,
            media_type=mime,
            filename=safe_filename,
            content_disposition_type="attachment",
        )

    return FileResponse(path=file_path, media_type=mime)


@router.delete("/uploads/{filename}")
async def delete_uploaded_file(
    filename: str,
    current_user: dict = Depends(get_current_user),
):
    """
    删除已上传文件。
    """
    user_id = current_user["user_id"]
    try:
        file_service.delete_uploaded_file(user_id, filename)
        return {
            "success": True,
            "message": "File deleted successfully",
        }
    except ErrorResponse:
        raise
    except Exception as exc:
        raise ErrorResponse(f"Failed to delete file: {str(exc)}", 500)


@router.get("/admin/uploads")
async def list_all_user_files(current_user: dict = Depends(require_admin)):
    """
    管理员获取所有用户上传的文件列表，按用户分组。
    """
    files_by_user = file_service.list_all_users_files()
    total_files = sum(len(files) for files in files_by_user.values())

    return {
        "success": True,
        "files": files_by_user,
        "total": total_files,
        "userCount": len(files_by_user),
    }


@router.get("/admin/uploads/tree")
async def list_all_user_file_tree(current_user: dict = Depends(require_admin)):
    """
    管理员按用户 -> 文件夹 -> 文件结构查看上传内容。
    """
    users = file_service.list_all_users_file_tree()
    return {
        "success": True,
        "users": users,
        "userCount": len(users),
        "total": sum(user.get("totalFiles", 0) for user in users),
    }


@router.get("/admin/uploads/content")
async def preview_or_download_user_file(
    user_id: str = Query(...),
    path: str = Query(...),
    download: bool = Query(default=False),
    current_user: dict = Depends(require_admin),
):
    """
    管理员按用户和相对路径预览/下载文件。
    """
    _ = current_user
    file_path, mime, safe_filename = file_service.resolve_user_file_by_relative_path(
        user_id, path
    )
    if download:
        return FileResponse(
            path=file_path,
            media_type=mime,
            filename=safe_filename.rsplit("/", 1)[-1],
            content_disposition_type="attachment",
        )
    return FileResponse(path=file_path, media_type=mime)


@router.delete("/admin/uploads/content")
async def delete_user_file_by_path(
    user_id: str = Query(...),
    path: str = Query(...),
    current_user: dict = Depends(require_admin),
):
    """
    管理员按用户和相对路径删除文件。
    """
    _ = current_user
    try:
        file_service.delete_user_file_by_relative_path(user_id, path)
        return {
            "success": True,
            "message": "File deleted successfully",
        }
    except ErrorResponse:
        raise
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
        high = (
            row.get("high_level_requirement") or row.get("high") or row.get("A") or ""
        ).strip()
        low = (
            row.get("low_level_requirement") or row.get("low") or row.get("B") or ""
        ).strip()
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
async def download_result(record_id: int = Query(alias="id")):
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
