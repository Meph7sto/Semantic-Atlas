"""
FastAPI 业务后端入口点
统一承载业务接口（包含 /api/v2/*）
"""

import os
import sys
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import httpx

# 确保项目根目录在 sys.path 中
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backend_business.config import settings
from backend_business.api.http.errors import (
    ErrorResponse,
    error_response_handler,
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期管理器
    """
    # 启动时的逻辑
    print("[lifespan] FastAPI business backend starting...")
    print(f"[lifespan] Inference URL: {settings.INFERENCE_BASE_URL}")
    print(f"[lifespan] Database: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}")
    app.state.classification_http_client = httpx.AsyncClient()

    yield

    # 关闭时的逻辑
    client = getattr(app.state, "classification_http_client", None)
    if isinstance(client, httpx.AsyncClient):
        await client.aclose()
    print("[lifespan] FastAPI business backend shutting down...")


# 创建 FastAPI 应用实例
app = FastAPI(
    title="Semantic Atlas Business API",
    version="2.0.0",
    description="Business backend for requirement analysis - FastAPI version",
    lifespan=lifespan,
    json_encoder=None,  # 使用默认 JSON 编码器（已支持中文）
)

# CORS 配置
if settings.CORS_ORIGINS == "*":
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
else:
    origins = [o.strip() for o in settings.CORS_ORIGINS.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )


# 注册路由（FastAPI）
# - auth 走 /api/v2/auth，认证模块
# - permission 走 /api/v2/permission，权限管理模块
# - manage 走 /api/v2/manage，项目管理模块
# - product 走 /api/v2/product，产品管理模块
# - conflict 走 /api/v2/conflict，冲突检测模块
# - mobile_chat 走 /api/v2/mobile，移动端消息模块
# - file 走 /api/v2/*，文件上传下载模块
from backend_business.api.routers import (
    analysis,
    auth,
    classification,
    conflict,
    deduplication,
    execution_graph,
    file,
    manage,
    mobile_chat,
    permission,
    push,
    product,
    requirements,
)
app.include_router(deduplication.router)
app.include_router(auth.router)
app.include_router(permission.router)
app.include_router(manage.router)
app.include_router(product.router)
app.include_router(analysis.router)
app.include_router(conflict.router)
app.include_router(classification.router)
app.include_router(requirements.router)
app.include_router(push.router)
app.include_router(mobile_chat.router)
app.include_router(file.router)
app.include_router(execution_graph.router)

# 注册业务异常处理器（保留 FastAPI 原生 HTTPException / validation 语义）
app.add_exception_handler(ErrorResponse, error_response_handler)


@app.get("/health")
def health_check():
    """
    健康检查接口

    Response:
        {
            "status": "business_backend_ok",
            "inference_url": "http://localhost:8000",
            "classification_url": "http://localhost:8000"
        }
    """
    return {
        "status": "business_backend_ok",
        "inference_url": settings.INFERENCE_BASE_URL,
        "classification_url": settings.INFERENCE_BASE_URL,
    }


if __name__ == "__main__":
    import uvicorn

    # 启动 uvicorn 服务器
    uvicorn.run(
        "backend_business.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
