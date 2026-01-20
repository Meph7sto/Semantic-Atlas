# 需求抽取功能 (L1-L3 Requirements Extraction)

## 概述

基于 mission.txt 中"三、需求抽取"的设计，实现了完整的 L1-L3 需求抽取功能。该功能通过 EgoBundle（以锚点为中心的上下文包）和 Agent toolcall 机制，从对话片段中自动抽取业务目标、功能需求和系统需求。

## 核心组件

### 1. 数据表结构

**requirements_l123 表**
```sql
CREATE TABLE requirements_l123 (
    req_id TEXT PRIMARY KEY,              -- 需求 ID (UUID)
    session_id TEXT NOT NULL,             -- 会话 ID
    level TEXT NOT NULL,                  -- 需求层级: L1/L2/L3
    text TEXT NOT NULL,                   -- 需求文本 (10-500字)
    fingerprint TEXT NOT NULL UNIQUE,     -- 去重指纹
    anchor_span_id TEXT,                  -- 来源锚点 span ID
    r INTEGER,                            -- 邻域半径 (1 或 2)
    created_at TIMESTAMPTZ DEFAULT NOW()
);
```

**需求层级说明：**
- **L1**: 业务目标、宏观愿景（如"提升借用审批效率并降低人工核验成本"）
- **L2**: 功能需求、用户故事（如"系统应支持在线提交借用申请"）
- **L3**: 系统需求、技术约束（如"系统必须在 2 秒内完成审批流程验证"）

### 2. EgoBundle 生成器

**文件**: `backend_business/services/ego_bundle_generator.py`

支持两种策略生成以锚点为中心的上下文包：

#### 序列窗口策略
```python
bundle = generator.generate_sequence_bundle(
    spans=spans,
    anchor_idx=2,
    r=2  # 取 anchor ± 2 范围
)
```

#### 图邻域策略
```python
bundle = generator.generate_graph_bundle(
    spans=spans,
    anchor_idx=2,
    adjacency=adjacency,
    hop=1,  # 1-hop 或 2-hop
    top_m_2hop=5
)
```

**锚点选择策略：**
- `all`: 每个 span 都作为锚点（覆盖最稳）
- `keyword`: 包含特定关键词的 span
- `informative`: 信息量大的 span（推荐）

### 3. 需求执行器

**文件**: `backend_business/services/requirements_executor.py`

负责解析、校验和落库需求：

**核心约束：**
- level 必须属于 {L1, L2, L3}
- text 长度限制 10-500 字
- 每个 EgoBundle 的产出上限：L1 ≤ 2，L2 ≤ 5，L3 ≤ 8
- L3 建议使用"系统必须/应当/shall/must/should"等可验证措辞，但不强制
- 自动去重（基于 fingerprint）

### 4. 需求抽取服务

**文件**: `backend_business/services/requirements_extraction_service.py`

整合完整流程：
1. 获取 session 的所有 spans
2. 选择锚点集合
3. 对每个锚点生成 EgoBundle
4. 调用 Planner（大模型）
5. 执行器校验并落库

## API 接口

### 1. 需求抽取

**POST** `/api/requirements/extract_l123`

对指定 session 进行 L1-L3 需求抽取。

**请求参数：**
```json
{
  "session_id": "session_001",
  "context_run_id": "run_001",        // 可选，用于图邻域策略
  "bundle_strategy": "sequence",       // "sequence" | "graph"
  "anchor_strategy": "informative",    // "all" | "keyword" | "informative"
  "r": 2,                             // 邻域半径或跳数
  "model": "deepseek-chat"            // 模型名称
}
```

**响应示例：**
```json
{
  "session_id": "session_001",
  "bundle_strategy": "sequence",
  "anchor_strategy": "informative",
  "r": 2,
  "total_spans": 50,
  "total_anchors": 15,
  "bundles_processed": 15,
  "total_inserted": 28,
  "total_duplicates": 3,
  "errors": []
}
```

### 2. 查询 Session 需求

**GET** `/api/requirements/session/{session_id}`

查询指定 session 的需求列表，支持按层级过滤和分页。

**查询参数：**
- `level`: L1 | L2 | L3（可选）
- `page`: 页码（默认 1）
- `per_page`: 每页数量（默认 50）

**响应示例：**
```json
{
  "requirements": [
    {
      "req_id": "uuid-001",
      "session_id": "session_001",
      "level": "L1",
      "text": "提升借用审批效率并降低人工核验成本",
      "fingerprint": "sha256...",
      "anchor_span_id": "span_003",
      "r": 2,
      "created_at": "2026-01-19T10:00:00Z"
    }
  ],
  "total": 28,
  "pages": 1,
  "current_page": 1,
  "per_page": 50
}
```

### 3. 需求详情

**GET** `/api/requirements/{req_id}`

获取单个需求的详细信息。

### 4. 删除需求

**DELETE** `/api/requirements/{req_id}`

删除指定需求。

### 5. 需求统计

**GET** `/api/requirements/stats`

获取需求统计信息。

**查询参数：**
- `session_id`: 会话 ID（可选，统计指定会话）

**响应示例：**
```json
{
  "total": 28,
  "by_level": {
    "L1": 5,
    "L2": 12,
    "L3": 11
  }
}
```

## 使用流程

### 1. 前提条件

确保已完成前两个阶段：
- 阶段一：预处理与解析（spans 已入库）
- 阶段二：上下文构建（span_links 已生成，可选）

### 2. 启动服务

```powershell
# 启动数据库
docker-compose up -d postgres

# 启动推理后端
cd backend_inference
python main.py

# 启动业务后端
cd backend_business
python app.py
```

### 3. 调用抽取接口

```python
import requests

# 对 session 进行需求抽取
response = requests.post(
    "http://localhost:5000/api/requirements/extract_l123",
    json={
        "session_id": "session_001",
        "bundle_strategy": "sequence",
        "anchor_strategy": "informative",
        "r": 2,
        "model": "deepseek-chat"
    }
)

result = response.json()
print(f"抽取完成，插入 {result['total_inserted']} 条需求")
```

### 4. 查询结果

```python
# 查询所有需求
response = requests.get(
    "http://localhost:5000/api/requirements/session/session_001"
)

requirements = response.json()["requirements"]

# 按层级查询
response = requests.get(
    "http://localhost:5000/api/requirements/session/session_001?level=L1"
)
```

## 测试

运行测试脚本：

```powershell
cd tests
python test_requirements_extraction.py
```

该脚本会演示：
1. EgoBundle 生成器的使用
2. 需求执行器的校验逻辑
3. Prompt 构建示例

## 配置参数建议

### 序列窗口策略（推荐起步配置）
```json
{
  "bundle_strategy": "sequence",
  "anchor_strategy": "informative",
  "r": 2,
  "max_spans_per_bundle": 12,
  "token_limit": 1500
}
```

### 图邻域策略
```json
{
  "bundle_strategy": "graph",
  "anchor_strategy": "all",
  "r": 1,  // 1-hop 或 2-hop
  "top_m_2hop": 5
}
```

### 模型参数
```json
{
  "model": "deepseek-chat",
  "temperature": 0.3,  // 降低温度以获得更稳定输出
  "max_tokens": 2000
}
```

## 架构特点

### 1. 证据不可变
- Spans 表保持只读/追加
- 需求抽取结果存入独立的 requirements_l123 表
- 通过 anchor_span_id 保持溯源关系

### 2. 防幻觉机制
- 使用短引用（S1..Sn）降低 UUID 幻觉风险
- 严格的参数校验（level、text 长度、数量上限）
- L3 引导性措辞（建议使用"系统必须/应当/shall"等）
- 自动去重（fingerprint）

### 3. 可复现性
- 记录 anchor_span_id 和 r 参数
- 可追溯每条需求的来源上下文
- 支持重跑和调参优化

### 4. 灵活性
- 支持两种 bundle 生成策略
- 支持三种锚点选择策略
- 可配置的数量和长度限制

## 后续扩展

1. **工具调用增强**：支持模型原生的 function calling
2. **证据链追溯**：新增 requirement_evidence 表关联具体 spans
3. **需求分类**：利用现有分类引擎对需求进行自动分类
4. **冲突检测**：利用现有冲突检测服务识别需求间的冲突
5. **可视化**：前端展示需求关联图和证据链

## 相关文件

- `mission.txt` - 完整设计文档
- `backend_business/services/ego_bundle_generator.py` - Bundle 生成器
- `backend_business/services/requirements_executor.py` - 执行器与校验器
- `backend_business/services/requirements_extraction_service.py` - 抽取服务
- `backend_business/routes/requirements_route.py` - API 路由
- `backend_inference/routers/chat.py` - 推理接口（新增 completions）
- `tests/test_requirements_extraction.py` - 测试脚本
