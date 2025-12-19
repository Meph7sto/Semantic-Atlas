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

# 1) 始终执行前端构建，确保代码更新生效
echo "[start] 开始前端构建 (npm install & npm run build)..."
# 清理旧的 dist 以防万一
rm -rf "$FRONTEND_ROOT"

# 为了防止服务器缺失配置文件，在此处自动生成
echo "Generating tailwind.config.js..."
cat > "${BASE_DIR}/frontend/tailwind.config.js" <<EOF
/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./index.html",
    "./src/**/*.{vue,js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {},
  },
  plugins: [],
}
EOF

echo "Generating postcss.config.js..."
cat > "${BASE_DIR}/frontend/postcss.config.js" <<EOF
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
EOF

(cd frontend && npm install && npm run build)

# 2) 生成 Nginx 配置并重载
echo "[start] 生成 Nginx 配置..."
export FRONTEND_ROOT
export MIME_TYPES_PATH="${BASE_DIR}/deploy/mime.types"
NGINX_CONFIG_READY=1
#如果是MacOS 可能需要 envsubst (gettext)
if command -v envsubst >/dev/null 2>&1; then
  envsubst '$FRONTEND_ROOT $MIME_TYPES_PATH' < "${BASE_DIR}/deploy/nginx_linux.conf" > "${BASE_DIR}/deploy/nginx.generated.conf"
else
  # fallback: only replace known placeholders to avoid touching nginx variables like $uri
  python - <<'PY'
import os

src = os.path.join(os.environ["BASE_DIR"], "deploy", "nginx_linux.conf")
dst = os.path.join(os.environ["BASE_DIR"], "deploy", "nginx.generated.conf")
with open(src, "r", encoding="utf-8") as f:
    data = f.read()
data = data.replace("${FRONTEND_ROOT}", os.environ.get("FRONTEND_ROOT", ""))
data = data.replace("${MIME_TYPES_PATH}", os.environ.get("MIME_TYPES_PATH", ""))
with open(dst, "w", encoding="utf-8") as f:
    f.write(data)
PY
fi

if command -v nginx >/dev/null 2>&1; then
  echo "[start] 启动/重载 Nginx..."
  nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;" -s reload 2>/dev/null || \
  nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;"
else
  echo "[start] 未检测到 nginx，跳过反向代理启动。"
fi

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
