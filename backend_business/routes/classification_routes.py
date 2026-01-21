from flask import Blueprint, Response, jsonify, request
import requests
import os

classification_bp = Blueprint("classification", __name__)

# Allow separating classification service port; default 8001
CLASSIFICATION_SERVICE_URL = os.getenv("CLASSIFICATION_URL", "http://localhost:8000")


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
