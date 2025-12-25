# Semantic-Atlas

Semantic-Atlas 是面向需求工程的语义分析原型项目，已打通需求冲突检测与需求追溯的端到端链路（前端 UI + 业务后端 + 推理后端）。需求分类保留工程结构与前端入口，尚未实现。

## 功能概览

- [x] 需求冲突检测: 双需求文本 -> 冲突/不冲突 + 解释
- [x] 需求追溯: 单对/批量分析 + 追溯网络 + 可选 SQLite 存储与下载
- [ ] 需求分类: 前端占位

## 架构

- Frontend: Vue 3 + Vite + Tailwind (`frontend/`), 通过 `/api` 访问业务后端
- Business Backend: Flask (`backend_business/`), 负责 `/api/*` 编排与存储
- Inference Backend: FastAPI + Transformers (`backend_inference/`), 负责推理 API
- 可选 Nginx: `deploy/nginx*.conf`, 统一入口端口 8008

## 端口约定

- 前端开发服务器: 5173
- 业务后端: 5001
- 推理后端: 8000
- Nginx 统一入口: 8008

## 快速开始（本地开发）

1) 安装 Python 依赖

```bash
pip install -r requirements.txt
```

2) 安装前端依赖

```bash
cd frontend
npm install
```

3) 启动推理后端（FastAPI）

```bash
uvicorn backend_inference.main:app --host 0.0.0.0 --port 8000
```

4) 启动业务后端（Flask）

```bash
python backend_business/app.py
```

5) 启动前端（Vite Dev Server）

```bash
cd frontend
npm run dev
```

访问: `http://localhost:5173`

## 前端开发代理

- `/api` -> `http://localhost:5001`（业务后端）
- `/inference` -> `http://localhost:8000`（推理后端，路径会去掉 `/inference` 前缀）

## 一键启动

### Linux/macOS

```bash
bash deploy/start.sh --mode all --provider local
```

### Windows PowerShell

```powershell
.\deploy\start.ps1 -Mode all -Provider local
```

停止脚本:

```bash
bash deploy/stop_services.sh
```

```powershell
.\deploy\stop_services.ps1
```

说明:

- `deploy/start.sh` 和 `deploy/start.ps1` 会执行前端构建，并生成 `deploy/nginx.generated.conf`
- Windows 脚本会尝试下载 `deploy/nginx-1.26.1`（若本地不存在）
- 日志默认输出在 `deploy/logs/`

## 已实现接口

### 业务后端（Flask, `/api`）

- GET `/health`: 业务后端健康检查
- GET `/api/health`: 业务后端 + 推理后端健康检查
- POST `/api/conflict/check`: 冲突检测（转发到推理后端）
- POST `/api/trace-relation`: 单对需求追溯
- POST `/api/batch-trace-relation`: 批量需求追溯
- POST `/api/upload_csv`: CSV 批量追溯（字段名: `high_level_requirement`, `low_level_requirement`）
- GET `/api/download_result?id=ID`: 下载某条分析记录的 JSON
- GET `/api/requirements`: 列表分页
- GET `/api/requirements/{id}`: 详情
- DELETE `/api/requirements/{id}`: 删除
- GET `/api/statistics`: 统计
- POST `/api/trigger_analysis`: 兼容占位接口（复用追溯分析）

示例: 冲突检测

```json
POST /api/conflict/check
{
  "requirement_a": "系统响应时间小于 1s",
  "requirement_b": "系统响应时间大于 2s"
}
```

示例: 单对追溯

```json
POST /api/trace-relation
{
  "high_level_requirement": "系统应提供用户登录功能。",
  "low_level_requirement": "实现用户名密码校验与会话管理。",
  "max_new_tokens": 800,
  "save_to_db": false
}
```

### 推理后端（FastAPI）

- GET `/health`
- POST `/conflict/check`
- POST `/traceability/relation`
- POST `/traceability/batch-relation`

## 配置说明

### 模型与推理

- `MODEL_PROVIDER`: `local` | `chutes` | `deepseek`
- `CHUTES_API_TOKEN` / `CHUTES_API_KEY`: chutes 模式必填
- `DEEPSEEK_API_KEY`: deepseek 模式必填
- 本地模型默认路径: `data/models/deepseek_conflict`（见 `backend_inference/core/config.py`）
- 推理后端会自动读取项目根目录的 `.env`

### 业务后端

- `INFERENCE_URL` / `INFERENCE_BASE_URL`: 推理后端地址（默认 `http://localhost:8000`）
- `BUSINESS_DB_PATH`: SQLite 路径（默认 `backend_business/data/requirement_trace.db`）
- `BUSINESS_DATA_DIR`: SQLite 目录
- `BUSINESS_HOST` / `BUSINESS_PORT` / `BUSINESS_DEBUG`
- `CORS_ORIGINS`: 默认 `*`

### 一键脚本

- `FRONTEND_ROOT`: 前端构建输出目录（默认 `frontend/dist`）

## 目录结构（关键部分）

```
frontend/                     # Vue 3 + Vite + Tailwind
  src/views/ConflictDetection.vue
  src/views/Traceability.vue
  src/views/Classification.vue    # 占位
  src/utils/api.js                # 前端 API 调用

backend_business/              # Flask 业务编排 + 存储
  app.py
  routes/analysis_route.py      # 追溯分析 API
  routes/conflict_routes.py     # 冲突检测代理
  routes/file_route.py          # CSV 上传/结果下载
  services/ai_proxy.py
  services/db_service.py

backend_inference/             # FastAPI 推理服务
  main.py
  routers/conflict.py
  routers/traceability.py
  services/conflict_service.py
  services/traceability_service.py

deploy/                        # Nginx 与一键启动脚本
data/models/                   # 本地模型目录
```
