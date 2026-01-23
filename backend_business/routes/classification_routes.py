from flask import Blueprint, Response, jsonify, request
import requests
import os

from backend_business.services.db_service import db_service

classification_bp = Blueprint("classification", __name__)

# Allow separating classification service port; default 8001
CLASSIFICATION_SERVICE_URL = os.getenv("CLASSIFICATION_URL", "http://localhost:8000")


@classification_bp.route("/predict-texts", methods=["POST"])
def classify_texts():
    try:
        data = request.json or {}
        save_to_db = bool(data.get("save_to_db", False))
        session_id = data.get("session_id")

        # 移除业务层参数，只传递分类服务需要的参数
        payload = {k: v for k, v in data.items() if k not in ['save_to_db', 'session_id']}

        resp = requests.post(
            f"{CLASSIFICATION_SERVICE_URL}/classification/predict-texts", json=payload
        )
        try:
            resp_data = resp.json()
        except ValueError:
            resp_data = {"detail": f"Upstream Error: {resp.text}"}

        record_id = None
        if save_to_db and db_service and resp.status_code == 200:
            requirements = data.get("requirements", [])
            predictions = resp_data.get("predictions", [])
            label_distribution = resp_data.get("label_distribution")
            total = resp_data.get("total")

            if requirements and predictions:
                record_id = db_service.save_classification(
                    session_id=session_id,
                    requirements=requirements,
                    predictions=predictions,
                    label_distribution=label_distribution,
                    total=total,
                    result_json=resp_data,
                )

        result = resp_data.copy() if isinstance(resp_data, dict) else {"data": resp_data}
        if record_id is not None:
            result["record_id"] = record_id

        return jsonify(result), resp.status_code
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
