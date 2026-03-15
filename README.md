# Semantic-Atlas

Semantic-Atlas 是面向需求工程的语义分析平台，覆盖会议转写解析、上下文构建、多层级需求抽取、追溯关系分析、冲突检测、需求分类、多 Agent 协作与通用对话等场景。系统采用三层架构：前端提供可视化工作台，业务后端负责编排与数据落库，推理后端负责模型调用与推理服务。

## 功能概览

- **会议转写解析（Phase 1）**：转写文本 → spans 写入数据库，支持 SSE 进度流
- **上下文构建（Phase 2）**：基于 spans 生成关联图、bundles 与 context_run_id
- **L1/L2/L3 需求抽取（Phase 3）**：EgoBundle + tool-call 写入 `requirements_l123`
- **L4 需求生成**：基于知识库的低层级需求细化生成与验证
- **需求追溯**：单对/批量关系分析、追溯网络可视化、结果入库/下载
- **冲突检测**：单对/流式冲突识别
- **需求分类**：文本/CSV 批量分类与统计
- **需求去重**：重复需求识别与合并
- **项目与产品管理**：项目 CRUD、产品管理、里程碑与分支管理
- **用户认证与权限**：JWT 认证、RBAC 权限管理、系统身份控制
- **执行图管理**：Agent 执行拓扑结构与可视化
- **需求 Actor**：需求执行者分配与管理
- **多 Agent 协作**：基于 MessageBus + Channel 的多 Agent 通信架构（详见 [AGENT_ARCHITECTURE.md](./AGENT_ARCHITECTURE.md)）
- **通用对话**：流式 chat（`/inference/chat/stream`）
- **移动端支持**：移动端消息桥接与推送通知

## 核心流程（Phase 1-3）

1. `/api/v2/ingest_transcript`：会议转写解析 → spans
2. `/api/v2/build_context`：构建关联图 → bundles / context_run_id
3. `/api/v2/requirements/extract_l123`：EgoBundle 抽取 L1/L2/L3 需求 → PostgreSQL

## 架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Vue 3 + Vite + Tailwind)       │
│                         Port: 8008                          │
│ /api/v2 → Business Backend   /inference → Inference Backend │
├─────────────────────────────────────────────────────────────┤
│ Business Backend (FastAPI) │  Inference Backend (FastAPI)   │
│       Port: 5002           │        Port: 8000              │
│  编排 / 存储 / 推理代理      │  LLM / ML 模型推理             │
├─────────────────────────────────────────────────────────────┤
│                  PostgreSQL (Port: 5432)                     │
│                  Adminer   (Port: 8080)                     │
└─────────────────────────────────────────────────────────────┘
```

- **Frontend**: Vue 3 + Vite + Tailwind (`frontend/`)，通过 `/api/v2` 代理访问业务后端，`/inference` 代理访问推理后端
- **Business Backend**: FastAPI (`backend_business/`)，负责 `/api/v2/*` 编排、存储与推理代理
- **Inference Backend**: FastAPI (`backend_inference/`)，负责冲突/追溯/分类/需求抽取/L4 生成/知识库/对话
- **可选 Nginx**: `deploy/nginx*.conf`，统一入口端口 8008

## 快速开始（本地开发）

> 建议使用 Python 3.12（`psycopg2-binary` 依赖版本要求）项目采用 conda 进行环境管理，运行前请自行创建并激活 `semantic-Atlas` 环境（注意大小写）。

### 环境准备

```bash
conda create -n semantic-Atlas python=3.12
conda activate semantic-Atlas
```

### 安装依赖

1) 安装 Python 依赖

```bash
pip install -r requirements.txt
```

2) 安装前端依赖

```bash
cd frontend && npm install
```

### 启动服务

3) 启动 PostgreSQL（Docker）

```bash
docker compose up -d
```

4) 启动推理后端（FastAPI）

```bash
uvicorn backend_inference.main:app --host 0.0.0.0 --port 8000
```

5) 启动业务后端（FastAPI）

```bash
uvicorn backend_business.main:app --host 0.0.0.0 --port 5002
```

6) 启动前端（Vite Dev Server）

```bash
cd frontend && npm run dev
```

访问: `http://localhost:8008`

## 一键启动

### Linux/macOS

```bash
bash deploy/start.sh --mode all --provider local
```

### Windows PowerShell

```powershell
.\deploy\start.ps1 -Mode all -Provider local
```

停止服务:

```bash
# Linux/macOS
bash deploy/stop_services.sh

# Windows PowerShell
.\deploy\stop_services.ps1
```

说明:
- `deploy/start.sh` 与 `deploy/start.ps1` 会执行前端构建并生成 `deploy/nginx.generated.conf`
- Windows 脚本会尝试下载 `deploy/nginx-1.26.1`（若本地不存在）
- 日志默认输出在 `deploy/logs/`
- 图生文（AutoDL）在 Alpha 图生文页面内填写连接信息并点击生成即可，无需单独启动脚本

## 前端路由

前端分为三套页面体系:

### Beta（正式功能）`/beta/*`

| 路由 | 页面 | 说明 |
|------|------|------|
| `/beta/login` | LoginView | 登录 |
| `/beta/register` | RegisterView | 注册 |
| `/beta/dashboard` | DashboardView | 仪表盘 |
| `/beta/project` | ProjectManageView | 项目管理 |
| `/beta/products` | ProductManageView | 产品管理 |
| `/beta/requirements-collection` | RequirementsCollectionView | Phase 1-3 流水线入口 |
| `/beta/requirements-analysis` | RequirementsAnalysisView | 需求分析 |
| `/beta/requirements` | RequirementsView | 需求展示 |
| `/beta/requirements-session` | RequirementsSessionView | 会话级需求查看 |
| `/beta/account` | AccountView | 账户设置 |
| `/beta/user-manage` | UserManageView | 用户管理（仅系统管理员） |

### Alpha（实验功能）`/alpha/*`

| 路由 | 页面 | 说明 |
|------|------|------|
| `/alpha/transcript-ingestion` | TranscriptIngestion | Phase 1 转写解析 |
| `/alpha/context-builder` | ContextBuilder | Phase 2 上下文构建 |
| `/alpha/requirements-extraction` | RequirementsExtraction | Phase 3 需求抽取 |
| `/alpha/l4-testing` | L4Testing | L4 需求测试 |
| `/alpha/requirements-manage` | RequirementsManage | 需求管理（调试） |
| `/alpha/requirements-manage-table` | RequirementsManageTableDebug | 需求表格（调试） |
| `/alpha/conflict` | ConflictDetection | 冲突检测 |
| `/alpha/traceability` | Traceability | 追溯分析 |
| `/alpha/classification` | Classification | 需求分类 |
| `/alpha/acquisition-trace` | AcquisitionTraceability | 获取 + 追溯 |
| `/alpha/chat` | GeneralChat | 通用对话 |
| `/alpha/message-push` | MessagePush | 消息推送 |
| `/alpha/mobile-bridge` | MobileBridge | 移动端桥接 |
| `/alpha/file-receive` | FileReceive | 文件接收 |
| `/alpha/image-caption` | ImageCaptionPreview | 图生文（AutoDL 配置与生成） |
| `/alpha/execution-topology` | ExecutionTopologyTemplate | 执行拓扑可视化 |
| `/alpha/actor-visual-tester` | ActorVisualTester | Actor 可视化测试 |

### 引导页

| 路由 | 说明 |
|------|------|
| `/guide` | 引导页/入口点 |

## 配置说明

推理与业务后端都会自动读取项目根目录的 `.env`。

### 推理后端

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MODEL_PROVIDER` | 模型提供方 | `local` / `chutes` / `deepseek` |
| `SKIP_MODEL_LOAD` | 跳过本地模型加载 | `false` |
| `LLM_MODEL_RELATIVE_PATH` | 本地 LLM 权重路径 | `data/models/deepseek_conflict` |
| `CLASSIFICATION_MODEL_RELATIVE_PATH` | 分类模型路径 | `data/models/deberta-v3-large` |
| `DEEPSEEK_API_KEY` | DeepSeek 模式必填 | - |
| `CHUTES_API_TOKEN` / `CHUTES_API_KEY` | Chutes 模式必填 | - |
| `OPENAI_API_KEY` / `OPENAI_BASE_URL` | OpenAI 兼容接口 | - |
| `CLASSIFICATION_LABELS` | 分类标签 | JSON 数组或逗号分隔 |

### 业务后端

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `INFERENCE_URL` / `INFERENCE_BASE_URL` | 推理后端地址 | `http://localhost:8000` |
| `CLASSIFICATION_URL` | 分类服务地址 | `http://localhost:8000` |
| `DATABASE_URL` | PostgreSQL 连接串（优先） | - |
| `POSTGRES_HOST` / `PORT` / `USER` / `PASSWORD` / `DB` | 数据库连接参数 | `127.0.0.1` / `5432` / `semantic` / `semantic_dev` / `semantic_atlas` |
| `BUSINESS_HOST` / `BUSINESS_PORT` / `BUSINESS_DEBUG` | FastAPI 业务服务配置 | - |
| `CORS_ORIGINS` | CORS 允许源 | `*` |
| `JWT_SECRET_KEY` | JWT 签名密钥（生产环境需更改） | - |

### 示例 `.env`

```bash
MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=your_key_here
SKIP_MODEL_LOAD=true
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
POSTGRES_USER=semantic
POSTGRES_PASSWORD=semantic_dev
POSTGRES_DB=semantic_atlas
JWT_SECRET_KEY=your_secret_key_here
```

## API 概览

### 业务后端（FastAPI, 前缀 `/api/v2`）

| Router | 前缀 | 说明 |
|--------|------|------|
| `analysis` | `/api/v2` | Phase 1 & 2 流水线 |
| `requirements` | `/api/v2` | Phase 3 & 需求 CRUD |
| `manage` | `/api/v2/manage` | 项目/需求/里程碑管理 |
| `product` | `/api/v2/product` | 产品管理 |
| `conflict` | `/api/v2/conflict` | 冲突检测代理 |
| `classification` | `/api/v2/classification` | 分类代理 |
| `deduplication` | `/api/v2/dedup` | 需求去重 |
| `push` | `/api/v2/push` | 推送通知（SSE） |
| `mobile_chat` | `/api/v2/mobile` | 移动端消息 |
| `file` | `/api/v2` | CSV 上传/下载 |
| `auth` | `/api/v2` | 用户认证（JWT） |
| `permission` | `/api/v2/permission` | 权限管理 |
| `execution_graph` | `/api/v2/execution_graph` | 执行图管理 |
| `execution_topology_structure` | `/api/v2/topology` | 执行拓扑结构 |
| `requirement_actor` | `/api/v2/actor` | 需求 Actor 管理 |

另有 `GET /health` 健康检查（非 `/api/v2` 前缀）。

### 推理后端（FastAPI）

| Router | 说明 |
|--------|------|
| `conflict` | 冲突检测 (`/conflict/check`, `/conflict/stream_check`) |
| `traceability` | 追溯分析 (`/traceability/relation`, `/traceability/batch-relation`) |
| `classification` | 需求分类 (`/classification/predict-texts`, `/classification/predict-csv`) |
| `requirements_acquisition` | 需求获取 (`/acquisition/extract`) |
| `chat` | 对话服务 (`/chat/stream`, `/chat/completions`, `/chat/completions/tools`) |
| `kb` | 知识库管理 |
| `l4_generation` | L4 需求生成 |
| `l4_validation` | L4 需求验证 |

## 数据库设计

数据库 schema 在 `backend_business/services/db_service_parts/schema.py` 中定义，模块化 schema 在 `backend_business/services/db_service_parts/schemas/`，首次启动自动建表。

### 流水线层（session_id 主键）

| 表 | 说明 |
|----|------|
| `spans` | 转写片段（说话人、文本、时间戳） |
| `context_runs` | Phase 2 执行记录 |
| `bundles` | 上下文聚合单元 |
| `span_links` | 片段间关系边（continuation, elaboration, dependency, same_topic, conflict） |
| `requirements_l123` | L1/L2/L3 抽取结果 |
| `low_level_requirements` | L4 低层需求 |

### 管理层（project_id 主键）

| 表 | 说明 |
|----|------|
| `manage_projects` | 项目记录，含 `current_session_id` 绑定 |
| `manage_requirements` | 项目级需求树 |
| `manage_products` | 产品管理 |
| `manage_milestones` | 里程碑 |
| `manage_branches` | 分支管理 |

### Agent 通信层

| 表 | 说明 |
|----|------|
| `mobile_chat_messages` | 移动端桥接消息（按 `user_id + session_id` 隔离） |
| `agent_channels` | 通信通道（direct / group / broadcast） |
| `agent_channel_members` | 通道成员 |
| `agent_messages` | Agent 消息记录 |
| `agent_pending_tasks` | Agent 待处理任务 |
| `ai_chat_sessions` | AI 对话会话 |

### 认证与权限层

| 表 | 说明 |
|----|------|
| `auth_users` | 用户账户（JWT 认证） |
| `permissions` | 权限定义 |
| `member_roles` | 用户在项目中的角色 |
| `project_members` | 项目成员分配 |

### 执行与 Actor 层

| 表 | 说明 |
|----|------|
| `execution_graphs` | 执行图记录 |
| `execution_nodes` | 执行节点 |
| `requirement_actors` | 需求执行者分配 |

## 多 Agent 架构

系统采用 **MessageBus + Channel** 通信模型，支持多 Agent 去中心化协作。

```
backend_business/services/agent/
├── context/          # 组合式上下文（execution, messaging, workflow, memory）
├── messaging/        # 消息总线、通道管理、路由策略、中间件
├── orchestration/    # 编排层（supervisor, workflow, strategies）
├── agents/           # Agent 定义（conductor, requirements）
├── tools/            # 工具层（requirement_tools, messaging_tools）
├── topology/         # Agent 拓扑与容器管理
├── engines/          # 思考工具引擎
└── tasks/            # 任务队列与执行器
```

通信模式:
- **Direct**: 1:1 私聊（Agent 间请求/回复）
- **Group**: 多人协作（如需求评审会议）
- **Broadcast**: 系统级广播通知

详见 [AGENT_ARCHITECTURE.md](./AGENT_ARCHITECTURE.md)。

## 目录结构

```
frontend/                          # Vue 3 + Vite + Tailwind
  src/
    views/
      beta/                        # 正式功能页面
        LoginView.vue              #   登录
        RegisterView.vue           #   注册
        DashboardView.vue          #   仪表盘
        ProjectManageView.vue      #   项目管理
        ProductManageView.vue      #   产品管理
        RequirementsCollectionView.vue  # Phase 1-3 流水线
        RequirementsAnalysisView.vue    # 需求分析
        RequirementsView.vue       #   需求展示
        RequirementsSessionView.vue #  会话级需求
        AccountView.vue           #   账户设置
        UserManageView.vue        #   用户管理
      alpha/                       # 实验功能页面
        ConflictDetection.vue      #   冲突检测
        Traceability.vue           #   追溯分析
        Classification.vue         #   需求分类
        TranscriptIngestion.vue   #   Phase 1
        ContextBuilder.vue         #   Phase 2
        RequirementsExtraction.vue #   Phase 3
        L4Testing.vue             #   L4 测试
        GeneralChat.vue           #   通用对话
        ExecutionTopologyTemplate.vue  # 执行拓扑
        ActorVisualTester.vue     #   Actor 可视化测试
        ...
      GuideView.vue                # 引导页
    router/index.js                # 路由配置
    utils/api.js                   # 统一 API 客户端
    stores/                        # Pinia 状态管理
      auth.js                      #   认证与权限

backend_business/                  # FastAPI 业务编排 + 存储
  main.py                          # FastAPI 应用入口
  api/routers/                     # FastAPI Router
    analysis.py                    #   Phase 1 & 2
    requirements.py                #   Phase 3 & 需求 CRUD
    manage.py                      #   项目/需求管理
    product.py                     #   产品管理
    conflict.py                    #   冲突检测代理
    classification.py              #   分类代理
    deduplication.py               #   需求去重
    push.py                        #   推送通知
    mobile_chat.py                 #   移动端消息
    file.py                        #   CSV 上传/下载
    auth.py                        #   用户认证
    permission.py                  #   权限管理
    execution_graph.py             #   执行图管理
    execution_topology_structure.py #   执行拓扑结构
    requirement_actor.py            #   需求 Actor 管理
  services/
    agent/                         # 多 Agent 架构
    context_builder/               # Phase 2 上下文构建
    requirements_extraction/       # Phase 3 需求抽取
    requirements_deduplication/    #   需求去重
    requirements_manage_service.py # 需求管理服务
    product_service.py             #   产品服务
    mobile_chat_service.py         #   移动端消息服务
    push_service.py                #   推送服务
    auth_service.py                #   认证服务
    permission_service.py          #   权限服务
    db_service.py                  # 数据库连接
    db_service_parts/              # 数据库 schema 与分模块操作
      schemas/
        trace_schema.py            #   追溯相关表
        requirement_schema.py      #   需求相关表
        project_schema.py          #   项目相关表
        agent_chat_schema.py      #   Agent 通信表
        auth_user_schema.py       #   认证用户表
        execution_schema.py       #   执行图表
        requirement_actor_schema.py #   Actor 表

backend_inference/                 # FastAPI 推理服务
  main.py                          # 应用入口
  routers/
    conflict.py                    # 冲突检测
    traceability.py                # 追溯分析
    classification.py              #   需求分类
    requirements_acquisition.py    #   需求获取
    chat.py                        #   对话服务
    kb.py                          #   知识库
    l4_generation.py               #   L4 需求生成
    l4_validation.py               #   L4 需求验证
  services/                        # 对应推理服务实现
    kb_service/                    #   知识库服务

deploy/                            # 部署脚本与 Nginx 配置
  start.sh / start.ps1             # 一键启动
  stop_services.sh / stop_services.ps1  # 停止服务
  nginx.conf / nginx_windows.conf / nginx_linux.conf

data/models/                       # 本地模型目录
tests/                             # 测试用例与示例文本
docker-compose.yml                 # PostgreSQL + Adminer
```

## 端口约定

| 服务 | 端口 |
|------|------|
| 前端开发服务器（Vite） | 8008 |
| 业务后端（FastAPI） | 5002 |
| 推理后端（FastAPI） | 8000 |
| PostgreSQL | 5432 |
| Adminer | 8080 |
| Nginx 统一入口 | 8008 |

## 前端开发代理

- `/api/v2` → `http://localhost:5002`（业务后端）
- `/inference` → `http://localhost:8000`（推理后端，路径去掉 `/inference` 前缀）

## 前端 API 客户端认证

前端使用 `@/utils/api.js` 中定义的两个 Axios 实例：
- `api` - 业务后端（`/api/v2` 路由）
- `inferenceAxios` - 推理后端（`/inference` 路由）

认证方式：
- **JWT Token**: `Authorization: Bearer <token>` 请求头
- **Legacy fallback**: `X-Actor` 和 `X-Role` 请求头（兼容旧版）

401 响应自动跳转到 `/beta/login`（除非已在登录/guide 页面）。
