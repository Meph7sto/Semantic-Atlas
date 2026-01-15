
from flask import Blueprint, request, jsonify
from backend_business.services.ai_proxy import ai_proxy

requirements_bp = Blueprint("requirements", __name__)

@requirements_bp.post("/requirements/extract")
def extract_requirements():
    data = request.get_json()
    if not data or "text" not in data:
        return jsonify({"error": "Missing 'text' field"}), 400
    
    text = data["text"]
    chunk_size = data.get("chunk_size", 3600)
    overlap = data.get("overlap", 500)
    clean_model = data.get("clean_model", "deepseek-chat")
    extract_model = data.get("extract_model", "deepseek-reasoner")
    
    try:
        result = ai_proxy.extract_requirements(
            text, 
            chunk_size, 
            overlap, 
            clean_model=clean_model, 
            extract_model=extract_model
        )
        return jsonify(result)
    except Exception as e:
        # Proxy or backend error
        return jsonify({"error": str(e)}), 500
