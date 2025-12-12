#!/bin/bash
set -euo pipefail

# 项目根目录
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"

# 默认前端打包路径，可通过环境变量覆盖
FRONTEND_ROOT="${FRONTEND_ROOT:-${BASE_DIR}/frontend/dist}"

# 日志目录
mkdir -p "${BASE_DIR}/deploy/logs"
PID_PATH="${BASE_DIR}/deploy/logs/nginx.pid"

echo "[start] 使用前端目录: ${FRONTEND_ROOT}"

# 1) 前端构建（如 dist 不存在则构建）
if [ ! -d "$FRONTEND_ROOT" ]; then
  echo "[start] 前端 dist 未找到，开始安装依赖并构建..."
  (cd frontend && npm install && npm run build)
else
  echo "[start] 已存在 dist，跳过前端构建"
fi

# 2) 生成 Nginx 配置并重载
echo "[start] 生成 Nginx 配置..."
export FRONTEND_ROOT
envsubst '$FRONTEND_ROOT' < "${BASE_DIR}/deploy/nginx.conf" > "${BASE_DIR}/deploy/nginx.generated.conf"

echo "[start] 启动/重载 Nginx..."
nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;" -s reload 2>/dev/null || \
nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;"

# 3) 启动 FastAPI 推理服务
echo "[start] 启动 FastAPI 推理服务 (8000)..."
nohup uvicorn backend_inference.main:app --host 0.0.0.0 --port 8000 \
  > "${BASE_DIR}/deploy/logs/inference.log" 2>&1 &

# 4) 启动 Flask 业务服务
echo "[start] 启动 Flask 业务服务 (5001)..."
nohup python backend_business/app.py \
  > "${BASE_DIR}/deploy/logs/business.log" 2>&1 &

echo "[start] 全部服务已尝试启动。Nginx 监听 8008，Flask 5001，FastAPI 8000。"
echo "[start] 查看日志: tail -f deploy/logs/*.log"
