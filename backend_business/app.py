from flask import Flask, request, jsonify
from flask_cors import CORS
import requests

app = Flask(__name__)
CORS(app)

# Configuration
INFERENCE_SERVICE_URL = "http://localhost:8000"
BUSINESS_PORT = 5001

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "business_backend_ok"})

@app.route('/api/conflict/check', methods=['POST'])
def check_conflict():
    """
    Proxy request to Inference Backend
    """
    try:
        data = request.json
        # Forward to Inference Backend
        resp = requests.post(f"{INFERENCE_SERVICE_URL}/conflict/check", json=data)
        return jsonify(resp.json()), resp.status_code
    except requests.exceptions.ConnectionError:
        return jsonify({"detail": "Inference service unavailable"}), 503
    except Exception as e:
        return jsonify({"detail": str(e)}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=BUSINESS_PORT, debug=True)
