# 数据库连接、端口等配置占位符
# 此文件用于存放数据库连接字符串、端口号等配置信息
import os


class Settings:
    """
    业务后端（backend_business）配置：
    - 负责对外提供 /api/* 业务接口
    - 负责数据落库（PostgreSQL）
    - 负责调用 backend_inference 推理服务（默认 http://localhost:8000）
    """

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

    # Flask
    HOST = os.environ.get("BUSINESS_HOST", "0.0.0.0")
    PORT = int(os.environ.get("BUSINESS_PORT", "5001"))
    DEBUG = os.environ.get("BUSINESS_DEBUG", "1") in ("1", "true", "True")

    # Inference service (FastAPI)
    # 不一致时以冲突为主：优先读取 INFERENCE_URL，其次 INFERENCE_BASE_URL
    INFERENCE_BASE_URL = os.environ.get("INFERENCE_URL") or os.environ.get("INFERENCE_BASE_URL", "http://localhost:8000")

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


settings = Settings()
