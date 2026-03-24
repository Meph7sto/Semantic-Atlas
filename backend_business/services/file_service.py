"""
文件服务：封装上传目录隔离、兼容 legacy 文件访问和文件读写逻辑。
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

from backend_business.api.http.errors import ErrorResponse


ALLOWED_EXTENSIONS = {
    "txt",
    "pdf",
    "png",
    "jpg",
    "jpeg",
    "gif",
    "webp",
    "heic",
    "heif",
    "doc",
    "docx",
    "xls",
    "xlsx",
    "csv",
    "json",
    "xml",
    "zip",
    "m4a",
    "mp4",
    "mp3",
    "wav",
}

METADATA_SUFFIX = ".meta.json"


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

    def _normalize_user_id(self, user_id: str) -> str:
        normalized = str(user_id or "").strip()
        if not normalized:
            raise ErrorResponse("Invalid user id", 401)

        if "/" in normalized or "\\" in normalized or ".." in normalized:
            raise ErrorResponse("Invalid user id", 400)

        return normalized

    @staticmethod
    def _normalize_relative_path(path: str, *, allow_empty: bool = False) -> str:
        normalized = str(path or "").strip().replace("\\", "/")
        while "//" in normalized:
            normalized = normalized.replace("//", "/")
        normalized = normalized.strip("/")

        if not normalized:
            if allow_empty:
                return ""
            raise ErrorResponse("Invalid path", 400)

        parts: list[str] = []
        for raw_part in normalized.split("/"):
            part = raw_part.strip()
            if not part or part in {".", ".."}:
                raise ErrorResponse("Invalid path", 400)
            parts.append(part)
        return "/".join(parts)

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
    def _is_within(parent: str, child: str) -> bool:
        """检查 child 路径是否在 parent 目录内，防止目录遍历攻击。"""
        parent_abs = os.path.abspath(parent)
        child_abs = os.path.abspath(child)
        return child_abs.startswith(parent_abs + os.sep) or child_abs == parent_abs

    @staticmethod
    def _normalize_timestamp(value: str | int | None) -> int | str | None:
        normalized = str(value or "").strip()
        if not normalized:
            return None
        if normalized.isdigit():
            return int(normalized)
        return normalized

    @staticmethod
    def _metadata_path(file_path: str) -> str:
        return f"{file_path}{METADATA_SUFFIX}"

    def _read_metadata(self, file_path: str) -> dict[str, Any]:
        metadata_path = self._metadata_path(file_path)
        if not os.path.isfile(metadata_path):
            return {}

        try:
            with open(metadata_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _write_metadata(self, file_path: str, metadata: dict[str, Any]) -> None:
        metadata_path = self._metadata_path(file_path)
        with open(metadata_path, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _is_metadata_file(filename: str) -> bool:
        return filename.endswith(METADATA_SUFFIX)

    def _resolve_relative_target(
        self, base_dir: str, relative_path: str
    ) -> tuple[str, str]:
        normalized = self._normalize_relative_path(relative_path)
        candidate = os.path.abspath(os.path.join(base_dir, *normalized.split("/")))
        if not self._is_within(base_dir, candidate):
            raise ErrorResponse("Invalid path", 400)
        return normalized, candidate

    @staticmethod
    def _apply_relative_location(
        file_info: dict[str, Any], relative_path: str | None
    ) -> dict[str, Any]:
        result = dict(file_info)
        if not relative_path:
            result.setdefault("relativePath", result.get("filename", ""))
            result.setdefault("folder", "")
            return result

        normalized = relative_path.replace(os.sep, "/")
        folder = normalized.rsplit("/", 1)[0] if "/" in normalized else ""
        result["relativePath"] = normalized
        result["folder"] = folder
        return result

    def _iter_files(self, base_dir: str, *, recursive: bool) -> list[str]:
        if not os.path.isdir(base_dir):
            return []

        file_paths: list[str] = []
        if recursive:
            for root, _, filenames in os.walk(base_dir):
                for filename in filenames:
                    if self._is_metadata_file(filename):
                        continue
                    file_path = os.path.join(root, filename)
                    if os.path.isfile(file_path):
                        file_paths.append(file_path)
            return file_paths

        for filename in os.listdir(base_dir):
            if self._is_metadata_file(filename):
                continue
            file_path = os.path.join(base_dir, filename)
            if os.path.isfile(file_path):
                file_paths.append(file_path)
        return file_paths

    def _build_file_info(self, file_path: str, filename: str) -> dict[str, Any]:
        cache_key = os.path.abspath(file_path)
        cached = self._uploaded_files_cache.get(cache_key)
        if cached:
            return dict(cached)

        stat = os.stat(file_path)
        ext = self._get_file_extension(filename)
        metadata = self._read_metadata(file_path)
        file_info = {
            "filename": filename,
            "originalFilename": metadata.get("originalFilename") or filename,
            "fileSize": stat.st_size,
            "uploadTime": metadata.get("uploadTime")
            or datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat(),
            "mimeType": metadata.get("mimeType") or self._guess_mime_type(ext),
            "extension": metadata.get("extension") or ext,
            "description": metadata.get("description", ""),
            "folder": metadata.get("folder", ""),
            "relativePath": metadata.get("relativePath") or filename,
            "importTime": metadata.get("importTime"),
            "captureTime": metadata.get("captureTime"),
        }
        self._uploaded_files_cache[cache_key] = file_info
        return dict(file_info)

    def save_uploaded_file(
        self,
        user_id: str,
        original_filename: str,
        content: bytes,
        description: str = "",
        content_type: str | None = None,
        folder: str = "",
        import_time: str = "",
        capture_time: str = "",
    ) -> dict[str, Any]:
        if not original_filename:
            raise ErrorResponse("No file selected", 400)

        if not self._allowed_file(original_filename):
            allowed_types = ", ".join(sorted(ALLOWED_EXTENSIONS))
            raise ErrorResponse(
                f"File type not allowed. Allowed types: {allowed_types}", 400
            )

        ext = self._get_file_extension(original_filename)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        unique_id = uuid.uuid4().hex[:8]
        raw_base = (
            original_filename.rsplit(".", 1)[0]
            if "." in original_filename
            else original_filename
        )
        safe_base = "".join(
            ch if ch.isalnum() or ch in {"-", "_"} else "_"
            for ch in raw_base.strip()
        ).strip("_")
        if not safe_base:
            safe_base = "file"
        safe_base = safe_base[:50] if len(safe_base) > 50 else safe_base
        saved_filename = (
            f"{timestamp}_{unique_id}_{safe_base}.{ext}"
            if ext
            else f"{timestamp}_{unique_id}_{safe_base}"
        )

        user_folder = self._get_user_folder(user_id)

        # 如果指定了文件夹，存储到子目录
        safe_folder = ""
        if folder:
            safe_folder, target_dir = self._resolve_relative_target(user_folder, folder)
            os.makedirs(target_dir, exist_ok=True)
            file_path = os.path.join(target_dir, saved_filename)
        else:
            file_path = os.path.join(user_folder, saved_filename)

        try:
            with open(file_path, "wb") as f:
                f.write(content)
        except Exception as exc:
            raise ErrorResponse(f"Failed to save file: {str(exc)}", 500)

        file_size = os.path.getsize(file_path)
        upload_time = datetime.now(timezone.utc).isoformat()
        relative_path = f"{safe_folder}/{saved_filename}" if safe_folder else saved_filename
        metadata = {
            "originalFilename": original_filename,
            "fileSize": file_size,
            "uploadTime": upload_time,
            "mimeType": content_type or self._guess_mime_type(ext),
            "extension": ext,
            "description": description,
            "folder": safe_folder,
            "relativePath": relative_path,
            "importTime": self._normalize_timestamp(import_time),
            "captureTime": self._normalize_timestamp(capture_time),
            "userId": self._normalize_user_id(user_id),
        }
        self._write_metadata(file_path, metadata)

        file_info = {
            "filename": saved_filename,
            "originalFilename": original_filename,
            "fileSize": file_size,
            "uploadTime": upload_time,
            "mimeType": content_type or "application/octet-stream",
            "extension": ext,
            "description": description,
            "folder": safe_folder,
            "relativePath": relative_path,
            "importTime": metadata["importTime"],
            "captureTime": metadata["captureTime"],
        }
        self._uploaded_files_cache[os.path.abspath(file_path)] = file_info
        return dict(file_info)

    def list_uploaded_files(self, user_id: str) -> list[dict[str, Any]]:
        files: list[dict[str, Any]] = []
        user_folder = self._get_user_folder(user_id)

        for file_path in self._iter_files(user_folder, recursive=True):
            relative_path = os.path.relpath(file_path, user_folder).replace(os.sep, "/")
            file_info = self._build_file_info(file_path, os.path.basename(file_path))
            files.append(self._apply_relative_location(file_info, relative_path))

        for scan_dir in (self.legacy_folder, self.upload_folder):
            for file_path in self._iter_files(scan_dir, recursive=False):
                files.append(
                    self._apply_relative_location(
                        self._build_file_info(file_path, os.path.basename(file_path)),
                        os.path.basename(file_path),
                    )
                )

        files.sort(key=lambda x: x["uploadTime"], reverse=True)
        return files

    def resolve_accessible_file(
        self, user_id: str, filename: str
    ) -> tuple[str, str, str]:
        user_folder = self._get_user_folder(user_id)
        requested_name = str(filename or "").strip()
        if not requested_name or "/" in requested_name or "\\" in requested_name:
            raise ErrorResponse("Invalid filename", 400)

        for base_dir, recursive in (
            (user_folder, True),
            (self.legacy_folder, False),
            (self.upload_folder, False),
        ):
            for candidate in self._iter_files(base_dir, recursive=recursive):
                if os.path.basename(candidate) != requested_name:
                    continue
                ext = self._get_file_extension(requested_name)
                return candidate, self._guess_mime_type(ext), requested_name

        raise ErrorResponse("File not found", 404)

    def resolve_user_file_by_relative_path(
        self, user_id: str, relative_path: str
    ) -> tuple[str, str, str]:
        user_folder = self._get_user_folder(user_id)
        normalized_path, file_path = self._resolve_relative_target(user_folder, relative_path)
        if not os.path.isfile(file_path) or self._is_metadata_file(os.path.basename(file_path)):
            raise ErrorResponse("File not found", 404)

        safe_filename = os.path.basename(file_path)
        ext = self._get_file_extension(safe_filename)
        return file_path, self._guess_mime_type(ext), normalized_path

    def delete_uploaded_file(self, user_id: str, filename: str) -> None:
        file_path, _, _ = self.resolve_accessible_file(user_id, filename)
        try:
            os.remove(file_path)
            metadata_path = self._metadata_path(file_path)
            if os.path.isfile(metadata_path):
                os.remove(metadata_path)
            self._uploaded_files_cache.pop(os.path.abspath(file_path), None)
        except Exception as exc:
            raise ErrorResponse(f"Failed to delete file: {str(exc)}", 500)

    def delete_user_file_by_relative_path(self, user_id: str, relative_path: str) -> None:
        file_path, _, _ = self.resolve_user_file_by_relative_path(user_id, relative_path)
        try:
            os.remove(file_path)
            metadata_path = self._metadata_path(file_path)
            if os.path.isfile(metadata_path):
                os.remove(metadata_path)
            self._uploaded_files_cache.pop(os.path.abspath(file_path), None)
        except Exception as exc:
            raise ErrorResponse(f"Failed to delete file: {str(exc)}", 500)

    def list_all_users_files(self) -> dict[str, list[dict[str, Any]]]:
        """
        获取所有用户的文件列表，按 user_id 分组返回。
        返回格式: {user_id: [file1, file2, ...]}
        """
        all_files = {}
        if not os.path.exists(self.upload_folder):
            return all_files

        for user_dir_name in os.listdir(self.upload_folder):
            user_dir_path = os.path.join(self.upload_folder, user_dir_name)
            if not os.path.isdir(user_dir_path) or user_dir_name == "legacy":
                continue

            files = []
            for file_path in self._iter_files(user_dir_path, recursive=True):
                relative_path = os.path.relpath(file_path, user_dir_path).replace(
                    os.sep, "/"
                )
                file_info = self._apply_relative_location(
                    self._build_file_info(file_path, os.path.basename(file_path)),
                    relative_path,
                )
                file_info["user_id"] = user_dir_name
                file_info["userId"] = user_dir_name
                files.append(file_info)

            if files:
                files.sort(key=lambda x: x["uploadTime"], reverse=True)
                all_files[user_dir_name] = files

        return all_files

    def list_all_users_file_tree(self) -> list[dict[str, Any]]:
        users: list[dict[str, Any]] = []
        if not os.path.exists(self.upload_folder):
            return users

        for user_dir_name in sorted(os.listdir(self.upload_folder)):
            user_dir_path = os.path.join(self.upload_folder, user_dir_name)
            if not os.path.isdir(user_dir_path) or user_dir_name == "legacy":
                continue

            root_files: list[dict[str, Any]] = []
            folders_map: dict[str, dict[str, Any]] = {}

            for file_path in self._iter_files(user_dir_path, recursive=True):
                relative_path = os.path.relpath(file_path, user_dir_path).replace(
                    os.sep, "/"
                )
                file_info = self._apply_relative_location(
                    self._build_file_info(file_path, os.path.basename(file_path)),
                    relative_path,
                )
                file_info["userId"] = user_dir_name

                folder_path = file_info.get("folder", "")
                if folder_path:
                    folder_entry = folders_map.setdefault(
                        folder_path,
                        {
                            "name": folder_path.rsplit("/", 1)[-1],
                            "path": folder_path,
                            "fileCount": 0,
                            "files": [],
                        },
                    )
                    folder_entry["files"].append(file_info)
                    folder_entry["fileCount"] += 1
                else:
                    root_files.append(file_info)

            folders = list(folders_map.values())
            for folder in folders:
                folder["files"].sort(key=lambda x: x["uploadTime"], reverse=True)
            folders.sort(key=lambda x: x["path"])
            root_files.sort(key=lambda x: x["uploadTime"], reverse=True)

            total_files = len(root_files) + sum(folder["fileCount"] for folder in folders)
            if total_files == 0:
                continue

            users.append(
                {
                    "userId": user_dir_name,
                    "folders": folders,
                    "rootFiles": root_files,
                    "folderCount": len(folders),
                    "totalFiles": total_files,
                }
            )

        return users

    def list_user_file_tree(self, user_id: str) -> dict[str, Any]:
        """
        获取指定用户的文件树（文件夹 -> 文件结构）。
        返回: { folders, rootFiles, folderCount, totalFiles }
        """
        user_dir_path = self._get_user_folder(user_id)

        root_files: list[dict[str, Any]] = []
        folders_map: dict[str, dict[str, Any]] = {}

        for file_path in self._iter_files(user_dir_path, recursive=True):
            relative_path = os.path.relpath(file_path, user_dir_path).replace(os.sep, "/")
            file_info = self._apply_relative_location(
                self._build_file_info(file_path, os.path.basename(file_path)),
                relative_path,
            )
            file_info["userId"] = user_id

            folder_path = file_info.get("folder", "")
            if folder_path:
                folder_entry = folders_map.setdefault(
                    folder_path,
                    {
                        "name": folder_path.rsplit("/", 1)[-1],
                        "path": folder_path,
                        "fileCount": 0,
                        "files": [],
                    },
                )
                folder_entry["files"].append(file_info)
                folder_entry["fileCount"] += 1
            else:
                root_files.append(file_info)

        folders = list(folders_map.values())
        for folder in folders:
            folder["files"].sort(key=lambda x: x["uploadTime"], reverse=True)
        folders.sort(key=lambda x: x["path"])
        root_files.sort(key=lambda x: x["uploadTime"], reverse=True)

        total_files = len(root_files) + sum(f["fileCount"] for f in folders)

        return {
            "folders": folders,
            "rootFiles": root_files,
            "folderCount": len(folders),
            "totalFiles": total_files,
        }

    def list_user_folders(self, user_id: str) -> list[dict[str, Any]]:
        """
        列出用户上传目录中的所有子文件夹。
        """
        user_folder = self._get_user_folder(user_id)
        folders: list[dict[str, Any]] = []

        if not os.path.exists(user_folder):
            return folders

        for entry in os.listdir(user_folder):
            entry_path = os.path.join(user_folder, entry)
            if not os.path.isdir(entry_path):
                continue

            # 统计文件夹内的文件数量
            file_count = len(self._iter_files(entry_path, recursive=True))

            # 获取最后修改时间
            stat = os.stat(entry_path)
            last_modified = datetime.fromtimestamp(stat.st_mtime, timezone.utc).isoformat()

            folders.append(
                {
                    "name": entry,
                    "fileCount": file_count,
                    "lastModified": last_modified,
                }
            )

        folders.sort(key=lambda x: x["lastModified"], reverse=True)
        return folders

    def list_folder_files(
        self, user_id: str, folder_name: str
    ) -> list[dict[str, Any]]:
        """
        列出用户指定文件夹内的所有文件。
        """
        user_folder = self._get_user_folder(user_id)
        safe_folder, folder_path = self._resolve_relative_target(user_folder, folder_name)

        if not os.path.isdir(folder_path):
            raise ErrorResponse("Folder not found", 404)

        files: list[dict[str, Any]] = []
        for file_path in self._iter_files(folder_path, recursive=True):
            relative_path = os.path.relpath(file_path, user_folder).replace(os.sep, "/")
            files.append(
                self._apply_relative_location(
                    self._build_file_info(file_path, os.path.basename(file_path)),
                    relative_path,
                )
            )

        files.sort(key=lambda x: x["uploadTime"], reverse=True)
        return files
