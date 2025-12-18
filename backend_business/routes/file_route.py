# /api/upload_csv, /api/download_result 路由占位符
import csv
import io
import json
from typing import Any, Dict, List, Tuple

from flask import Blueprint, jsonify, request, send_file

from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.db_service import db_service


file_bp = Blueprint("file_api", __name__)


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

