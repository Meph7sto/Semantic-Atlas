"""
文件服务：封装上传目录隔离、兼容 legacy 文件访问和文件读写逻辑。
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime
from typing import Any

from werkzeug.utils import secure_filename

from backend_business.api.http.errors import ErrorResponse


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


class FileService:
    def __init__(self, upload_folder: str):
        self.upload_folder = os.path.abspath(upload_folder)
        self.legacy_folder = os.path.join(self.upload_folder, "legacy")
        self._uploaded_files_cache: dict[str, dict[str, Any]] = {}

        os.makedirs(self.upload_folder, exist_ok=True)
        os.makedirs(self.legacy_folder, exist_ok=True)

    @staticmethod
    def _allowed_file(filename: str) -> bool:
        return (
            "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS
        )

    @staticmethod
    def _get_file_extension(filename: str) -> str:
        return filename.rsplit(".", 1)[1].lower() if "." in filename else ""

    @staticmethod
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

    @staticmethod
    def _is_within(base_path: str, target_path: str) -> bool:
        base = os.path.abspath(base_path)
        target = os.path.abspath(target_path)
        return os.path.commonpath([base, target]) == base

    def _normalize_user_id(self, user_id: str) -> str:
        normalized = str(user_id or "").strip()
        if not normalized:
            raise ErrorResponse("Invalid user id", 401)

        if "/" in normalized or "\\" in normalized or ".." in normalized:
            raise ErrorResponse("Invalid user id", 400)

        return normalized

    def _get_user_folder(self, user_id: str) -> str:
        normalized_user_id = self._normalize_user_id(user_id)
        user_folder = os.path.abspath(
            os.path.join(self.upload_folder, normalized_user_id)
        )
        if not self._is_within(self.upload_folder, user_folder):
            raise ErrorResponse("Invalid user id", 400)
        os.makedirs(user_folder, exist_ok=True)
        return user_folder

    @staticmethod
    def _validate_request_filename(filename: str) -> str:
        safe_filename = secure_filename(filename or "")
        if not safe_filename or safe_filename != filename:
            raise ErrorResponse("Invalid filename", 400)
        return safe_filename

    def _build_file_info(self, file_path: str, filename: str) -> dict[str, Any]:
        cache_key = os.path.abspath(file_path)
        cached = self._uploaded_files_cache.get(cache_key)
        if cached:
            return cached

        stat = os.stat(file_path)
        ext = self._get_file_extension(filename)
        file_info = {
            "filename": filename,
            "originalFilename": filename,
            "fileSize": stat.st_size,
            "uploadTime": datetime.utcfromtimestamp(stat.st_mtime).isoformat() + "Z",
            "mimeType": self._guess_mime_type(ext),
            "extension": ext,
            "description": "",
        }
        self._uploaded_files_cache[cache_key] = file_info
        return file_info

    def save_uploaded_file(
        self,
        user_id: str,
        original_filename: str,
        content: bytes,
        description: str = "",
        content_type: str | None = None,
    ) -> dict[str, Any]:
        if not original_filename:
            raise ErrorResponse("No file selected", 400)

        if not self._allowed_file(original_filename):
            allowed_types = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise ErrorResponse(
                f"File type not allowed. Allowed types: {allowed_types}", 400
            )

        ext = self._get_file_extension(original_filename)
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        raw_base = (
            original_filename.rsplit(".", 1)[0]
            if "." in original_filename
            else original_filename
        )
        safe_base = secure_filename(raw_base)
        if not safe_base:
            safe_base = "file"
        safe_base = safe_base[:50] if len(safe_base) > 50 else safe_base
        saved_filename = (
            f"{timestamp}_{unique_id}_{safe_base}.{ext}"
            if ext
            else f"{timestamp}_{unique_id}_{safe_base}"
        )

        user_folder = self._get_user_folder(user_id)
        file_path = os.path.join(user_folder, saved_filename)

        try:
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as exc:
            raise ErrorResponse(f"Failed to save file: {str(exc)}", 500)

        file_size = os.path.getsize(file_path)
        upload_time = datetime.utcnow().isoformat() + "Z"

        file_info = {
            "filename": saved_filename,
            "originalFilename": original_filename,
            "fileSize": file_size,
            "uploadTime": upload_time,
            "mimeType": content_type or "application/octet-stream",
            "extension": ext,
            "description": description,
        }
        self._uploaded_files_cache[os.path.abspath(file_path)] = file_info
        return file_info

    def list_uploaded_files(self, user_id: str) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        user_folder = self._get_user_folder(user_id)

        scan_dirs = [user_folder, self.legacy_folder, self.upload_folder]
        for scan_dir in scan_dirs:
            if not os.path.exists(scan_dir):
                continue
            for filename in os.listdir(scan_dir):
                file_path = os.path.join(scan_dir, filename)
                if not os.path.isfile(file_path):
                    continue
                files.append(self._build_file_info(file_path, filename))

        files.sort(key=lambda x: x["uploadTime"], reverse=True)
        return files

    def resolve_accessible_file(
        self, user_id: str, filename: str
    ) -> tuple[str, str, str]:
        safe_filename = self._validate_request_filename(filename)
        user_folder = self._get_user_folder(user_id)

        for base_dir in (user_folder, self.legacy_folder, self.upload_folder):
            candidate = os.path.abspath(os.path.join(base_dir, safe_filename))
            if not self._is_within(base_dir, candidate):
                continue
            if os.path.isfile(candidate):
                ext = self._get_file_extension(safe_filename)
                return candidate, self._guess_mime_type(ext), safe_filename

        raise ErrorResponse("File not found", 404)

    def delete_uploaded_file(self, user_id: str, filename: str) -> None:
        file_path, _, _ = self.resolve_accessible_file(user_id, filename)
        try:
            os.remove(file_path)
            self._uploaded_files_cache.pop(os.path.abspath(file_path), None)
        except Exception as exc:
            raise ErrorResponse(f"Failed to delete file: {str(exc)}", 500)
