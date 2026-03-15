#!/bin/bash
set -euo pipefail

# Base paths
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PID_FILE="${BASE_DIR}/deploy/logs/nginx.pid"

# 递归停止进程树（停止父进程及其所有子进程）
stop_process_tree() {
  local pid="$1"
  local label="${2:-process}"
  if [[ -z "$pid" ]] || [[ "$pid" -le 0 ]]; then
    return
  fi

  # 先停止所有子进程
  if command -v pgrep >/dev/null 2>&1; then
    local children
    children=$(pgrep -P "$pid" 2>/dev/null || true)
    for child in $children; do
      stop_process_tree "$child" "$label"
    done
  fi

  # 停止父进程
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
}

echo "[stop] 尝试停止 Nginx..."
nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;" -s stop 2>/dev/null || true
if [ -f "${PID_FILE}" ]; then
  PID=$(cat "${PID_FILE}")
  stop_process_tree "$PID" "nginx"
  rm -f "${PID_FILE}"
fi

# 通过进程名匹配 Nginx，直接杀掉 master 进程避免 worker 被不断重启
if command -v pgrep >/dev/null 2>&1; then
  # 优先停止 master 进程
  for pid in $(pgrep -f "nginx: master process" 2>/dev/null || true); do
    if [[ -n "$pid" ]] && [[ "$pid" -gt 0 ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  # 停止剩余的 nginx 进程（如 worker）
  for pid in $(pgrep -f "nginx" 2>/dev/null || true); do
    if [[ -n "$pid" ]] && [[ "$pid" -gt 0 ]]; then
      kill "$pid" 2>/dev/null || true
    fi
  done
fi

if command -v pgrep >/dev/null 2>&1; then
  sleep 0.5
  if pgrep -x "nginx" >/dev/null 2>&1; then
    echo "[warning] Nginx 停止失败，仍有残留进程存在。"
  else
    echo "[success] Nginx 停止成功。"
  fi
fi

echo "[stop] 结束占用端口的进程: 8000 (FastAPI Inference), 5002 (FastAPI Business), 8008 (Nginx), 5173 (Vite Dev)"
for port in 8000 5002 8008 5173; do
  if command -v lsof >/dev/null 2>&1; then
    PIDS=$(lsof -ti :"${port}" 2>/dev/null || true)
    if [[ -n "${PIDS}" ]]; then
      for pid in $PIDS; do
        echo " - port ${port}: PID ${pid} -> stopping"
        stop_process_tree "$pid" "port $port"
      done
    fi
  elif command -v ss >/dev/null 2>&1; then
    PIDS=$(ss -tulnH "sport = :${port}" 2>/dev/null | awk '{print $5}' | cut -d: -f2 || true)
    if [[ -n "${PIDS}" ]]; then
      for pid in $PIDS; do
        echo " - port ${port}: PID ${pid} -> stopping"
        stop_process_tree "$pid" "port $port"
      done
    fi
  fi
done

echo "[stop] 检查 Node/Vite 进程..."
if command -v pgrep >/dev/null 2>&1; then
  for pid in $(pgrep -f "vite" 2>/dev/null || true); do
    if [[ -n "$pid" ]]; then
      echo " - node PID ${pid} (vite) -> stopping"
      stop_process_tree "$pid" "node"
    fi
  done
fi

# 匹配并停止 Python 进程（通过命令行参数）
echo "[stop] 检查 Python 后端进程..."
if command -v pgrep >/dev/null 2>&1; then
  # 匹配 backend_inference
  for pid in $(pgrep -f "backend_inference" 2>/dev/null || true); do
    if [[ -n "$pid" ]]; then
      echo " - python PID ${pid} (backend_inference) -> stopping"
      stop_process_tree "$pid" "python"
    fi
  done

  # 匹配 backend_business/main.py
  for pid in $(pgrep -f "backend_business[/\\\\]main.py" 2>/dev/null || true); do
    if [[ -n "$pid" ]]; then
      echo " - python PID ${pid} (backend_business/main.py) -> stopping"
      stop_process_tree "$pid" "python"
    fi
  done

  # 匹配 uvicorn backend_business.main
  for pid in $(pgrep -f "uvicorn.*backend_business.main" 2>/dev/null || true); do
    if [[ -n "$pid" ]]; then
      echo " - python PID ${pid} (uvicorn backend_business.main) -> stopping"
      stop_process_tree "$pid" "python"
    fi
  done
fi

# 停止 FRP 客户端
echo "[stop] 检查 FRP 客户端..."
FRP_PID_FILE="${BASE_DIR}/deploy/logs/frpc.pid"
if [[ -f "$FRP_PID_FILE" ]]; then
  FRP_PID=$(cat "$FRP_PID_FILE")
  if [[ -n "$FRP_PID" ]]; then
    echo " - frpc PID ${FRP_PID} -> stopping"
    stop_process_tree "$FRP_PID" "frpc"
    rm -f "$FRP_PID_FILE"
  fi
fi

# 通过进程名匹配 frpc
if command -v pgrep >/dev/null 2>&1; then
  for pid in $(pgrep -f "frpc" 2>/dev/null || true); do
    if [[ -n "$pid" ]]; then
      echo " - frpc PID ${pid} -> stopping"
      stop_process_tree "$pid" "frpc"
    fi
  done
fi

echo "[stop] 完成。"
