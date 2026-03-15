"""
业务后端（backend_business）配置：
- 支持从环境变量读取
- 也支持自动加载项目根目录的 .env（便于本地开发）
"""

import os

# 尝试自动加载项目根目录的 .env，便于本地开发/测试
try:
    from dotenv import load_dotenv  # type: ignore
except ImportError:
    load_dotenv = None

if load_dotenv:
    _ROOT_ENV_PATH = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env"
    )
    load_dotenv(_ROOT_ENV_PATH, override=False)


class Settings:
    """
    业务后端（backend_business）配置：
    - 负责对外提供 /api/v2/* 业务接口
    - 负责数据落库（PostgreSQL）
    - 负责调用 backend_inference 推理服务（默认 http://localhost:8000）
    """

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    # 项目根目录（backend_business 的上一级）
    ROOT_DIR = os.path.dirname(BASE_DIR)

    # 文件上传目录：优先读取环境变量，默认使用项目根下的 data/uploads/
    UPLOAD_FOLDER = os.environ.get(
        "UPLOAD_FOLDER",
        os.path.join(ROOT_DIR, "data", "uploads"),
    )

    # Business API (FastAPI)
    HOST = os.environ.get("BUSINESS_HOST", "0.0.0.0")
    PORT = int(os.environ.get("BUSINESS_PORT", "5002"))
    DEBUG = os.environ.get("BUSINESS_DEBUG", "1") in ("1", "true", "True")

    # Inference service (FastAPI)
    # 不一致时以冲突为主：优先读取 INFERENCE_URL，其次 INFERENCE_BASE_URL
    INFERENCE_BASE_URL = os.environ.get("INFERENCE_URL") or os.environ.get(
        "INFERENCE_BASE_URL", "http://localhost:8000"
    )
    ASR_REMOTE_BASE_URL = os.environ.get(
        "ASR_REMOTE_BASE_URL", INFERENCE_BASE_URL
    ).rstrip("/")
    ASR_REMOTE_TRANSCRIBE_PATH = os.environ.get(
        "ASR_REMOTE_TRANSCRIBE_PATH", "/asr/transcribe"
    )
    ASR_REMOTE_HEALTH_PATH = os.environ.get("ASR_REMOTE_HEALTH_PATH", "/asr/health")
    ASR_REMOTE_AUTH_TOKEN = os.environ.get("ASR_REMOTE_AUTH_TOKEN", "")
    ASR_REMOTE_TIMEOUT_SECONDS = float(
        os.environ.get("ASR_REMOTE_TIMEOUT_SECONDS", "1800")
    )
    ASR_MAX_UPLOAD_MB = int(os.environ.get("ASR_MAX_UPLOAD_MB", "200"))
    ASR_ALLOWED_EXTENSIONS = os.environ.get(
        "ASR_ALLOWED_EXTENSIONS", "wav,mp3,m4a,mp4"
    )

    # Storage (PostgreSQL)
    POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "127.0.0.1")
    POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
    POSTGRES_USER = os.environ.get("POSTGRES_USER", "semantic")
    POSTGRES_PASSWORD = os.environ.get("POSTGRES_PASSWORD", "semantic_dev")
    POSTGRES_DB = os.environ.get("POSTGRES_DB", "semantic_atlas")
    DATABASE_URL = os.environ.get("DATABASE_URL")

    @property
    def POSTGRES_DSN(self) -> str:
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"postgresql://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
            f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
        )

    # CORS
    CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "*")  # 生产建议配置为具体域名

    # JWT 认证
    JWT_SECRET_KEY = os.environ.get(
        "JWT_SECRET_KEY", "semantic-atlas-jwt-secret-key-2024-change-in-production"
    )
    JWT_ALGORITHM = "HS256"
    JWT_EXPIRY_HOURS = int(os.environ.get("JWT_EXPIRY_HOURS", "24"))

    # RequirementActor 分布式协调（可选）
    REDIS_URL = os.environ.get("REDIS_URL", "").strip()
    ACTOR_INSTANCE_ID = os.environ.get("ACTOR_INSTANCE_ID", "").strip()

    # Vision 回调来源校验
    VISION_CALLBACK_SOURCE = os.environ.get("VISION_CALLBACK_SOURCE", "autodl")
    VISION_CALLBACK_TOKEN = os.environ.get("VISION_CALLBACK_TOKEN") or os.environ.get(
        "FRP_TOKEN", ""
    )
    VISION_CAPTION_URL = os.environ.get(
        "VISION_CAPTION_URL", "http://127.0.0.1:9000/caption-image"
    )
    VISION_SERVICE_TOKEN = os.environ.get("VISION_SERVICE_TOKEN", "").strip()
    VISION_CAPTION_TIMEOUT_SECONDS = float(
        os.environ.get("VISION_CAPTION_TIMEOUT_SECONDS", "120")
    )


settings = Settings()
