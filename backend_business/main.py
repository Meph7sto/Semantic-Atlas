"""
FastAPI 业务后端入口点
统一承载业务接口（包含 /api/v2/*）
"""

import os
import sys
import logging
from contextlib import asynccontextmanager
from logging import Filter

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


class InternalEndpointsFilter(Filter):
    """过滤内部端点的访问日志"""

    def filter(self, record):
        # 过滤掉内部端点的 INFO 级别日志
        if (
            "/api/v2/_internals/" in record.getMessage()
            and record.levelno == logging.INFO
        ):
            return False
        return True


def configure_uvicorn_access_log_filter() -> None:
    """确保 uvicorn.access 仅安装一次内部端点过滤器。"""
    uvicorn_access_logger = logging.getLogger("uvicorn.access")
    for log_filter in uvicorn_access_logger.filters:
        if isinstance(log_filter, InternalEndpointsFilter):
            return
    uvicorn_access_logger.addFilter(InternalEndpointsFilter())


# 无论通过 uvicorn 模块路径还是 python 入口启动，均启用过滤器。
configure_uvicorn_access_log_filter()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期管理器
    """
    # 启动时的逻辑
    print("[lifespan] FastAPI business backend starting...")
    print(f"[lifespan] Inference URL: {settings.INFERENCE_BASE_URL}")
    print(
        f"[lifespan] Database: {settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )
    app.state.classification_http_client = httpx.AsyncClient()
    app.state.http_client = httpx.AsyncClient()

    yield

    # 关闭时的逻辑
    classification_client = getattr(app.state, "classification_http_client", None)
    if isinstance(classification_client, httpx.AsyncClient):
        await classification_client.aclose()
    http_client = getattr(app.state, "http_client", None)
    if isinstance(http_client, httpx.AsyncClient):
        await http_client.aclose()
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
    agent_chat,
    analysis,
    asr,
    auth,
    classification,
    conflict,
    deduplication,
    execution_graph,
    file,
    manage,
    mobile_chat,
    permission,
    product,
    push,
    requirement_actor,
    requirements,
    vision,
)

app.include_router(agent_chat.router)
app.include_router(deduplication.router)
app.include_router(auth.router)
app.include_router(permission.router)
app.include_router(manage.router)
app.include_router(product.router)
app.include_router(analysis.router)
app.include_router(conflict.router)
app.include_router(classification.router)
app.include_router(requirements.router)
app.include_router(requirement_actor.router)
app.include_router(requirement_actor.internals_router)
app.include_router(push.router)
app.include_router(mobile_chat.router)
app.include_router(file.router)
app.include_router(execution_graph.router)
app.include_router(vision.router)
app.include_router(asr.router)

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

    # 显式调用一次，确保直接脚本启动也覆盖到。
    configure_uvicorn_access_log_filter()

    # 启动 uvicorn 服务器
    uvicorn.run(
        "backend_business.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
