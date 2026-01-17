from flask import Blueprint, Response, jsonify, request
import requests
import os

from backend_business.config import settings
from backend_business.services.doors_store import DoorsStore

classification_bp = Blueprint("classification", __name__)

# Allow separating classification service port; default 8001
CLASSIFICATION_SERVICE_URL = os.getenv("CLASSIFICATION_URL", "http://localhost:8000")


def _normalize_fnf_label(raw: str) -> str:
    """
    你要求当前分类暂时只有：功能需求 / 非功能需求。
    这里做一个最小映射：
    - 只要包含“功能”且不包含“非”，归为 功能需求
    - 其他全部归为 非功能需求
    """
    s = (raw or "").strip()
    if ("功能" in s) and ("非" not in s):
        return "功能需求"
    return "非功能需求"


def _maybe_store_classification(payload: dict, resp_data: dict) -> dict | None:
    if not settings.DOORS_DB_URL:
        return None

    project_name = (payload.get("project_name") or settings.DOORS_PROJECT_NAME or "default").strip()
    created_by = (payload.get("created_by") or "").strip() or None

    store = DoorsStore(settings.DOORS_DB_URL)
    project_id = store.ensure_project(project_name)
    ws_id = store.create_workspace(project_id, scope_query={"stage": "classify"}, created_by=created_by)
    run_id = store.create_analysis_run(workspace_id=ws_id, stage="classify", config={}, status="success")

    # 推理后端返回结构：{total, predictions:[{index,requirement,predicted_label}], label_distribution}
    predictions = resp_data.get("predictions") or []
    stored_ids = []
    for item in predictions:
        try:
            text_body = (item.get("requirement") or "").strip()
            if not text_body:
                continue
            obj = store.upsert_requirement(
                project_id=project_id,
                object_type="system",
                text_body=text_body,
                status="Proposed",
                source_kind="manual",
                created_by=created_by,
                quality_metrics={"source": "classification_input", "run_id": run_id},
            )
            label = _normalize_fnf_label(str(item.get("predicted_label") or ""))
            cid = store.insert_classification_result(
                run_id=run_id,
                object_id=obj.object_id,
                label=label,
                score=None,
                rationale=None,
                status="proposed",
            )
            stored_ids.append(cid)
        except Exception:
            continue

    return {"project_id": project_id, "workspace_id": ws_id, "analysis_run_id": run_id, "stored": len(stored_ids)}


@classification_bp.route("/predict-texts", methods=["POST"])
def classify_texts():
    try:
        data = request.json or {}
        resp = requests.post(
            f"{CLASSIFICATION_SERVICE_URL}/classification/predict-texts", json=data
        )
        try:
            resp_data = resp.json()
        except ValueError:
            resp_data = {"detail": f"Upstream Error: {resp.text}"}

        # 仅在 upstream 成功时落库
        doors = None
        if resp.status_code == 200 and isinstance(resp_data, dict) and "predictions" in resp_data:
            doors = _maybe_store_classification(data, resp_data)
            resp_data = {**resp_data, "doors": doors}

        return jsonify(resp_data), resp.status_code
    except requests.exceptions.ConnectionError:
        return (
            jsonify(
                {
                    "detail": f"Cannot connect to Classification Service at {CLASSIFICATION_SERVICE_URL}. Is it running?"
                }
            ),
            503,
        )
    except Exception as e:
        return jsonify({"detail": f"Business Backend Error: {str(e)}"}), 500


@classification_bp.route("/predict-csv", methods=["POST"])
def classify_csv():
    try:
        file = request.files.get("file")
        if not file:
            return jsonify({"detail": "请上传 CSV 文件"}), 400
        files = {"file": (file.filename, file.stream, file.mimetype)}
        resp = requests.post(
            f"{CLASSIFICATION_SERVICE_URL}/classification/predict-csv", files=files
        )

        # Pass through JSON errors
        content_type = resp.headers.get("Content-Type", "")
        if content_type.startswith("application/json"):
            return jsonify(resp.json()), resp.status_code

        # Pass through CSV (or other binary) response
        excluded = {
            "content-encoding",
            "transfer-encoding",
            "connection",
            "content-length",
        }
        headers = [(k, v) for k, v in resp.headers.items() if k.lower() not in excluded]
        return Response(resp.content, status=resp.status_code, headers=headers)
    except requests.exceptions.ConnectionError:
        return (
            jsonify(
                {
                    "detail": f"Cannot connect to Classification Service at {CLASSIFICATION_SERVICE_URL}. Is it running?"
                }
            ),
            503,
        )
    except Exception as e:
        return jsonify({"detail": f"Business Backend Error: {str(e)}"}), 500
