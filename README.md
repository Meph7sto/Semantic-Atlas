# Semantic-Atlas

## 目录结构

```
# Semantic-Atlas

Semantic-Atlas 是一个面向“需求工程”的语义分析原型项目，当前已实现 **需求冲突检测** 的端到端链路；**需求分类** 与 **需求追溯** 已预留工程结构与前端入口（占位），本文档给出后续的设计与落地路径（不涉及具体代码）。

---

## 1. 当前能力概览

- ✅ 需求冲突检测：输入两条需求文本，返回是否冲突与模型解释。
- ⏳ 需求分类（规划中）：前端/后端结构已预留，但页面与接口仍为占位。
- ⏳ 需求追溯（规划中）：前端/后端结构已预留，但页面与接口仍为占位。

---

## 2. 总体架构（按现有实现）

本项目采用“三段式”架构，将 **UI**、**业务编排** 与 **模型推理** 解耦：

1) **Frontend（Vue + Vite）**：用户交互与结果展示

2) **Business Backend（Flask）**：业务 API 网关/编排层（统一对前端提供 `/api/**`）

3) **Inference Backend（FastAPI + Transformers）**：模型加载与推理（统一对业务后端提供 `/conflict/**` 等推理接口）

可选：通过 `deploy/nginx.conf` 将前端静态资源、`/api/*` 与 `/inference/*` 统一入口到同一端口（默认 8008）。

---

## 3. 需求冲突检测是如何做的（已实现）

### 3.1 目标与输入输出

**目标**：判断“需求A”和“需求B”是否存在 **无法同时满足** 的逻辑冲突。

**请求（JSON）**

```json
{
    "requirement_a": "...",
    "requirement_b": "..."
}
```

**响应（JSON）**

```json
{
    "is_conflict": true,
    "raw_response": "冲突：..."
}
```

其中：

- `is_conflict`：布尔判定结果
- `raw_response`：模型的原始解释文本（用于调试/复核）

### 3.2 端到端链路（从前端到模型）

**Step 1｜前端发起请求**

- 页面：`frontend/src/views/ConflictDetection.vue`
- 调用：`POST /api/conflict/check`
- 开发态（Vite）：`frontend/vite.config.js` 将 `/api` 代理到 `http://localhost:5001`

**Step 2｜业务后端转发（Flask 代理层）**

- 服务入口：`backend_business/app.py`
- 路由：`backend_business/routes/conflict_routes.py`
- 行为：收到 `/api/conflict/check` 后，将请求原样转发到推理后端：

```
{INFERENCE_URL}/conflict/check
```

`INFERENCE_URL` 默认为 `http://localhost:8000`，可通过环境变量覆盖。

**Step 3｜推理后端处理（FastAPI + 模型）**

- 服务入口：`backend_inference/main.py`
- 路由：`backend_inference/routers/conflict.py`（`POST /conflict/check`）
- 行为：
    - 用预定义的系统提示词（System Prompt）明确“冲突/不冲突”的判定规则与输出格式
    - 将两条需求拼接为用户提示词（User Prompt）
    - 调用共享的 `model_engine.generate(...)` 生成模型回答
    - 对模型输出做规则解析：优先看输出前缀是否为“冲突/不冲突”，否则回退为关键字匹配

### 3.3 为什么要分“业务后端”和“推理后端”

当前冲突检测看起来只是“代理转发”，但这个分层对后续扩展非常关键：

- **业务后端**：负责鉴权、审计、数据入库、批处理编排、任务队列等“工程化能力”（未来会逐步补齐）。
- **推理后端**：只关注模型加载、提示词、推理与结构化输出，保持可替换性。

### 3.4 健康检查

- Flask：`GET /health`（5001）
- FastAPI：`GET /health`（8000，返回 `model_loaded` 状态）

---

## 4. 快速开始（Windows 本地开发推荐）

### 4.1 环境准备

- Python（建议使用虚拟环境）
- Node.js（建议使用 LTS）

安装 Python 依赖：

```bash
pip install -r requirements.txt
```

安装前端依赖：

```bash
cd frontend
npm install
```

### 4.2 启动推理后端（FastAPI，8000）

```bash
uvicorn backend_inference.main:app --host 0.0.0.0 --port 8000
```

### 4.3 启动业务后端（Flask，5001）

```bash
python backend_business/app.py
```

### 4.4 启动前端（Vite Dev Server，5173）

```bash
cd frontend
npm run dev
```

打开：`http://localhost:5173`，进入 “Conflict Detection”。

---

## 5. 一键启动（Linux/macOS / 服务器部署形态）

项目提供 `deploy/start.sh`：

- 自动构建前端（`npm install && npm run build`）
- 生成并启动 Nginx（默认监听 8008）
- 后台启动 FastAPI（8000）与 Flask（5001）

```bash
bash deploy/start.sh
```

停止脚本：

```bash
bash deploy/stop_services.sh
```

说明：停止脚本依赖 `lsof`，更适用于 Linux/macOS 环境。

---

## 6. 配置说明（与现有代码一致）

### 6.1 业务后端 → 推理后端地址

- 环境变量：`INFERENCE_URL`
- 默认值：`http://localhost:8000`

### 6.2 推理模型路径

推理后端默认模型目录由 `backend_inference/core/config.py` 计算：

- 项目根目录：自动推导
- 默认相对路径：`data/models/deepseek_conflict`

注意：仓库当前 `data/models/` 下可能仅包含其他模型目录（例如 `deberta-v3-large/`）。如果你要运行冲突检测推理服务，需要确保 **`data/models/deepseek_conflict/` 指向一个可用于生成式对话/生成任务的 Transformers 模型目录**（包含 tokenizer、config、权重等文件），或自行调整配置。

---

## 7. 目录结构（按当前实现与占位情况标注）

```
frontend/                 # Vue UI（当前仅 /conflict 路由已接通）
    src/views/ConflictDetection.vue
    src/views/Classification.vue      # 占位
    src/views/Traceability.vue        # 占位
    src/components/...                # 多为占位

backend_business/          # Flask 业务编排层（当前仅冲突检测路由可用）
    app.py
    routes/conflict_routes.py
    routes/analysis_route.py          # 占位
    routes/file_route.py              # 占位
    services/ai_proxy.py              # 占位
    services/db_service.py            # 占位

backend_inference/         # FastAPI 推理层（当前仅 conflict 路由可用）
    main.py
    routers/conflict.py
    schemas/conflict_report.py
    core/engine.py
    core/model_container.py

deploy/                    # Nginx 与一键启动脚本
data/                      # 模型/数据目录
```

---

## 8. 后续开发设计：需求分类（如何设计与落地）

### 8.1 目标

把“非结构化需求文本”自动归入约定的分类体系（Taxonomy），并支持：

- 单标签或多标签分类（建议优先多标签，兼容现实需求）
- 置信度/依据片段（可选，用于审计与迭代）
- 批量处理（从文件导入或数据库拉取）

### 8.2 建议的数据模型（不限定存储实现）

最小可用的数据实体建议如下：

1) **Requirement（需求）**

- `id`：需求唯一标识
- `text`：需求原文
- `source`：来源（文件名/模块/系统）
- `version`：版本或批次号（支持增量迭代）
- `created_at/updated_at`

2) **ClassificationResult（分类结果）**

- `requirement_id`
- `labels`：分类标签列表（或主标签 + 子标签）
- `scores`：置信度（可选）
- `rationale`：分类依据（可选，面向人工复核）
- `model_version/prompt_version`

### 8.3 推理后端 API 设计（FastAPI）

建议新增一个独立 Router（与 conflict 完全隔离），并遵循“结构化输出优先”的原则：

- `POST /classification/classify`：单条需求分类
- `POST /classification/batch`：批量分类（输入需求列表，输出逐条结果）

输出尽量采用稳定的 JSON 结构（由 Pydantic Schema 校验），避免前端依赖自然语言文本。

### 8.4 业务后端 API 设计（Flask）

业务后端不做模型细节，只做编排与工程化增强：

- `POST /api/classification/classify`：转发到推理后端，并可选择写入数据库
- `POST /api/classification/batch`：支持文件上传/批处理任务（未来可接队列）
- `GET /api/classification/result?batch_id=...`：查询批次结果

这里将来可把 `backend_business/services/db_service.py` 补齐为数据持久层。

### 8.5 前端页面与交互设计

建议把“分类”页面拆成三个稳定阶段：

1) 导入需求（手输/文件上传）
2) 触发分类（单条/批量）
3) 展示结果（表格 + 可视化，如热力图/分布图）

并使用统一的状态管理（Pinia）维护：需求列表、批次状态、结果缓存。

---

## 9. 后续开发设计：需求追溯（如何设计与落地）

### 9.1 目标

在需求之间建立“可解释、可查询、可视化”的关系网络，用于：

- 上下游追踪（高层需求 → 子需求/实现需求）
- 依赖关系（依赖、前置、约束）
- 重复/等价需求识别
- 与冲突检测联动（冲突边作为一种关系类型）

### 9.2 关系类型建议（可扩展）

先定义一个最小关系集合，避免早期复杂化：

- `refines`：细化/派生（Parent → Child）
- `depends_on`：依赖
- `duplicates`：重复/等价
- `conflicts_with`：冲突（可复用冲突检测结果）

### 9.3 追溯生成的推荐流程（可扩展为离线任务）

追溯的核心难点在于候选对生成与规模控制。建议采用“两阶段”流程：

1) **候选生成（检索/相似度阶段）**

- 对需求文本生成向量表示（Embedding），或用关键词检索（BM25）
- 为每条需求召回 Top-K 候选（避免 O(n^2) 全量两两比较）

2) **关系判定（LLM 判别阶段）**

- 对候选对调用模型，输出关系类型 + 置信度 + 简短依据
- 强制模型输出结构化 JSON，便于入库与前端可视化

### 9.4 推理后端 API 设计（FastAPI）

- `POST /traceability/build`：输入需求列表（或 batch_id），输出节点与边
- `POST /traceability/pair`：对某一对需求做关系判定（便于调试与人工复核）

### 9.5 业务后端 API 设计（Flask）

- `POST /api/traceability/build`：编排“候选生成 + 判定 + 入库”
- `GET /api/traceability/graph?requirement_id=...&depth=...`：按需查询子图

### 9.6 前端可视化设计

追溯结果建议统一成图结构：

- `nodes`: [{ id, text, labels... }]
- `links`: [{ source, target, type, score }]

前端 “Traceability” 页面以图谱为主，支持：按需求 ID 选点、按 depth 展开、点击边展示解释。

---

## 10. 开发约束（保持工程可扩展性）

为避免后续模块互相干扰，建议持续遵循当前的分层方式：

- 推理后端按功能拆分 Router 与 Schema（`routers/*` + `schemas/*`）
- 模型通过单例容器共享（只加载一次），路由中禁止重复加载模型
- 业务后端聚焦编排与工程化能力（鉴权、入库、批处理、审计、队列、缓存）
