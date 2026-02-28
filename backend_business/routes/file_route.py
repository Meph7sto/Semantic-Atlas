# /api/upload_csv, /api/download_result, /api/upload 路由
import csv
import io
import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Tuple

from flask import Blueprint, jsonify, request, send_file, send_from_directory
from werkzeug.utils import secure_filename

from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service


file_bp = Blueprint("file_api", __name__)

# 文件上传配置
UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.dirname(__file__)), "uploads")
ALLOWED_EXTENSIONS = {"txt", "pdf", "png", "jpg", "jpeg", "gif", "doc", "docx", "xls", "xlsx", "csv", "json", "xml", "zip"}
MAX_CONTENT_LENGTH = 50 * 1024 * 1024  # 50MB

# 确保上传目录存在
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# 内存缓存：存储上传文件的元数据
_uploaded_files_cache: Dict[str, Dict[str, Any]] = {}


def allowed_file(filename: str) -> bool:
    """检查文件扩展名是否允许"""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def get_file_extension(filename: str) -> str:
    """获取文件扩展名"""
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


@file_bp.route("/upload", methods=["POST"])
def upload_file():
    """
    通用文件上传端点（供移动端使用）。

    接收 multipart/form-data 格式的文件，保存到 uploads 目录。

    返回：
    {
        "success": true,
        "message": "Upload successful",
        "filename": "xxx.jpg",
        "fileSize": 12345,
        "uploadTime": "2025-01-30T10:00:00Z"
    }
    """
    if "file" not in request.files:
        return jsonify({
            "success": False,
            "message": "No file part in request"
        }), 400

    f = request.files["file"]
    if f.filename == "":
        return jsonify({
            "success": False,
            "message": "No file selected"
        }), 400

    original_filename = f.filename
    if not allowed_file(original_filename):
        return jsonify({
            "success": False,
            "message": f"File type not allowed. Allowed types: {', '.join(ALLOWED_EXTENSIONS)}"
        }), 400

    # 生成安全的文件名（保留原始扩展名，添加时间戳和UUID避免冲突）
    ext = get_file_extension(original_filename)
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    safe_base = secure_filename(original_filename.rsplit(".", 1)[0] if "." in original_filename else original_filename)
    # 限制基础文件名长度
    safe_base = safe_base[:50] if len(safe_base) > 50 else safe_base
    saved_filename = f"{timestamp}_{unique_id}_{safe_base}.{ext}" if ext else f"{timestamp}_{unique_id}_{safe_base}"

    file_path = os.path.join(UPLOAD_FOLDER, saved_filename)

    try:
        f.save(file_path)
        file_size = os.path.getsize(file_path)
        upload_time = datetime.utcnow().isoformat() + "Z"

        # 获取可选的描述字段
        description = request.form.get("description", "")

        # 缓存文件元数据
        _uploaded_files_cache[saved_filename] = {
            "filename": saved_filename,
            "originalFilename": original_filename,
            "fileSize": file_size,
            "uploadTime": upload_time,
            "mimeType": f.content_type or "application/octet-stream",
            "extension": ext,
            "description": description,
        }

        return jsonify({
            "success": True,
            "message": "Upload successful",
            "filename": saved_filename,
            "originalFilename": original_filename,
            "fileSize": file_size,
            "uploadTime": upload_time,
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Failed to save file: {str(e)}"
        }), 500


@file_bp.route("/uploads", methods=["GET"])
def list_uploaded_files():
    """
    获取已上传的文件列表。

    返回：
    {
        "success": true,
        "files": [
            {
                "filename": "xxx.jpg",
                "originalFilename": "photo.jpg",
                "fileSize": 12345,
                "uploadTime": "2025-01-30T10:00:00Z",
                "mimeType": "image/jpeg",
                "extension": "jpg"
            },
            ...
        ]
    }
    """
    files = []

    # 扫描上传目录，补充缓存中没有的文件
    if os.path.exists(UPLOAD_FOLDER):
        for filename in os.listdir(UPLOAD_FOLDER):
            file_path = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(file_path):
                if filename in _uploaded_files_cache:
                    files.append(_uploaded_files_cache[filename])
                else:
                    # 文件存在但不在缓存中（可能是服务重启后），从文件系统获取信息
                    stat = os.stat(file_path)
                    ext = get_file_extension(filename)
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

    # 按上传时间降序排列
    files.sort(key=lambda x: x["uploadTime"], reverse=True)

    return jsonify({
        "success": True,
        "files": files,
        "total": len(files)
    })


@file_bp.route("/uploads/<filename>", methods=["GET"])
def download_uploaded_file(filename: str):
    """
    下载/预览已上传的文件。

    GET /api/uploads/<filename>
    可选参数：?download=true 强制下载（而非预览）
    """
    safe_filename = secure_filename(filename)
    file_path = os.path.join(UPLOAD_FOLDER, safe_filename)

    if not os.path.exists(file_path):
        return jsonify({
            "success": False,
            "message": "File not found"
        }), 404

    # 检查是否强制下载
    force_download = request.args.get("download", "").lower() in ("true", "1", "yes")

    return send_from_directory(
        UPLOAD_FOLDER,
        safe_filename,
        as_attachment=force_download
    )


@file_bp.route("/uploads/<filename>", methods=["DELETE"])
def delete_uploaded_file(filename: str):
    """
    删除已上传的文件。

    DELETE /api/uploads/<filename>
    """
    safe_filename = secure_filename(filename)
    file_path = os.path.join(UPLOAD_FOLDER, safe_filename)

    if not os.path.exists(file_path):
        return jsonify({
            "success": False,
            "message": "File not found"
        }), 404

    try:
        os.remove(file_path)
        # 从缓存中移除
        _uploaded_files_cache.pop(safe_filename, None)
        return jsonify({
            "success": True,
            "message": "File deleted successfully"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"Failed to delete file: {str(e)}"
        }), 500


def _guess_mime_type(ext: str) -> str:
    """根据扩展名猜测 MIME 类型"""
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


@file_bp.route("/upload_csv", methods=["POST"])
def upload_csv():
    """
    上传 CSV 并进行批量追溯分析。

    CSV 格式要求（至少两列）：
    - high_level_requirement
    - low_level_requirement

    返回：批量分析结果（聚合为 highs/lows + batch-relation 调用）
    """
    if "file" not in request.files:
        return jsonify({"success": False, "error": "未找到上传文件字段 file"}), 400

    f = request.files["file"]
    content = f.read()
    try:
        text = content.decode("utf-8-sig")
    except Exception:
        text = content.decode("utf-8", errors="ignore")

    reader = csv.DictReader(io.StringIO(text))
    highs: List[str] = []
    lows: List[str] = []

    for row in reader:
        high = (row.get("high_level_requirement") or row.get("high") or row.get("A") or "").strip()
        low = (row.get("low_level_requirement") or row.get("low") or row.get("B") or "").strip()
        if high and low:
            highs.append(high)
            lows.append(low)

    if not highs or not lows:
        return jsonify({"success": False, "error": "CSV 中未解析到有效的 high/low 需求对"}), 400

    # 去重（保序）
    def _uniq(xs: List[str]) -> List[str]:
        seen = set()
        out = []
        for x in xs:
            if x in seen:
                continue
            seen.add(x)
            out.append(x)
        return out

    highs_u = _uniq(highs)
    lows_u = _uniq(lows)

    save_to_db = str(request.form.get("save_to_db", "false")).lower() in ("1", "true", "yes")
    max_new_tokens = int(request.form.get("max_new_tokens", 1600))

    try:
        result = ai_proxy.trace_batch(highs_u, lows_u, max_new_tokens=max_new_tokens)
        record_id = None
        if save_to_db:
            record_id = db_service.save_batch(highs_u, lows_u, result)
        return jsonify({"success": True, "data": result, "record_id": record_id})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@file_bp.route("/download_result", methods=["GET"])
def download_result():
    """
    下载某条分析记录的 output_json（作为 .json 文件）。
    GET /api/download_result?id=123
    """
    rid = request.args.get("id", type=int)
    if not rid:
        return jsonify({"success": False, "error": "缺少参数 id"}), 400

    detail = db_service.get_requirement_detail(rid)
    if not detail:
        return jsonify({"success": False, "error": "资源未找到"}), 404

    output = detail.get("output", {})
    buf = io.BytesIO(json.dumps(output, ensure_ascii=False, indent=2).encode("utf-8"))
    buf.seek(0)
    return send_file(
        buf,
        as_attachment=True,
        download_name=f"trace_result_{rid}.json",
        mimetype="application/json; charset=utf-8",
    )

