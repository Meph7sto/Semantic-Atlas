# Semantic-Atlas

Semantic-Atlas 是面向需求工程的语义分析原型平台，覆盖会议转写解析、上下文构建、L1/L2/L3 需求抽取、追溯关系分析、冲突检测、需求分类与通用对话等场景。前端提供可视化工作台，业务后端负责编排与数据落库，推理后端负责模型调用与推理服务。

## 功能概览

- 会议转写解析（Phase 1）：转写文本 -> spans 写入数据库，支持 SSE 进度流
- 上下文构建（Phase 2）：基于 spans 生成关联图、bundles 与 context_run_id
- L1/L2/L3 需求抽取（Phase 3）：EgoBundle + tool-call 写入 `requirements_l123`
- 需求获取：原始文本清洗 + 抽取为 L1/L2/L3 卡片（流式进度）
- 需求追溯：单对/批量关系分析、追溯网络可视化、结果入库/下载
- 冲突检测：单对/流式冲突识别
- 需求分类：文本/CSV 批量分类与统计
- 通用对话：流式 chat、工具调用接口（DeepSeek tool call 兼容）

## 核心流程（Phase 1-3）

1) `/analysis/ingest_transcript`：会议转写解析 -> spans
2) `/analysis/build_context`：构建关联图 -> bundles/context_run_id
3) `/requirements/extract_l123`：EgoBundle 抽取 L1/L2/L3 需求 -> PostgreSQL

## 架构

- Frontend: Vue 3 + Vite + Tailwind (`frontend/`)，通过 `/api` 访问业务后端，`/inference` 直连推理后端
- Business Backend: Flask (`backend_business/`)，负责 `/api/*` 编排、存储与推理代理
- Inference Backend: FastAPI + Transformers (`backend_inference/`)，负责冲突/追溯/分类/需求抽取/对话
- 可选 Nginx: `deploy/nginx*.conf`，统一入口端口 8008

## 端口约定

- 前端开发服务器（Vite）: 8008
- 业务后端: 5001
- 推理后端: 8000
- PostgreSQL: 5432
- Adminer: 8080
- Nginx 统一入口: 8008

## 快速开始（本地开发）

> 建议使用 Python 3.12（`psycopg2-binary` 依赖版本要求）。

1) 安装 Python 依赖

```bash
pip install -r requirements.txt
```

2) 安装前端依赖

```bash
cd frontend
npm install
```

3) 启动 PostgreSQL（Docker）

```bash
docker compose up -d
```

4) 启动推理后端（FastAPI）

```bash
uvicorn backend_inference.main:app --host 0.0.0.0 --port 8000
```

5) 启动业务后端（Flask）

```bash
python backend_business/app.py
```

6) 启动前端（Vite Dev Server）

```bash
cd frontend
npm run dev
```

访问: `http://localhost:8008`

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

- `deploy/start.sh` 与 `deploy/start.ps1` 会执行前端构建并生成 `deploy/nginx.generated.conf`
- Windows 脚本会尝试下载 `deploy/nginx-1.26.1`（若本地不存在）
- 日志默认输出在 `deploy/logs/`

## 配置说明

推理与业务后端都会自动读取项目根目录的 `.env`。

### 推理后端

- `MODEL_PROVIDER`: `local` | `chutes` | `deepseek`
- `LLM_MODEL_RELATIVE_PATH`: 本地 LLM 权重路径（默认 `data/models/deepseek_conflict`）
- `CHUTES_API_TOKEN` / `CHUTES_API_KEY`: chutes 模式必填
- `DEEPSEEK_API_KEY`: deepseek 模式必填
- `OPENAI_API_KEY` / `OPENAI_BASE_URL`: OpenAI 兼容接口（默认复用 DeepSeek）
- `CLASSIFICATION_MODEL_RELATIVE_PATH`: 分类模型路径（默认 `data/models/deberta-v3-large`）
- `CLASSIFICATION_LABELS`: JSON 数组或逗号分隔文本

### 业务后端

- `INFERENCE_URL` / `INFERENCE_BASE_URL`: 推理后端地址（默认 `http://localhost:8000`）
- `CLASSIFICATION_URL`: 分类服务地址（默认 `http://localhost:8000`）
- `DATABASE_URL`: PostgreSQL 连接串（优先）
- `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_USER` / `POSTGRES_PASSWORD` / `POSTGRES_DB`
- `BUSINESS_HOST` / `BUSINESS_PORT` / `BUSINESS_DEBUG`

### 示例 `.env`

```bash
MODEL_PROVIDER=local
LLM_MODEL_RELATIVE_PATH=data/models/deepseek_conflict
CLASSIFICATION_MODEL_RELATIVE_PATH=data/models/deberta-v3-large
DEEPSEEK_API_KEY=your_key_here
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=semantic
POSTGRES_PASSWORD=semantic_dev
POSTGRES_DB=semantic_atlas
```

## API 概览

### 业务后端（Flask）

除 `/health` 外，其余接口默认挂载在 `/api` 前缀下。

- GET `/health`（业务后端根路径）
- GET `/api/health`（业务后端 + 推理后端健康检查）
- POST `/conflict/check`
- POST `/trace-relation`
- POST `/batch-trace-relation`
- POST `/upload_csv` / GET `/download_result?id=ID`
- POST `/analysis/ingest_transcript` / `/analysis/ingest_transcript/stream`
- POST `/analysis/build_context` / `/analysis/build_context/stream`
- GET `/analysis/context_runs`
- GET `/analysis/bundles/<context_run_id>`
- GET `/analysis/span_links/<context_run_id>`
- GET `/analysis/spans/<session_id>`
- POST `/requirements/extract`（传统需求抽取）
- POST `/requirements/extract/stream`（SSE 代理）
- POST `/requirements/extract_l123`
- GET `/requirements/session/<session_id>` / `/requirements/stats`
- GET `/requirements/<req_id>` / DELETE `/requirements/<req_id>`
- POST `/classification/predict-texts` / `/classification/predict-csv`

### 推理后端（FastAPI）

- GET `/health`
- POST `/conflict/check` / `/conflict/stream_check`
- POST `/traceability/relation` / `/traceability/batch-relation`
- POST `/classification/predict-texts` / `/classification/predict-csv`
- POST `/acquisition/extract` / `/acquisition/extract/stream`
- POST `/chat/stream` / `/chat/completions` / `/chat/completions/tools`

## 目录结构（关键部分）

```
frontend/                     # Vue 3 + Vite + Tailwind
  src/views/ConflictDetection.vue
  src/views/TranscriptIngestion.vue
  src/views/ContextBuilder.vue
  src/views/RequirementsExtraction.vue
  src/views/RequirementsAcquisition.vue
  src/views/Traceability.vue
  src/views/AcquisitionTraceability.vue
  src/views/Classification.vue
  src/views/GeneralChat.vue
  src/utils/api.js

backend_business/              # Flask 业务编排 + 存储
  app.py
  routes/analysis_route.py
  routes/requirements_route.py
  routes/conflict_routes.py
  routes/classification_routes.py
  routes/file_route.py
  services/

backend_inference/             # FastAPI 推理服务
  main.py
  routers/conflict.py
  routers/traceability.py
  routers/classification.py
  routers/requirements_acquisition.py
  routers/chat.py
  services/

deploy/                        # Nginx 与一键启动脚本
data/models/                   # 本地模型目录
tests/                         # 测试用例与示例文本
```
