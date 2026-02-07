import os
import sys
from flask import Flask
from flask_cors import CORS

# Ensure project root is on sys.path so `python backend_business/app.py` works reliably
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend_business.config import settings
from backend_business.routes.analysis_route import analysis_bp
from backend_business.routes.conflict_routes import conflict_bp
from backend_business.routes.file_route import file_bp
from backend_business.routes.requirements_route import requirements_bp
from backend_business.routes.classification_routes import classification_bp
from backend_business.routes.manage_routes import manage_bp
from backend_business.routes.product_routes import product_bp
from backend_business.routes.push_routes import push_bp
from backend_business.routes.mobile_chat_routes import mobile_chat_bp
from backend_business.routes.deduplication_route import dedup_bp
from backend_business.routes.ai_chat_routes import ai_chat_bp
from backend_business.routes.agent_task_routes import agent_task_bp


def create_app() -> Flask:
    app = Flask(__name__)

    # 让 jsonify 直接输出中文（不转义为 \uXXXX），便于本地 curl / 日志阅读
    try:
        app.json.ensure_ascii = False  # type: ignore[attr-defined]
    except Exception:
        app.config["JSON_AS_ASCII"] = False

    # CORS
    if settings.CORS_ORIGINS == "*":
        CORS(app, resources={r"/api/*": {"origins": "*"}})
    else:
        origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
        CORS(app, resources={r"/api/*": {"origins": origins}})

    # Register blueprints
    app.register_blueprint(analysis_bp, url_prefix="/api")
    app.register_blueprint(conflict_bp, url_prefix="/api/conflict")
    app.register_blueprint(file_bp, url_prefix="/api")
    app.register_blueprint(requirements_bp, url_prefix="/api")
    app.register_blueprint(classification_bp, url_prefix="/api/classification")
    app.register_blueprint(manage_bp, url_prefix="/api/manage")
    app.register_blueprint(product_bp, url_prefix="/api/product")
    app.register_blueprint(push_bp, url_prefix="/api/push")
    app.register_blueprint(mobile_chat_bp, url_prefix="/api/mobile")
    app.register_blueprint(dedup_bp, url_prefix="/api/dedup")
    app.register_blueprint(ai_chat_bp, url_prefix="/api/ai-chat")
    app.register_blueprint(agent_task_bp, url_prefix="/api/agent-tasks")

    # 兼容主框架：提供 /health（非 /api/health）
    @app.get("/health")
    def root_health():
        return {
            "status": "business_backend_ok",
            "inference_url": os.getenv("INFERENCE_URL", "http://localhost:8000"),
            "classification_url": os.getenv(
                "CLASSIFICATION_URL", "http://localhost:8000"
            ),
        }

    return app


app = create_app()


if __name__ == "__main__":
    app.run(host=settings.HOST, port=settings.PORT, debug=settings.DEBUG)
