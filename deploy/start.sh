#!/bin/bash
# 兼容某些环境下 pipefail 不可用（或脚本带 CRLF 导致 pipefail\r 解析失败）
set -eu
# shellcheck disable=SC3040
if [ -n "${BASH_VERSION:-}" ]; then
  set -o pipefail 2>/dev/null || true
fi

# 项目根目录
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"

# Python venv（推理/业务都依赖 venv；如果不激活，python/uvicorn 可能来自 conda/system 导致启动失败）
# 允许通过环境变量 VENV_DIR 显式指定；否则自动探测常见路径。
PYTHON_BIN="python"
if [ -z "${VENV_DIR:-}" ]; then
  for cand in "${BASE_DIR}/.venv" "${BASE_DIR}/../.venv" "/root/autodl-tmp/.venv" "${HOME:-/root}/autodl-tmp/.venv"; do
    if [ -f "${cand}/bin/python" ]; then
      VENV_DIR="${cand}"
      break
    fi
  done
fi

if [ -n "${VENV_DIR:-}" ] && [ -f "${VENV_DIR}/bin/activate" ]; then
  # shellcheck disable=SC1090
  source "${VENV_DIR}/bin/activate"
  PYTHON_BIN="${VENV_DIR}/bin/python"
  echo "[start] 已激活虚拟环境: ${VENV_DIR}"
else
  echo "[start] 警告：未找到虚拟环境（可设置 VENV_DIR=/path/to/.venv），将使用当前 python：$(command -v python || echo python)"
fi

echo "[start] 使用 Python: $(${PYTHON_BIN} -c 'import sys; print(sys.executable)' 2>/dev/null || echo ${PYTHON_BIN})"

# 默认前端打包路径，可通过环境变量覆盖
FRONTEND_ROOT="${FRONTEND_ROOT:-${BASE_DIR}/frontend/dist}"

# 日志目录
mkdir -p "${BASE_DIR}/deploy/logs"
PID_PATH="${BASE_DIR}/deploy/logs/nginx.pid"

echo "[start] 使用前端目录: ${FRONTEND_ROOT}"

# 1) 前端构建（若 npm 来自 nvm，需要在非交互脚本里手动加载 nvm）
# 如需跳过前端构建：export SKIP_FRONTEND_BUILD=1
if [ "${SKIP_FRONTEND_BUILD:-0}" = "1" ]; then
  echo "[start] SKIP_FRONTEND_BUILD=1，跳过前端构建。"
else
  if ! command -v npm >/dev/null 2>&1; then
    # 尝试加载 nvm（nvm 安装时默认写入 ~/.bashrc，但脚本不会自动 source）
    export NVM_DIR="${NVM_DIR:-${HOME:-/root}/.nvm}"
    if [ -s "${NVM_DIR}/nvm.sh" ]; then
      # shellcheck disable=SC1090
      . "${NVM_DIR}/nvm.sh"
      nvm use --lts >/dev/null 2>&1 || true
    fi
  fi

  if ! command -v npm >/dev/null 2>&1; then
    echo "[start] 未检测到 npm（可能是 nvm 未加载或未安装 Node.js），跳过前端构建。NVM_DIR=${NVM_DIR:-unset}"
  else
    echo "[start] 开始前端构建 (npm install & npm run build)..."
    # 清理旧的 dist 以防万一
    rm -rf "$FRONTEND_ROOT"
  fi
fi

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

if [ "${SKIP_FRONTEND_BUILD:-0}" != "1" ] && command -v npm >/dev/null 2>&1; then
  (cd frontend && npm install && npm run build)
fi

# 2) 生成 Nginx 配置并重载
echo "[start] 生成 Nginx 配置..."
export FRONTEND_ROOT
export MIME_TYPES_PATH="${BASE_DIR}/deploy/mime.types"
#如果是MacOS 可能需要 envsubst (gettext)
envsubst '$FRONTEND_ROOT $MIME_TYPES_PATH' < "${BASE_DIR}/deploy/nginx.conf" > "${BASE_DIR}/deploy/nginx.generated.conf"

echo "[start] 启动/重载 Nginx..."
nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;" -s reload 2>/dev/null || \
nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;"

# 3) 启动 FastAPI 推理服务
echo "[start] 启动 FastAPI 推理服务 (8000)..."
nohup "${PYTHON_BIN}" -m uvicorn backend_inference.main:app --host 0.0.0.0 --port 8000 \
  > "${BASE_DIR}/deploy/logs/inference.log" 2>&1 &

# 4) 启动 Flask 业务服务
echo "[start] 启动 Flask 业务服务 (5001)..."
nohup "${PYTHON_BIN}" backend_business/app.py \
  > "${BASE_DIR}/deploy/logs/business.log" 2>&1 &

echo "[start] 全部服务已尝试启动。Nginx 监听 8008，Flask 5001，FastAPI 8000。"
echo "[start] 查看日志: tail -f deploy/logs/*.log"
