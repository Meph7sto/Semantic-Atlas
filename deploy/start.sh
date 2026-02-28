#!/bin/bash
set -euo pipefail

# 项目根目录（脚本位于 deploy/ 下）
BASE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$BASE_DIR"

MODE=""
PROVIDER=""
ENTRY=""
BUSINESS_BACKEND=""
ENABLE_FASTAPI_BUSINESS=""
FRP_MODE=""
FRP_SERVER_ADDR=""
FRP_TOKEN=""

# 解析命令行参数
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
    -e|--entry)
      if [[ -z "${2:-}" ]]; then
        echo "[start] Missing value for --entry"
        exit 1
      fi
      ENTRY="$2"
      shift 2
      ;;
    --enable-fastapi-business)
      ENABLE_FASTAPI_BUSINESS=1
      shift
      ;;
    --frp|-f)
      FRP_MODE=1
      shift
      ;;
    *)
      if [[ -z "$MODE" ]]; then
        MODE="$1"
      elif [[ -z "$PROVIDER" ]]; then
        PROVIDER="$1"
      elif [[ -z "$ENTRY" ]]; then
        ENTRY="$1"
      else
        echo "[start] Unknown argument: $1"
        exit 1
      fi
      shift
      ;;
  esac
done

# 网络模式选择（本地运行 vs frp 内网穿透）
if [[ -z "$FRP_MODE" ]]; then
  echo "请选择网络模式: 1=本地运行(默认) 2=开启frp内网穿透"
  read -r -p "输入编号 (默认 1): " net_choice
  if [[ "$net_choice" == "2" ]]; then
    FRP_MODE=1
  fi
fi

# 如果启用了 frp 模式，收集配置信息
if [[ "$FRP_MODE" == "1" ]]; then
  echo "[start] FRP 模式已启用"
  if [[ -z "$FRP_SERVER_ADDR" ]]; then
    read -r -p "请输入 frp 服务器 IP 地址（留空则跳过）: " FRP_SERVER_ADDR
    if [[ -n "$FRP_SERVER_ADDR" ]]; then
      export FRP_SERVER_ADDR
      if ! grep -q "FRP_SERVER_ADDR=" "$ENV_FILE" 2>/dev/null; then
        echo "FRP_SERVER_ADDR=\"$FRP_SERVER_ADDR\"" >> "$ENV_FILE"
        echo "[start] FRP Server Address saved to .env"
      fi
    fi
  fi
  if [[ -z "$FRP_TOKEN" ]]; then
    read -r -p "请输入 frp 服务器密码 (token)（留空则跳过）: " FRP_TOKEN
    if [[ -n "$FRP_TOKEN" ]]; then
      export FRP_TOKEN
      if ! grep -q "FRP_TOKEN=" "$ENV_FILE" 2>/dev/null; then
        echo "FRP_TOKEN=\"$FRP_TOKEN\"" >> "$ENV_FILE"
        echo "[start] FRP Token saved to .env"
      fi
    fi
  fi
  if [[ -z "$FRP_SERVER_ADDR" || -z "$FRP_TOKEN" ]]; then
    echo "[start] 错误：FRP 模式需要提供服务器 IP 和密码"
    exit 1
  fi
  export FRP_MODE FRP_SERVER_ADDR FRP_TOKEN
fi

# 启动模式选择
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

# 模型提供方选择
if [[ -z "$PROVIDER" ]]; then
  default_provider="${MODEL_PROVIDER:-deepseek}"
  echo "请选择模型模式: 1=local(本地模型) 2=chutes(API) 3=deepseek"
  read -r -p "输入编号或模式名 (默认 ${default_provider}): " choice
  case "$choice" in
    1|local) PROVIDER="local" ;;
    2|chutes) PROVIDER="chutes" ;;
    3|deepseek) PROVIDER="deepseek" ;;
    "") PROVIDER="${default_provider}" ;;
    *) PROVIDER="${default_provider}" ;;
  esac
fi

export MODEL_PROVIDER="$PROVIDER"

# 是否加载模型选择 (默认不加载)
echo "是否加载本地模型权重? 1=no(跳过, 启动快) 2=yes(加载, 需GPU/大内存)"
read -r -p "输入编号 (默认 1/no): " load_choice
if [[ "$load_choice" == "2" || "$load_choice" == "yes" ]]; then
  export SKIP_MODEL_LOAD="false"
  echo "[start] Model loading enabled."
else
  export SKIP_MODEL_LOAD="true"
  echo "[start] Model loading skipped (default)."
fi

# 前端入口选择
if [[ -z "$ENTRY" ]]; then
  default_entry="${FRONTEND_ENTRY:-all}"
  echo "请选择前端入口: 1=main(正式页面) 2=alpha(测试页面) 3=all(全部模式+引导页)"
  read -r -p "输入编号或模式名 (默认 ${default_entry}): " choice
  case "$choice" in
    1|main) ENTRY="main" ;;
    2|alpha) ENTRY="alpha" ;;
    3|all) ENTRY="all" ;;
    "") ENTRY="${default_entry}" ;;
    *) ENTRY="${default_entry}" ;;
  esac
fi

export FRONTEND_ENTRY="$ENTRY"

# 是否启动 FastAPI 业务后端
if [[ "$ENABLE_FASTAPI_BUSINESS" != "1" ]]; then
  echo "是否启动 FastAPI 业务后端 (/api/v2/)? 1=yes(默认, 与Flask并行) 2=no"
  read -r -p "输入编号 (默认 1/yes): " choice
  if [[ "$choice" == "2" || "$choice" == "no" ]]; then
    ENABLE_FASTAPI_BUSINESS=0
  else
    ENABLE_FASTAPI_BUSINESS=1
    echo "[start] FastAPI business backend will be enabled."
  fi
fi

# 尝试加载 .env 文件 (用于持久化 API Key)
ENV_FILE="${BASE_DIR}/.env"
if [[ -f "$ENV_FILE" ]]; then
  echo "[start] Loading secrets from .env..."
  set -a
  source "$ENV_FILE"
  set +a
fi

# Chutes API Token 检查
if [[ "$PROVIDER" == "chutes" && -z "${CHUTES_API_TOKEN:-}" ]]; then
  echo "检测到使用 chutes 模式，但未设置 CHUTES_API_TOKEN。"
  read -r -p "请输入 Chutes API Token（留空则跳过）: " token
  if [[ -n "$token" ]]; then
    export CHUTES_API_TOKEN="$token"
    # Persist to .env
    if ! grep -q "CHUTES_API_TOKEN=" "$ENV_FILE" 2>/dev/null; then
      echo "CHUTES_API_TOKEN=\"$token\"" >> "$ENV_FILE"
      echo "[start] Chutes Token saved to .env"
    fi
  fi
fi

# DeepSeek API Key 检查
if [[ "$PROVIDER" == "deepseek" && -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "检测到使用 deepseek 模式，但未设置 DEEPSEEK_API_KEY。"
  read -r -p "请输入 DeepSeek API Key（留空则跳过）: " key
  if [[ -n "$key" ]]; then
    export DEEPSEEK_API_KEY="$key"
    # Persist to .env
    if ! grep -q "DEEPSEEK_API_KEY=" "$ENV_FILE" 2>/dev/null; then
      echo "DEEPSEEK_API_KEY=\"$key\"" >> "$ENV_FILE"
      echo "[start] DeepSeek Key saved to .env"
    fi
  else
    echo "未输入 Key，后续调用将失败。"
  fi
fi

# 设置 Hugging Face 镜像地址（解决国内无法连接问题）
export HF_ENDPOINT=https://hf-mirror.com

# Conda env setup for Python services
CONDA_ENV="semantic-Atlas"
CONDA_PYTHON_VERSION="3.12"

# Initialize conda in current shell (not subshell)
conda_exe="${CONDA_EXE:-}"
if [[ -z "$conda_exe" ]]; then
  conda_exe="$(command -v conda 2>/dev/null || true)"
fi

if [[ -n "$conda_exe" ]]; then
  conda_base="$(dirname "$(dirname "$conda_exe")")"
  if [[ -f "${conda_base}/etc/profile.d/conda.sh" ]]; then
    source "${conda_base}/etc/profile.d/conda.sh"
  fi

  # Check if env exists by looking for the path in conda env list
  env_exists=0
  if conda env list 2>/dev/null | grep -q "^${CONDA_ENV} "; then
    env_exists=1
  fi

  if [[ "$env_exists" -eq 0 ]]; then
    echo "[start] Conda env '$CONDA_ENV' not found. Creating..."
    conda create -n "$CONDA_ENV" python="$CONDA_PYTHON_VERSION" -y
  fi

  echo "[start] Activating conda env '$CONDA_ENV'..."
  conda activate "$CONDA_ENV"
else
  echo "[start] Conda not found; skipping conda activation."
fi

# PostgreSQL helper functions
escape_postgres_literal() {
  local value="$1"
  echo "${value//\'/\'\'}"
}

invoke_postgres_sql() {
  local docker_exe="$1"
  local container_name="$2"
  local sql="$3"
  local database="$4"
  local password="$5"
  shift 5
  local users=("$@")

  local last_output=""
  for user in "${users[@]}"; do
    [[ -z "$user" ]] && continue
    last_output=$("$docker_exe" exec "$container_name" psql -v ON_ERROR_STOP=1 -U "$user" -d "$database" -c "$sql" 2>&1) && return 0

    if [[ -n "$password" ]]; then
      last_output=$("$docker_exe" exec -e "PGPASSWORD=$password" "$container_name" psql -v ON_ERROR_STOP=1 -U "$user" -d "$database" -c "$sql" 2>&1) && return 0
    fi
  done

  echo "$last_output"
  return 1
}

ensure_postgres_access() {
  local docker_exe="$1"
  local container_name="$2"
  local db_user="$3"
  local db_password="$4"
  local db_name="$5"

  local db_user_esc
  db_user_esc="$(escape_postgres_literal "$db_user")"
  local db_password_esc
  db_password_esc="$(escape_postgres_literal "$db_password")"
  local db_name_esc
  db_name_esc="$(escape_postgres_literal "$db_name")"

  local sql
  sql=$(cat <<EOF
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${db_user_esc}') THEN
    EXECUTE format('CREATE ROLE %I LOGIN PASSWORD %L', '${db_user_esc}', '${db_password_esc}');
  ELSE
    EXECUTE format('ALTER ROLE %I WITH LOGIN PASSWORD %L', '${db_user_esc}', '${db_password_esc}');
  END IF;

  IF NOT EXISTS (SELECT 1 FROM pg_database WHERE datname = '${db_name_esc}') THEN
    EXECUTE format('CREATE DATABASE %I OWNER %I', '${db_name_esc}', '${db_user_esc}');
  END IF;
END
\$\$;
EOF
)

  local admin_users=("postgres" "$db_user")
  local unique_users=()
  for u in "${admin_users[@]}"; do
    [[ -z "$u" ]] && continue
    local found=0
    for uu in "${unique_users[@]:-}"; do
      [[ "$u" == "$uu" ]] && found=1 && break
    done
    [[ "$found" -eq 0 ]] && unique_users+=("$u")
  done

  for i in {1..8}; do
    if invoke_postgres_sql "$docker_exe" "$container_name" "$sql" "postgres" "$db_password" "${unique_users[@]}" >/dev/null 2>&1; then
      echo "[start] PostgreSQL role/database ensured."
      return 0
    fi
    echo "[start] PostgreSQL not ready, retry $i/8..."
    sleep 2
  done

  echo "[start] Failed to ensure PostgreSQL user/database in container."
  return 1
}

test_local_port_open() {
  local port="$1"
  if command -v nc >/dev/null 2>&1; then
    nc -z 127.0.0.1 "$port" 2>/dev/null && return 0
  elif command -v ss >/dev/null 2>&1; then
    ss -tuln 2>/dev/null | grep -q ":${port} " && return 0
  elif command -v netstat >/dev/null 2>&1; then
    netstat -tuln 2>/dev/null | grep -q ":${port} " && return 0
  fi
  return 1
}

test_postgres_port_conflict() {
  local port="$1"
  if ! test_local_port_open "$port"; then
    return 1
  fi
  # Port is open, assume conflict
  return 0
}

get_container_host_port() {
  local docker_exe="$1"
  local container_name="$2"
  local container_port="$3"

  local format='{{(index (index .NetworkSettings.Ports "'"$container_port"'") 0).HostPort}}'
  local host_port
  host_port=$("$docker_exe" inspect -f "$format" "$container_name" 2>/dev/null) || return 1
  if [[ -n "$host_port" && "$host_port" != "<no value>" ]]; then
    echo "$host_port"
    return 0
  fi
  return 1
}

select_postgres_port() {
  local default_port="$1"
  local docker_exe="${2:-}"
  local container_name="${3:-}"

  if [[ -n "$docker_exe" && -n "$container_name" ]]; then
    local existing_port
    existing_port=$(get_container_host_port "$docker_exe" "$container_name" "5432/tcp" 2>/dev/null) || true
    if [[ -n "$existing_port" ]]; then
      echo "$existing_port"
      return
    fi
  fi

  if ! test_local_port_open "$default_port"; then
    echo "$default_port"
    return
  fi

  for p in $(seq $((default_port + 1)) $((default_port + 10))); do
    if ! test_local_port_open "$p"; then
      echo "$p"
      return
    fi
  done

  echo "$default_port"
}

# 日志目录与 PID 路径
LOGS_DIR="${BASE_DIR}/deploy/logs"
mkdir -p "$LOGS_DIR"

# Start PostgreSQL (if business backend enabled)
if [[ "$do_business" -eq 1 ]]; then
  : "${POSTGRES_HOST:=127.0.0.1}"
  [[ "$POSTGRES_HOST" == "localhost" || "$POSTGRES_HOST" == "::1" ]] && POSTGRES_HOST="127.0.0.1"
  port_explicit="${POSTGRES_PORT:+1}"
  : "${POSTGRES_PORT:=5433}"
  : "${POSTGRES_PORT_LOCK:=1}"
  : "${POSTGRES_USER:=semantic}"
  : "${POSTGRES_PASSWORD:=semantic_dev}"
  : "${POSTGRES_DB:=semantic_atlas}"
  export POSTGRES_HOST POSTGRES_PORT POSTGRES_PORT_LOCK POSTGRES_USER POSTGRES_PASSWORD POSTGRES_DB

  # 检测 Docker 是否可用（包括 daemon 是否运行）
  docker_available=0
  if command -v docker >/dev/null 2>&1; then
    if docker info >/dev/null 2>&1; then
      docker_available=1
    else
      echo "[start] Docker command found but daemon is not running (possibly in container environment)."
    fi
  fi

  if [[ "$docker_available" -eq 1 ]]; then
    # ========== Docker 模式 ==========
    echo "[start] Docker daemon is available, using Docker Compose for PostgreSQL..."
    
    compose_file="${BASE_DIR}/docker-compose.yml"
    if [[ -f "$compose_file" ]]; then
      docker_exe="$(command -v docker)"
      docker_compose_exe=""
      if command -v docker-compose >/dev/null 2>&1; then
        docker_compose_exe="$(command -v docker-compose)"
      fi

      port_locked=0
      [[ "$POSTGRES_PORT_LOCK" == "1" || "$POSTGRES_PORT_LOCK" == "true" || "$POSTGRES_PORT_LOCK" == "True" ]] && port_locked=1

      needs_override=0
      if [[ "$port_locked" -eq 0 ]]; then
        if [[ -z "$port_explicit" ]]; then
          needs_override=1
        elif [[ "$POSTGRES_PORT" == "5432" ]] && test_postgres_port_conflict "$POSTGRES_PORT"; then
          needs_override=1
        fi
      fi

      if [[ "$needs_override" -eq 1 ]]; then
        selected_port=$(select_postgres_port "$POSTGRES_PORT" "$docker_exe" "semantic-atlas-postgres")
        if [[ "$selected_port" != "$POSTGRES_PORT" ]]; then
          echo "[start] Port $POSTGRES_PORT is in use. Switching PostgreSQL host port to $selected_port."
          POSTGRES_PORT="$selected_port"
          export POSTGRES_PORT
        fi
      fi

      force_recreate=0
      existing_container=$("$docker_exe" ps -a -q -f "name=semantic-atlas-postgres" 2>/dev/null) || true
      if [[ -n "$existing_container" ]]; then
        published_port=$(get_container_host_port "$docker_exe" "semantic-atlas-postgres" "5432/tcp" 2>/dev/null) || true
        if [[ -z "$published_port" ]]; then
          echo "[start] PostgreSQL container has no published host port. Forcing recreate."
          force_recreate=1
        elif [[ "$published_port" != "$POSTGRES_PORT" ]]; then
          echo "[start] PostgreSQL container is bound to host port $published_port, expected $POSTGRES_PORT. Forcing recreate."
          force_recreate=1
        fi
      fi

      echo "[start] Starting PostgreSQL via docker compose..."
      compose_args=("compose" "-f" "$compose_file" "up" "-d")
      [[ "$force_recreate" -eq 1 ]] && compose_args+=("--force-recreate")
      compose_args+=("postgres" "adminer")
      if ! "$docker_exe" "${compose_args[@]}"; then
        echo "[start] Failed to start PostgreSQL via docker compose."
      else
        container_id=$("$docker_exe" ps -q -f "name=semantic-atlas-postgres" 2>/dev/null) || true
        if [[ -n "$container_id" ]]; then
          ensure_postgres_access "$docker_exe" "semantic-atlas-postgres" "$POSTGRES_USER" "$POSTGRES_PASSWORD" "$POSTGRES_DB" || true
        fi
      fi
    else
      echo "[start] docker-compose.yml not found; skipping Docker PostgreSQL startup."
    fi
  else
    # ========== 原生 PostgreSQL 模式（适用于 autodl 等容器环境）==========
    echo "[start] Docker not available, falling back to native PostgreSQL..."
    
    # 安装 PostgreSQL（如果未安装）
    if ! command -v psql >/dev/null 2>&1 || ! command -v lsof >/dev/null 2>&1; then
      echo "[start] Necessary tools (PostgreSQL/lsof) not found. Installing..."
      if command -v apt-get >/dev/null 2>&1; then
        apt-get update
        apt-get install -y postgresql postgresql-contrib lsof
      elif command -v yum >/dev/null 2>&1; then
        yum install -y postgresql-server postgresql-contrib lsof
        postgresql-setup --initdb || true
      elif command -v dnf >/dev/null 2>&1; then
        dnf install -y postgresql-server postgresql-contrib lsof
        postgresql-setup --initdb || true
      fi
      echo "[start] Tools installed."
    fi

    # 获取 PostgreSQL 版本和集群信息
    pg_version="14"
    if command -v pg_lsclusters >/dev/null 2>&1; then
      pg_cluster_info=$(pg_lsclusters -h 2>/dev/null | head -n1) || true
      if [[ -n "$pg_cluster_info" ]]; then
        pg_version=$(echo "$pg_cluster_info" | awk '{print $1}')
        pg_cluster=$(echo "$pg_cluster_info" | awk '{print $2}')
      fi
    fi

    # 确定数据目录和二进制路径
    pg_data="/var/lib/postgresql/${pg_version}/${pg_cluster:-main}"
    pg_bin="/usr/lib/postgresql/${pg_version}/bin/pg_ctl"
    
    if [[ ! -d "$pg_data" ]]; then
      # 如果默认路径不对，尝试查找
      for candidate in /var/lib/postgresql/*/main /var/lib/pgsql/data; do
        if [[ -d "$candidate" ]]; then
          pg_data="$candidate"
          # 从路径中提取版本号
          if [[ "$candidate" =~ /postgresql/([0-9.]+)/ ]]; then
            pg_version="${BASH_REMATCH[1]}"
            pg_bin="/usr/lib/postgresql/${pg_version}/bin/pg_ctl"
          fi
          break
        fi
      done
    fi

    # Helper to run commands as postgres user, falling back to su if sudo is missing
    run_as_postgres() {
      if command -v sudo >/dev/null 2>&1; then
        sudo -u postgres "$@"
      else
        # Construct command string for su -c using printf %q for safe quoting
        local cmd_str=""
        for arg in "$@"; do
          cmd_str="$cmd_str $(printf %q "$arg")"
        done
        su - postgres -c "$cmd_str"
      fi
    }

    # 检查 pg_bin 是否存在，不存在则使用通用的
    if [[ ! -f "$pg_bin" ]]; then
      pg_bin=$(command -v pg_ctl || true)
    fi

    # 确保 PostgreSQL 启动环境权限（解决 autodl 等容器环境下的 root 启动问题）
    echo "[start] Preparing PostgreSQL runtime environment..."
    mkdir -p /var/run/postgresql
    chown -R postgres:postgres /var/run/postgresql
    chmod 2775 /var/run/postgresql

    # 在 /tmp 下创建日志，解决 /root 目录权限导致的拒绝访问问题
    PG_TMP_LOG="/tmp/semantic_atlas_postgres.log"
    touch "$PG_TMP_LOG"
    chown postgres:postgres "$PG_TMP_LOG"
    chmod 666 "$PG_TMP_LOG"

    # 启动 PostgreSQL 服务 (优先使用 pg_ctlcluster，适应 Ubuntu 拆分路径)
    echo "[start] Starting PostgreSQL service..."
    if command -v pg_ctlcluster >/dev/null 2>&1 && [[ -n "${pg_version:-}" && -n "${pg_cluster:-}" ]]; then
      echo "[start] Using pg_ctlcluster to start PostgreSQL ${pg_version} ${pg_cluster}..."
      pg_ctlcluster "${pg_version}" "${pg_cluster}" start || true
    elif [[ -n "$pg_bin" && -d "$pg_data" ]]; then
      # 确保数据目录权限正确
      chown -R postgres:postgres "$pg_data" 2>/dev/null || true
      # 切换到 postgres 用户启动，将日志重定向到 /tmp 下的任务文件
      if ! run_as_postgres "$pg_bin" -D "$pg_data" -o "-k /var/run/postgresql" -l "$PG_TMP_LOG" start; then
        echo "[start] pg_ctl failed to start. Log content from ${PG_TMP_LOG}:"
        cat "$PG_TMP_LOG"
      fi
    else
      # 备选：尝试使用服务方式（通常在容器里会由于 policy-rc.d 失败）
      service postgresql start || true
    fi

    # 等待 PostgreSQL 就绪
    echo "[start] Waiting for PostgreSQL to be ready..."
    pg_ready=0
    for i in {1..15}; do
      if run_as_postgres psql -c "SELECT 1" >/dev/null 2>&1; then
        echo "[start] PostgreSQL is ready."
        pg_ready=1
        break
      fi
      echo "[start] PostgreSQL not ready, retry $i/15..."
      sleep 2
    done

    if [[ "$pg_ready" -eq 0 ]]; then
      echo "[start] ERROR: PostgreSQL failed to start. Last log entries from ${PG_TMP_LOG}:"
      # 打印最后几行日志帮助调试
      if [[ -f "$PG_TMP_LOG" ]]; then
        tail -n 20 "$PG_TMP_LOG"
      else
        echo "Log file not found at ${PG_TMP_LOG}"
      fi
    fi

    # 创建用户和数据库
    echo "[start] Ensuring PostgreSQL user and database..."
    # 增加 -h /var/run/postgresql 显式指定 socket 目录
    run_as_postgres psql <<EOSQL || true
DO \$\$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = '${POSTGRES_USER}') THEN
    EXECUTE 'CREATE ROLE ${POSTGRES_USER} LOGIN PASSWORD ' || quote_literal('${POSTGRES_PASSWORD}');
  ELSE
    EXECUTE 'ALTER ROLE ${POSTGRES_USER} WITH LOGIN PASSWORD ' || quote_literal('${POSTGRES_PASSWORD}');
  END IF;
END
\$\$;
EOSQL

    # 检查数据库是否存在，不存在则创建
    db_exists=$(run_as_postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='${POSTGRES_DB}'")
    if [[ "$db_exists" != "1" ]]; then
      echo "[start] Creating database ${POSTGRES_DB}..."
      run_as_postgres psql -c "CREATE DATABASE ${POSTGRES_DB} OWNER ${POSTGRES_USER}" || true
    fi

    # 配置 pg_hba.conf 允许密码认证
    pg_hba_path=""
    for candidate in "/etc/postgresql/${pg_version}/${pg_cluster:-main}/pg_hba.conf" "${pg_data}/pg_hba.conf"; do
      if [[ -f "$candidate" ]]; then
        pg_hba_path="$candidate"
        break
      fi
    done
    
    if [[ -n "$pg_hba_path" ]]; then
      # 检查是否已有 md5 认证规则
      if ! grep -q "host.*${POSTGRES_DB}.*${POSTGRES_USER}.*md5" "$pg_hba_path" 2>/dev/null; then
        echo "[start] Adding password authentication rule to pg_hba.conf..."
        echo "host    ${POSTGRES_DB}    ${POSTGRES_USER}    127.0.0.1/32    md5" >> "$pg_hba_path"
        echo "host    ${POSTGRES_DB}    ${POSTGRES_USER}    ::1/128         md5" >> "$pg_hba_path"
        # 重载配置
        echo "[start] Reloading PostgreSQL configuration..."
        if [[ -n "$pg_bin" && -d "$pg_data" ]]; then
          run_as_postgres "$pg_bin" -D "$pg_data" reload || true
        else
          service postgresql reload || true
        fi
      fi
    fi

    # 更新端口为默认的 5432（原生 PostgreSQL 默认端口）
    POSTGRES_PORT=5432
    export POSTGRES_PORT
    echo "[start] Native PostgreSQL configured on port $POSTGRES_PORT."
  fi
fi

# 前端产物目录，可通过环境变量 FRONTEND_ROOT 覆盖
FRONTEND_ROOT="${FRONTEND_ROOT:-${BASE_DIR}/frontend/dist}"
# envsubst 只读取导出的环境变量，不导出会导致 ${FRONTEND_ROOT} 被替换为空
export FRONTEND_ROOT

# 0) 先执行停止脚本清理环境
stop_script="${BASE_DIR}/deploy/stop_services.sh"
if [[ -f "$stop_script" ]]; then
  echo "[start] Auto-running stop_services.sh to clean environment..."
  bash "$stop_script" || true
fi

echo "[start] Mode: $MODE; Model provider: $PROVIDER"
if [[ "$do_frontend" -eq 1 ]]; then
  echo "[start] Using frontend directory: $FRONTEND_ROOT"
fi

if [[ "$do_frontend" -eq 1 ]]; then
  # 检查并安装 Node.js
  if ! command -v node >/dev/null 2>&1; then
    echo "[start] Node.js not found. Installing..."
    if command -v apt-get >/dev/null 2>&1; then
      # Debian/Ubuntu
      curl -fsSL https://deb.nodesource.com/setup_20.x | bash -
      apt-get install -y nodejs
    elif command -v yum >/dev/null 2>&1; then
      # CentOS/RHEL
      curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
      yum install -y nodejs
    elif command -v dnf >/dev/null 2>&1; then
      # Fedora
      curl -fsSL https://rpm.nodesource.com/setup_20.x | bash -
      dnf install -y nodejs
    else
      echo "[start] Cannot auto-install Node.js. Please install manually."
      exit 1
    fi
    echo "[start] Node.js installed: $(node --version)"
  fi

  # 选择前端包管理器：
  # - 若存在 package-lock.json，优先 npm ci（可复现，避免依赖漂移）
  # - 否则回退到 pnpm
  FRONTEND_PM="pnpm"
  if [[ -f "${BASE_DIR}/frontend/package-lock.json" ]]; then
    FRONTEND_PM="npm"
  fi

  if [[ "$FRONTEND_PM" == "pnpm" ]] && ! command -v pnpm >/dev/null 2>&1; then
    echo "[start] pnpm not found. Installing via npm..."
    npm install -g pnpm
    echo "[start] pnpm installed: $(pnpm --version)"
  fi

  # 1) 前端构建
  echo "[start] Building frontend (${FRONTEND_PM} install + build)..."
  if [[ -d "$FRONTEND_ROOT" ]]; then
    rm -rf "$FRONTEND_ROOT"
  fi

  # 根据入口选择修改路由默认重定向
  ROUTER_PATH="${BASE_DIR}/frontend/src/router/index.js"
  if [[ -f "$ROUTER_PATH" ]]; then
    if [[ "$ENTRY" == "alpha" ]]; then
      sed -i.bak "s|redirect: '/main/login'|redirect: '/alpha/conflict'|g" "$ROUTER_PATH"
      sed -i.bak "s|redirect: '/guide'|redirect: '/alpha/conflict'|g" "$ROUTER_PATH"
      rm -f "${ROUTER_PATH}.bak"
      echo "[start] Frontend entry set to: alpha (测试页面)"
    elif [[ "$ENTRY" == "all" ]]; then
      sed -i.bak "s|redirect: '/main/login'|redirect: '/guide'|g" "$ROUTER_PATH"
      sed -i.bak "s|redirect: '/alpha/conflict'|redirect: '/guide'|g" "$ROUTER_PATH"
      rm -f "${ROUTER_PATH}.bak"
      echo "[start] Frontend entry set to: all (全部模式+引导页)"
    else
      sed -i.bak "s|redirect: '/alpha/conflict'|redirect: '/main/login'|g" "$ROUTER_PATH"
      sed -i.bak "s|redirect: '/guide'|redirect: '/main/login'|g" "$ROUTER_PATH"
      rm -f "${ROUTER_PATH}.bak"
      echo "[start] Frontend entry set to: main (正式页面)"
    fi
  fi

  # 生成前端配置文件（保持与 Windows 脚本一致）
  cat > "${BASE_DIR}/frontend/tailwind.config.js" <<'EOF'
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

  cat > "${BASE_DIR}/frontend/postcss.config.js" <<'EOF'
module.exports = {
  plugins: {
    tailwindcss: {},
    autoprefixer: {},
  },
}
EOF

  # 仅在显式开启时清理依赖目录，默认保留以减少安装波动与耗时
  if [[ "${CLEAN_FRONTEND_DEPS:-0}" == "1" ]]; then
    if [[ -d "${BASE_DIR}/frontend/node_modules" ]]; then
      echo "[start] CLEAN_FRONTEND_DEPS=1 -> cleaning node_modules..."
      rm -rf "${BASE_DIR}/frontend/node_modules"
    fi
  fi

  # 根据 Linux 可用内存动态设置 Node 堆上限，避免固定 4096 在低内存机器上触发 OOM
  mem_total_mb="$(awk '/MemTotal:/ { printf "%d", $2/1024 }' /proc/meminfo 2>/dev/null || echo 2048)"
  mem_limit_mb=""

  # cgroup v2
  if [[ -r /sys/fs/cgroup/memory.max ]]; then
    cgroup_limit="$(cat /sys/fs/cgroup/memory.max 2>/dev/null || true)"
    if [[ -n "$cgroup_limit" && "$cgroup_limit" != "max" ]]; then
      mem_limit_mb="$((cgroup_limit / 1024 / 1024))"
    fi
  fi
  # cgroup v1
  if [[ -z "$mem_limit_mb" && -r /sys/fs/cgroup/memory/memory.limit_in_bytes ]]; then
    cgroup_limit="$(cat /sys/fs/cgroup/memory/memory.limit_in_bytes 2>/dev/null || true)"
    if [[ -n "$cgroup_limit" && "$cgroup_limit" -lt 9223372036854771712 ]]; then
      mem_limit_mb="$((cgroup_limit / 1024 / 1024))"
    fi
  fi

  available_mem_mb="$mem_total_mb"
  if [[ -n "$mem_limit_mb" && "$mem_limit_mb" -gt 0 && "$mem_limit_mb" -lt "$available_mem_mb" ]]; then
    available_mem_mb="$mem_limit_mb"
  fi

  # 某些环境会通过 ulimit -v 限制单进程虚拟内存；若存在，则进一步收紧
  vmem_limit_kb="$(ulimit -v 2>/dev/null || true)"
  vmem_limit_mb=""
  if [[ "$vmem_limit_kb" =~ ^[0-9]+$ && "$vmem_limit_kb" -gt 0 ]]; then
    vmem_limit_mb="$((vmem_limit_kb / 1024))"
    if [[ "$vmem_limit_mb" -lt "$available_mem_mb" ]]; then
      available_mem_mb="$vmem_limit_mb"
    fi
  fi

  node_heap_mb="$((available_mem_mb * 65 / 100))"
  if [[ "$node_heap_mb" -lt 768 ]]; then
    node_heap_mb=768
  fi
  if [[ "$node_heap_mb" -gt 2048 ]]; then
    node_heap_mb=2048
  fi

  node_runtime_opts=""
  node_no_snapshot_supported=0
  node_no_snapshot_env_supported=0
  use_cli_no_snapshot_mode=0

  # ARM64 部分环境会在快照反序列化阶段崩溃，优先关闭 node snapshot
  if [[ "${DISABLE_NODE_SNAPSHOT:-1}" == "1" ]]; then
    if node --no-node-snapshot -e "process.exit(0)" >/dev/null 2>&1; then
      node_no_snapshot_supported=1
    fi
    if NODE_OPTIONS="--no-node-snapshot" node -e "process.exit(0)" >/dev/null 2>&1; then
      node_no_snapshot_env_supported=1
      node_runtime_opts="--no-node-snapshot"
    fi
    # 某些 Node 版本/发行包不允许通过 NODE_OPTIONS 注入该参数，改为命令行直传
    if [[ "$node_no_snapshot_supported" -eq 1 && "$node_no_snapshot_env_supported" -eq 0 ]]; then
      use_cli_no_snapshot_mode=1
    fi
  fi
  build_node_opts="--max-old-space-size=${node_heap_mb}"
  conservative_node_opts="--max-old-space-size=1024"
  if [[ -n "$node_runtime_opts" ]]; then
    build_node_opts="${node_runtime_opts} ${build_node_opts}"
    conservative_node_opts="${node_runtime_opts} ${conservative_node_opts}"
  fi

  run_with_node_options() {
    local opts="$1"
    shift
    if [[ -n "$opts" ]]; then
      NODE_OPTIONS="$opts" "$@"
    else
      "$@"
    fi
  }

  echo "[start] Node runtime: path=$(command -v node), version=$(node --version), arch=$(uname -m), page_size=$(getconf PAGESIZE 2>/dev/null || echo unknown), cli_no_snapshot_mode=${use_cli_no_snapshot_mode}"
  echo "[start] Memory detected: host=${mem_total_mb}MB, cgroup=${mem_limit_mb:-none}MB, ulimit_v=${vmem_limit_mb:-none}MB, node_heap=${node_heap_mb}MB, node_opts=${node_runtime_opts:-none}"

  if [[ "$FRONTEND_PM" == "npm" ]]; then
    (
      cd "${BASE_DIR}/frontend"
      npm_cli_path="$(command -v npm)"
      vite_cli_path="${BASE_DIR}/frontend/node_modules/vite/bin/vite.js"

      run_npm_ci() {
        if [[ "$use_cli_no_snapshot_mode" -eq 1 ]]; then
          node --no-node-snapshot "$npm_cli_path" ci --no-audit --no-fund
        else
          run_with_node_options "$node_runtime_opts" npm ci --no-audit --no-fund
        fi
      }

      run_npm_build_with_opts() {
        local opts="$1"
        if [[ "$use_cli_no_snapshot_mode" -eq 1 && -f "$vite_cli_path" ]]; then
          # 直接执行 vite，确保 no-snapshot 作为 Node CLI 参数生效
          if [[ -n "$opts" ]]; then
            node --no-node-snapshot $opts "$vite_cli_path" build
          else
            node --no-node-snapshot "$vite_cli_path" build
          fi
        else
          run_with_node_options "$opts" npm run build
        fi
      }

      if ! run_npm_ci; then
        echo "[start] npm ci failed, retrying once after cleaning node_modules..."
        rm -rf node_modules
        run_npm_ci
      fi

      build_ok=0
      if run_with_node_options "$build_node_opts" node -e "process.exit(0)" >/dev/null 2>&1; then
        if run_npm_build_with_opts "$build_node_opts"; then
          build_ok=1
        fi
      else
        echo "[start] Node runtime check failed with NODE_OPTIONS='${build_node_opts}'; will build without NODE_OPTIONS."
      fi

      if [[ "$build_ok" -eq 0 ]]; then
        echo "[start] Retrying frontend build without NODE_OPTIONS..."
        if run_npm_build_with_opts ""; then
          build_ok=1
        fi
      fi

      if [[ "$build_ok" -eq 0 ]]; then
        echo "[start] Retrying frontend build with conservative heap=1024MB..."
        if run_npm_build_with_opts "$conservative_node_opts"; then
          build_ok=1
        fi
      fi

      if [[ "$build_ok" -ne 1 ]]; then
        echo "[start] Frontend build failed after retries."
        exit 1
      fi
    )
  else
    (
      cd "${BASE_DIR}/frontend"
      if [[ -f "${BASE_DIR}/frontend/pnpm-lock.yaml" ]]; then
        run_with_node_options "$node_runtime_opts" pnpm install --frozen-lockfile
      else
        run_with_node_options "$node_runtime_opts" pnpm install
      fi

      build_ok=0
      if run_with_node_options "$build_node_opts" node -e "process.exit(0)" >/dev/null 2>&1; then
        if run_with_node_options "$build_node_opts" pnpm run build; then
          build_ok=1
        fi
      else
        echo "[start] Node runtime check failed with NODE_OPTIONS='${build_node_opts}'; will build without NODE_OPTIONS."
      fi

      if [[ "$build_ok" -eq 0 ]]; then
        echo "[start] Retrying frontend build without NODE_OPTIONS..."
        if pnpm run build; then
          build_ok=1
        fi
      fi

      if [[ "$build_ok" -eq 0 ]]; then
        echo "[start] Retrying frontend build with conservative heap=1024MB..."
        if run_with_node_options "$conservative_node_opts" pnpm run build; then
          build_ok=1
        fi
      fi

      if [[ "$build_ok" -ne 1 ]]; then
        echo "[start] Frontend build failed after retries."
        exit 1
      fi
    )
  fi

  # 2) 生成 Nginx 配置
  MIME_PATH="${BASE_DIR}/deploy/mime.types"
  NGINX_TEMPLATE="${BASE_DIR}/deploy/nginx_linux.conf"
  NGINX_GENERATED_PATH="${BASE_DIR}/deploy/nginx.generated.conf"

  if command -v envsubst >/dev/null 2>&1; then
    envsubst '$FRONTEND_ROOT' < "$NGINX_TEMPLATE" | tr -d '\r' > "$NGINX_GENERATED_PATH"
  else
    # fallback: only replace known placeholders to avoid touching nginx variables like $uri
    python - <<PY
import os

BASE_DIR = "${BASE_DIR}"
FRONTEND_ROOT = "${FRONTEND_ROOT}"

src = os.path.join(BASE_DIR, "deploy", "nginx_linux.conf")
dst = os.path.join(BASE_DIR, "deploy", "nginx.generated.conf")
with open(src, "r", encoding="utf-8") as f:
    data = f.read()
data = data.replace("\r\n", "\n").replace("\r", "\n")
data = data.replace("\${FRONTEND_ROOT}", FRONTEND_ROOT)
with open(dst, "w", encoding="utf-8", newline="\n") as f:
    f.write(data)
PY
  fi
  if grep -qE '^[[:space:]]*root[[:space:]]*;' "$NGINX_GENERATED_PATH"; then
    echo "[start] Invalid nginx root generated (empty FRONTEND_ROOT)."
    exit 1
  fi
  echo "[start] Nginx config generated at $NGINX_GENERATED_PATH"
fi

if [[ "$do_nginx" -eq 1 && "$do_frontend" -eq 1 ]]; then
  # 3) 检查并安装 Nginx
  if ! command -v nginx >/dev/null 2>&1; then
    echo "[start] Nginx not found. Installing..."
    if command -v apt-get >/dev/null 2>&1; then
      # Debian/Ubuntu
      apt-get update
      apt-get install -y nginx
    elif command -v yum >/dev/null 2>&1; then
      # CentOS/RHEL
      yum install -y epel-release
      yum install -y nginx
    elif command -v dnf >/dev/null 2>&1; then
      # Fedora
      dnf install -y nginx
    else
      echo "[start] Cannot auto-install Nginx. Please install manually."
    fi
    
    if command -v nginx >/dev/null 2>&1; then
      echo "[start] Nginx installed: $(nginx -v 2>&1)"
    fi
  fi

  # 4) 启动 / 重载 Nginx（若存在）
  if command -v nginx >/dev/null 2>&1; then
    # Ensure temp dir exists for Nginx
    TEMP_DIR="${BASE_DIR}/deploy/temp"
    mkdir -p "$TEMP_DIR"

    echo "[start] Starting/reloading Nginx..."
    nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;" -s reload 2>/dev/null || \
    nginx -c "${BASE_DIR}/deploy/nginx.generated.conf" -p "${BASE_DIR}/deploy" -g "pid logs/nginx.pid;"
  else
    echo "[start] nginx not found in PATH; skipping reverse-proxy startup."
  fi
fi

# 获取当前环境 python 绝对路径
PYTHON_EXE="$(command -v python)"

# Ensure a compatible Python version for psycopg2 wheels
if [[ -n "$PYTHON_EXE" ]]; then
  py_version=$("$PYTHON_EXE" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null) || py_version=""
  if [[ "$py_version" =~ ^([0-9]+)\.([0-9]+)$ ]]; then
    py_major="${BASH_REMATCH[1]}"
    py_minor="${BASH_REMATCH[2]}"
    if [[ "$py_major" -gt 3 || ( "$py_major" -eq 3 && "$py_minor" -ge 13 ) ]]; then
      echo "[start] Detected Python ${py_major}.${py_minor} which is not supported by psycopg2-binary. Please use Python $CONDA_PYTHON_VERSION."
      exit 1
    fi
  fi
fi

# 3.5) 安装/更新依赖
if [[ "$do_inference" -eq 1 || "$do_business" -eq 1 ]]; then
  if [[ -f "${BASE_DIR}/requirements.txt" ]]; then
    echo "[start] Installing/Updating Python dependencies..."
    "$PYTHON_EXE" -m pip install -r "${BASE_DIR}/requirements.txt"
  fi
fi

# 3.6) PostgreSQL smoke test (default when business enabled)
if [[ "$do_business" -eq 1 ]]; then
  TEST_SCRIPT="${BASE_DIR}/tests/fixtures/test_postgres.py"
  if [[ -f "$TEST_SCRIPT" ]]; then
    echo "[start] Running PostgreSQL smoke test..."
    if ! "$PYTHON_EXE" "$TEST_SCRIPT"; then
      echo "[start] PostgreSQL smoke test failed."
      exit 1
    fi
  else
    echo "[start] PostgreSQL test script not found; skipping smoke test."
  fi
fi

# 4) 启动 FastAPI 推理服务
if [[ "$do_inference" -eq 1 ]]; then
  echo "[start] Starting FastAPI inference service (8000)..."
  echo "[start] Working directory: $BASE_DIR"
  nohup "$PYTHON_EXE" -m uvicorn backend_inference.main:app --host 0.0.0.0 --port 8000 \
    > "${LOGS_DIR}/inference.log" 2>&1 &
fi

# 5) 启动业务服务 (Flask 默认，FastAPI 可选并行)
if [[ "$do_business" -eq 1 ]]; then
  # Flask (主业务后端)
  echo "[start] Starting Flask business service (5001)..."
  nohup "$PYTHON_EXE" "${BASE_DIR}/backend_business/app.py" \
    > "${LOGS_DIR}/business.log" 2>&1 &

  # FastAPI 业务后端 (可选，使用 /api/v2/ 前缀)
  if [[ "$ENABLE_FASTAPI_BUSINESS" == "1" ]]; then
    echo "[start] Starting FastAPI business service (5002) with /api/v2/ prefix..."
    echo "[start] Working directory: $BASE_DIR"
    nohup "$PYTHON_EXE" -m uvicorn backend_business.main:app --host 0.0.0.0 --port 5002 \
      > "${LOGS_DIR}/business_fastapi.log" 2>&1 &
  fi
fi

backend_info="Flask 5001"
if [[ "$ENABLE_FASTAPI_BUSINESS" == "1" ]]; then
  backend_info="Flask 5001 + FastAPI 5002 (/api/v2/)"
fi

echo "[start] Done. Mode=$MODE; Model provider=$PROVIDER; Entry=$ENTRY"
echo "[start] Nginx 8008 (if enabled), FastAPI 8000 (if enabled), Business: $backend_info."
echo "[start] Logs located in $LOGS_DIR"

# 6) 启动 FRP 客户端（如果启用）
if [[ "$FRP_MODE" == "1" ]]; then
  FRP_DIR="${BASE_DIR}/deploy/frp"
  FRP_CONFIG="${FRP_DIR}/frpc.toml"
  FRP_PID_FILE="${LOGS_DIR}/frpc.pid"
  
  echo "[start] Setting up FRP client..."
  
  # 检测系统架构
  os_name="linux"
  arch_name="$(uname -m)"
  case "$arch_name" in
    x86_64|amd64) arch_name="amd64" ;;
    aarch64|arm64) arch_name="arm64" ;;
    armv7l|armhf) arch_name="arm" ;;
    i386|i686) arch_name="386" ;;
    *) echo "[start] Warning: Unknown architecture $arch_name, falling back to amd64"; arch_name="amd64" ;;
  esac
  
  # 获取最新版本号
  FRP_VERSION=""
  if command -v curl >/dev/null 2>&1; then
    FRP_VERSION=$(curl -sI "https://github.com/fatedier/frp/releases/latest" 2>/dev/null | grep -i "location:" | sed 's/.*tag\///' | tr -d '\r\n')
  fi
  if [[ -z "$FRP_VERSION" ]]; then
    FRP_VERSION="0.61.1"
    echo "[start] Could not fetch latest version, using default: $FRP_VERSION"
  else
    echo "[start] Latest FRP version: $FRP_VERSION"
  fi
  
  FRP_TAR_NAME="frp_${FRP_VERSION#v}_${os_name}_${arch_name}.tar.gz"
  FRP_DIR_NAME="frp_${FRP_VERSION#v}_${os_name}_${arch_name}"
  FRP_DOWNLOAD_URL="https://github.com/fatedier/frp/releases/download/${FRP_VERSION}/${FRP_TAR_NAME}"
  FRP_EXE="${FRP_DIR}/${FRP_DIR_NAME}/frpc"
  
  mkdir -p "$FRP_DIR"
  
  # 检查是否需要下载
  if [[ ! -f "$FRP_EXE" ]]; then
    echo "[start] Downloading FRP client from $FRP_DOWNLOAD_URL..."
    FRP_TAR_PATH="${FRP_DIR}/${FRP_TAR_NAME}"
    if command -v curl >/dev/null 2>&1; then
      curl -L -o "$FRP_TAR_PATH" "$FRP_DOWNLOAD_URL"
    elif command -v wget >/dev/null 2>&1; then
      wget -O "$FRP_TAR_PATH" "$FRP_DOWNLOAD_URL"
    else
      echo "[start] Error: Neither curl nor wget is available"
      exit 1
    fi
    
    if [[ -f "$FRP_TAR_PATH" ]]; then
      tar -xzf "$FRP_TAR_PATH" -C "$FRP_DIR"
      rm -f "$FRP_TAR_PATH"
      echo "[start] FRP client downloaded and extracted"
    else
      echo "[start] Error: Failed to download FRP client"
      exit 1
    fi
  else
    echo "[start] FRP client already exists at $FRP_EXE"
  fi
  
  # 生成 frpc.toml 配置文件
  cat > "$FRP_CONFIG" <<EOF
serverAddr = "${FRP_SERVER_ADDR}"
serverPort = 7000

auth.method = "token"
auth.token = "${FRP_TOKEN}"

[[proxies]]
name = "nginx"
type = "tcp"
localIP = "127.0.0.1"
localPort = 8008
remotePort = 16666
EOF
  
  echo "[start] FRP config generated at $FRP_CONFIG"
  
  # 启动 frpc
  echo "[start] Starting FRP client..."
  chmod +x "$FRP_EXE"
  nohup "$FRP_EXE" -c "$FRP_CONFIG" > "${LOGS_DIR}/frpc.log" 2>&1 &
  FRP_PID=$!
  echo "$FRP_PID" > "$FRP_PID_FILE"
  echo "[start] FRP client started (PID: $FRP_PID)"
  echo "[start] Remote access: ${FRP_SERVER_ADDR}:16666 -> local:8008"
fi
