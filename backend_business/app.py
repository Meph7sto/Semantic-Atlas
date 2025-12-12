from flask import Flask, jsonify
from flask_cors import CORS
from routes.conflict_routes import conflict_bp

app = Flask(__name__)
CORS(app)

# Configuration
BUSINESS_PORT = 5001

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "business_backend_ok"})

# Register Blueprints
# This maps /api/conflict/check -> conflict_bp.check_conflict
app.register_blueprint(conflict_bp, url_prefix='/api/conflict')

if __name__ == '__main__':
    # Use 0.0.0.0 to listen on all interfaces
    # debug=True removed for better practice, or use env var if needed
    app.run(host='0.0.0.0', port=BUSINESS_PORT)
