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

### 3. 如何扩展新功能（例如：添加“需求分类”）

假设需要添加一个“需求分类”功能，只需按照以下步骤操作，**无需修改现有冲突检测代码**：

#### 第一步：定义数据结构
 `backend_inference/schemas/classification.py`:
```python
from pydantic import BaseModel

class ClassifyRequest(BaseModel):
    requirement_text: str  # 只需要一段文本

class ClassifyResponse(BaseModel):
    category: str          # 返回类别（如：功能性、性能、安全性）
    confidence: float
```

#### 第二步：编写业务路由
新建 `backend_inference/routers/classification.py`:
```python
from fastapi import APIRouter
from core.model_container import model_engine  # 引用同一个模型引擎
from schemas.classification import ClassifyRequest, ClassifyResponse

router = APIRouter(prefix="/classification", tags=["Classification"])

SYSTEM_PROMPT = "你是一个需求分类专家..."

@router.post("/predict", response_model=ClassifyResponse)
async def classify(request: ClassifyRequest):
    # 1. 拼接提示词
    prompt = f"请分类以下需求：{request.requirement_text}"
    
    # 2. 调用模型
    answer = model_engine.generate(prompt, system_prompt=SYSTEM_PROMPT)
    
    # 3. 解析结果并返回
    return ClassifyResponse(category=answer, confidence=1.0)
```

#### 第三步：注册路由
打开 `backend_inference/main.py`，加入两行代码：
```python
from routers import classification  # 导入新模块

# ... 在 app = FastAPI(...) 之后
app.include_router(classification.router) # 注册新模块
```

