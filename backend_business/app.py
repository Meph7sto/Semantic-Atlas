"""
业务后端兼容入口（旧架构已下线）。

保留该文件用于兼容旧启动命令/旧导入路径：
- `python backend_business/app.py`
- `from backend_business.app import app`
"""

from backend_business.config import settings
from backend_business.main import app


def create_app():
    return app


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "backend_business.main:app",
        host=settings.HOST,
        port=settings.PORT,
        reload=settings.DEBUG,
    )
