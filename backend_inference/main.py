import os
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI

# 确保可以从本地模块导入
# 将当前目录添加到 sys.path 中，以便能够导入 core, routers 等模块
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from core.model_container import model_engine
from core.config import settings
from routers import conflict

# 未来可以在此处轻松导入其他路由模块
# from routers import classification, traceability

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI 生命周期管理器
    """
    # 启动时：加载模型
    print(f"Initializing Model from: {settings.MODEL_PATH}")
    if os.path.exists(settings.MODEL_PATH):
        try:
            model_engine.load_model()
        except Exception as e:
            print(f"CRITICAL ERROR: Failed to load model files: {e}")
            # We continue startup so health checks pass, but inference will fail
    else:
        print(f"CRITICAL WARNING: Model directory not found at {settings.MODEL_PATH}")
    yield
    # 如果需要，可以在此处添加关闭时的逻辑 (Shutdown logic)

# 创建 FastAPI 应用实例
app = FastAPI(
    title="Semantic Atlas Inference API", 
    version="1.0",
    description="Backend inference service for requirement analysis.",
    lifespan=lifespan
)

from fastapi.middleware.cors import CORSMiddleware

# 添加 CORS 中间件，允许所有来源访问
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由 (Routers)
app.include_router(conflict.router)
# app.include_router(classification.router)
# app.include_router(traceability.router)

@app.get("/health")
def health_check():
    """
    健康检查接口
    检查模型是否已加载
    """
    return {"status": "ok", "model_loaded": model_engine.model is not None}

if __name__ == "__main__":
    import uvicorn
    # 启动 uvicorn 服务器
    uvicorn.run(app, host="0.0.0.0", port=8000)
