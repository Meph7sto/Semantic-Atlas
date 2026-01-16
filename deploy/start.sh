#!/bin/bash
set -euo pipefail

# 项目根目录
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"

MODE=""
PROVIDER=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    -m|--mode)
      if [[ -z "${2:-}" ]]; then
        echo "[start] Missing value for --mode"
        exit 1
      fi
      MODE="$2"
      shift 2
      ;;
    -p|--provider)
      if [[ -z "${2:-}" ]]; then
        echo "[start] Missing value for --provider"
        exit 1
      fi
      PROVIDER="$2"
      shift 2
      ;;
    *)
      if [[ -z "$MODE" ]]; then
        MODE="$1"
      elif [[ -z "$PROVIDER" ]]; then
        PROVIDER="$1"
      else
        echo "[start] Unknown argument: $1"
        exit 1
      fi
      shift
      ;;
  esac
done

if [[ -z "$MODE" ]]; then
  echo "请选择启动模式: 1=all(前端构建+nginx+全部后端) 2=backend(两个后端) 3=inference 4=business 5=frontend"
  read -r -p "输入编号或模式名 (默认 all): " choice
  case "$choice" in
    2|backend) MODE="backend" ;;
    3|inference) MODE="inference" ;;
    4|business) MODE="business" ;;
    5|frontend) MODE="frontend" ;;
    ""|1|all) MODE="all" ;;
    *) MODE="all" ;;
  esac
fi

if [[ -z "$PROVIDER" ]]; then
  default_provider="${MODEL_PROVIDER:-local}"
  echo "请选择模型模式: 1=local(本地模型) 2=chutes(API) 3=deepseek(API占位)"
  read -r -p "输入编号或模式名 (默认 ${default_provider}): " choice
  case "$choice" in
    2|chutes) PROVIDER="chutes" ;;
    3|deepseek) PROVIDER="deepseek" ;;
    1|local|"") PROVIDER="${default_provider}" ;;
    *) PROVIDER="${default_provider}" ;;
  esac
fi

export MODEL_PROVIDER="$PROVIDER"

if [[ "$PROVIDER" == "chutes" && -z "${CHUTES_API_TOKEN:-}" && -z "${CHUTES_API_KEY:-}" ]]; then
  echo "检测到使用 chutes 模式，但未设置 CHUTES_API_TOKEN。"
  read -r -p "请输入 Chutes API Token（留空则跳过）: " token
  if [[ -n "$token" ]]; then
    export CHUTES_API_TOKEN="$token"
  fi
fi

do_frontend=0
do_nginx=0
do_inference=0
do_business=0

case "$MODE" in
  all)
    do_frontend=1
    do_nginx=1
    do_inference=1
    do_business=1
    ;;
  backend)
    do_inference=1
    do_business=1
    ;;
  inference)
    do_inference=1
    ;;
  business)
    do_business=1
    ;;
  frontend)
    do_frontend=1
    do_nginx=1
    ;;
  *)
    MODE="all"
    do_frontend=1
    do_nginx=1
    do_inference=1
    do_business=1
    ;;
esac

# 默认前端打包路径，可通过环境变量覆盖
FRONTEND_ROOT="${FRONTEND_ROOT:-${BASE_DIR}/frontend/dist}"

# 日志目录
mkdir -p "${BASE_DIR}/deploy/logs"
PID_PATH="${BASE_DIR}/deploy/logs/nginx.pid"

echo "[start] Mode: ${MODE}; Model provider: ${PROVIDER}"
if [[ "$do_frontend" -eq 1 ]]; then
  echo "[start] 使用前端目录: ${FRONTEND_ROOT}"
fi

if [[ "$do_frontend" -eq 1 ]]; then
  # 1) 执行前端构建，确保代码更新生效
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

  # 2) 生成 Nginx 配置
  echo "[start] 生成 Nginx 配置..."
  export FRONTEND_ROOT
  export MIME_TYPES_PATH="${BASE_DIR}/deploy/mime.types"
  export BASE_DIR
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
fi

if [[ "$do_nginx" -eq 1 ]]; then
  if command -v nginx >/dev/null 2>&1; then
    echo "[start] 启动/重载 Nginx..."
    nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;" -s reload 2>/dev/null || \
    nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;"
  else
    echo "[start] 未检测到 nginx，跳过反向代理启动。"
  fi
fi

if [[ "$do_inference" -eq 1 ]]; then
  # 3) 启动 FastAPI 推理服务
  echo "[start] 启动 FastAPI 推理服务 (8000)..."
  nohup uvicorn backend_inference.main:app --host 0.0.0.0 --port 8000 \
    > "${BASE_DIR}/deploy/logs/inference.log" 2>&1 &
fi

if [[ "$do_business" -eq 1 ]]; then
  # 4) 启动 Flask 业务服务
  echo "[start] 启动 Flask 业务服务 (5001)..."
  nohup python backend_business/app.py \
    > "${BASE_DIR}/deploy/logs/business.log" 2>&1 &
fi

echo "[start] Done. Mode=${MODE}; Model provider=${PROVIDER}; Nginx 8008 (if enabled), FastAPI 8000 (if enabled), Flask 5001 (if enabled)."
echo "[start] Logs located in ${BASE_DIR}/deploy/logs"
