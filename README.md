# Semantic-Atlas

## 目录结构

```
data/
├── models/
│   └── deberta-v3-large/
│       ├── config.json
│       └── pytorch_model.bin
├── ollama_home/
├── pg_data/
└── datasets/

deploy/
├── nginx.conf
└── start.sh

frontend/
├── src/
│   ├── assets/
│   ├── components/
│   │   ├── charts/
│   │   │   ├── TraceGraph.vue
│   │   │   └── Heatmap.vue
│   │   └── FileUpload.vue
│   ├── stores/
│   │   └── reqStore.js
│   ├── views/
│   │   ├── Classification.vue
│   │   ├── Traceability.vue
│   │   └── ConflictDetection.vue
│   └── utils/
│       └── api.js
└── package.json

backend_business/
├── app.py
├── config.py
├── routes/
│   ├── file_route.py
│   └── analysis_route.py
└── services/
    ├── db_service.py
    └── ai_proxy.py

backend_inference/
├── main.py                 # FastAPI 应用入口与生命周期管理
├── routers/                # 业务路由层（按功能模块拆分）
│   └── conflict.py         # [示例] 需求冲突检测路由
├── schemas/                # 数据契约层（Pydantic模型）
│   ├── inference.py        # 通用推理数据结构
│   └── conflict_report.py  # 冲突检测专用数据结构
├── core/                   # 核心基础层
│   ├── config.py           # 全局配置
│   ├── engine.py           # 模型底层引擎封装
│   └── model_container.py  # 模型单例容器
└── test_conflict.py        # 自动化测试脚本
```

## Backend Inference 架构设计与开发指南

模块 (`backend_inference`) 负责处理所有与大模型 (DeepSeek) 相关的推理任务。为了应对未来“需求分类”、“需求追溯”等功能的扩展

### 1. 设计

我们采用了以下设计模式，确保不同业务模块之间**互不干扰**，同时共享底层资源：

*   **Router 模式 (物理隔离)**: 每个业务功能（如冲突检测、分类、追溯）都有独立的路由文件。修改“冲突检测”的代码绝不会影响“需求分类”。
*   **Schemas 分离 (数据隔离)**: 每个业务拥有独立的输入/输出数据定义 (Pydantic Models)。
*   **Singleton 单例模式 (资源共享)**: 无论有多少个业务模块，底层的 DeepSeek 模型在内存中**只加载一次**，所有模块共享同一个模型实例，极大节省显存。

### 2. 代码结构详解

#### Layer 1: Core (核心基础层)
这是系统的地基，通常不需要修改。
*   `core/engine.py`: 封装了 `transformers` 的复杂逻辑（模型加载、Token处理、显存自动分配）。外界调用只需一行代码 `engine.generate(...)`。
*   `core/model_container.py`: **关键组件**。它是一个全局容器，负责在应用启动时初始化模型，并供所有 Router 调用。

#### Layer 2: Schemas (数据契约层)
定义前端/业务端传来的数据长什么样。
*   例如 `schemas/conflict_report.py` 定义了冲突检测只需传 `requirement_a` 和 `requirement_b`。
*   严格的数据校验防止了脏数据进入模型层。

#### Layer 3: Routers (业务逻辑层)
这是日常开发主要工作的区域。
*   例如 `routers/conflict.py`: 处理 HTTP 请求，拼接 Prompt（提示词），调用 Core 层，处理返回结果。
*   **Prompt 管理**: 提示词 (Prompt) 维护在各自的 Router 文件中。

#### Layer 4: Main (应用入口)
*   `main.py`: 负责将所有的 Router 注册到 FastAPI 应用中，并管理生命周期（启动时加载模型）。

---

### 3. 需求冲突检测的设计思路 (Design Philosophy)

需求冲突检测模块 (`backend_inference/routers/conflict.py`) 的设计核心在于**利用大语言模型的语义理解能力，配合严格的提示词工程 (Prompt Engineering)**。

#### 实现机制
1.  **输入**: 接收两个需求文本（Requirement A 和 Requirement B）。
2.  **Prompt 构建**: 使用预定义的 `SYSTEM_PROMPT_CONFLICT`，明确告知模型什么情况属于“冲突”，什么属于“不冲突”。
    *   **冲突定义**: 逻辑互斥（如“>2s”与“<1s”）、属性互斥（“黑”与“白”）。
    *   **非冲突定义**: 兼容、不同维度、相似内容。
3.  **推理**: 调用共享的 `model_engine` 生成文本回答。
4.  **结果解析**:
    *   采用规则解析 (Rule-based Parsing) 对模型的自然语言输出进行标准化处理。
    *   主要依据模型输出的开头关键词（"冲突" 或 "不冲突"）来判定布尔值结果。
    *   保留 `raw_response` 以便人工复核和调试。

此设计的优势在于**灵活性**：通过调整 System Prompt 即可优化冲突检测的标准，而无需修改底层代码。

---

### 4. 需求追溯与需求分类开发指南

后续队友在提交“需求追溯”和“需求分类”功能时，请严格遵守以下开发规范：

#### 需求分类 (Requirement Classification)

**设计目标**: 将非结构化的需求文本自动归类为预定义的类别（如：功能需求、性能需求、安全需求等）。

**开发步骤**:
1.  **定义数据结构**: 在 `backend_inference/schemas/classification.py` 中定义请求和响应模型。
    *   Request: 包含 `requirement_text`。
    *   Response: 包含 `category` (类别) 和 `confidence` (置信度，可选)。
2.  **编写路由逻辑**: 在 `backend_inference/routers/` 下创建 `classification.py`。
    *   定义 `SYSTEM_PROMPT_CLASSIFICATION`，列出所有可选类别及其定义。
    *   构造 Prompt 让模型输出分类标签。
3.  **注册路由**: 在 `main.py` 中取消 `app.include_router(classification.router)` 的注释。

#### 需求追溯 (Requirement Traceability)

**设计目标**: 建立需求之间的关联关系（如：Parent-Child, Depends-On），形成追溯图谱。

**开发步骤**:
1.  **定义数据结构**: 在 `backend_inference/schemas/trace_output.py` 中定义图谱结构。
    *   通常包含 `nodes` (需求节点列表) 和 `links` (关联关系列表)。
2.  **编写路由逻辑**: 在 `backend_inference/routers/` 下创建 `traceability.py` (假设命名)。
    *   追溯通常需要分析多个需求。Prompt 可能会比较复杂，需要让模型输出 JSON 格式的关联列表。
    *   示例 Prompt: "分析以下需求列表，找出它们之间的依赖关系，并以 JSON 格式输出..."。
3.  **注册路由**: 同样在 `main.py` 中注册新路由。

**注意**: 所有新功能都**必须**使用 `core/model_container.py` 中的 `model_engine` 单例，**严禁**在路由中重新加载模型。
