from flask import Blueprint, request, jsonify
import requests
import os

# Create a Blueprint
conflict_bp = Blueprint('conflict', __name__)

# Configuration
# Read from env or default to localhost:8000
INFERENCE_SERVICE_URL = os.getenv("INFERENCE_URL", "http://localhost:8000")

@conflict_bp.route('/check', methods=['POST'])
def check_conflict():
    """
    Proxy request to Inference Backend
    """
    try:
        data = request.json
        # Forward to Inference Backend
        # Note: The path is now /conflict/conflict/check ? No, Blueprint prefix handles /api/conflict
        # The inference backend expects /conflict/check.
        
        resp = requests.post(f"{INFERENCE_SERVICE_URL}/conflict/check", json=data)
        
        # Try to parse JSON, if not, return text
        try:
            resp_data = resp.json()
        except ValueError:
            resp_data = {"detail": f"Upstream Inference Error: {resp.text}"}

        return jsonify(resp_data), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"detail": f"Cannot connect to Inference Service at {INFERENCE_SERVICE_URL}. Is it running?"}), 503
    except Exception as e:
        return jsonify({"detail": f"Business Backend Error: {str(e)}"}), 500
