#!/bin/bash
set -eu
# shellcheck disable=SC3040
if [ -n "${BASH_VERSION:-}" ]; then
  set -o pipefail 2>/dev/null || true
fi

# Base paths
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${BASE_DIR}/deploy/logs/nginx.pid"

echo "[stop] 尝试停止 Nginx..."
nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;" -s stop 2>/dev/null || true
if [ -f "${PID_FILE}" ]; then
  PID=$(cat "${PID_FILE}")
  kill "${PID}" 2>/dev/null || true
  rm -f "${PID_FILE}"
fi

echo "[stop] 结束占用端口的进程: 8000 (FastAPI), 5001 (Flask), 8008 (Nginx)"
for port in 8000 5001 8008; do
  PIDS=$(lsof -ti :"${port}" || true)
  if [ -n "${PIDS}" ]; then
    echo " - port ${port}: ${PIDS}"
    kill -9 ${PIDS} 2>/dev/null || true
  fi
done

echo "[stop] 完成。"
