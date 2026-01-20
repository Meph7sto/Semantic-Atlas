# 需求抽取功能实现总结

## 完成情况

✅ **已完成** mission.txt 中"三、需求抽取"部分的完整实现

## 实现的功能模块

### 1. 数据库表结构
- ✅ 创建 `requirements_l123` 表
- ✅ 包含所有必需字段：req_id, session_id, level, text, fingerprint, anchor_span_id, r, created_at
- ✅ 添加索引和约束（level 枚举、text 长度、fingerprint 唯一性）

### 2. EgoBundle 生成器
**文件**: `backend_business/services/ego_bundle_generator.py`

- ✅ 实现序列窗口策略（anchor ± r）
- ✅ 实现图邻域策略（1-hop 和 2-hop）
- ✅ 三种锚点选择策略：all, keyword, informative
- ✅ 自动修剪 bundle（按数量和 token 限制）
- ✅ 短引用映射（S1..Sn）

### 3. 工具定义和约束
**文件**: `backend_business/services/requirements_executor.py`

- ✅ create_req 工具的 JSON Schema 定义
- ✅ 系统提示词生成
- ✅ 严格的约束规则：
  - level 枚举校验（L1/L2/L3）
  - text 长度校验（10-500 字）
  - 数量上限（L1≤2, L2≤5, L3≤8）
  - L3 引导性措辞（建议使用"系统必须/应当/shall"等）

### 4. 执行器和校验器
**文件**: `backend_business/services/requirements_executor.py`

- ✅ Toolcall 解析（支持 CALL 行格式）
- ✅ 参数校验（语法、长度、枚举）
- ✅ 数量上限检查
- ✅ 去重机制（fingerprint = sha256(session_id + level + normalized_text)）
- ✅ 批量插入和错误处理

### 5. 需求抽取服务
**文件**: `backend_business/services/requirements_extraction_service.py`

- ✅ 完整的端到端流程：
  1. 获取 session 的所有 spans
  2. 选择锚点集合
  3. 生成 EgoBundle
  4. 调用 Planner（大模型）
  5. 执行器校验并落库
- ✅ 支持两种 bundle 策略（sequence/graph）
- ✅ 支持三种锚点策略（all/keyword/informative）
- ✅ Prompt 自动构建
- ✅ 错误处理和日志记录

### 6. API 路由
**文件**: `backend_business/routes/requirements_route.py`

- ✅ POST `/api/requirements/extract_l123` - L1-L3 需求抽取
- ✅ GET `/api/requirements/session/{session_id}` - 查询需求列表
- ✅ GET `/api/requirements/{req_id}` - 需求详情
- ✅ DELETE `/api/requirements/{req_id}` - 删除需求
- ✅ GET `/api/requirements/stats` - 需求统计
- ✅ 保持向后兼容（原有的 `/extract` 接口）

### 7. 推理后端扩展
**文件**: `backend_inference/routers/chat.py`

- ✅ POST `/chat/completions` - 标准 chat completions 接口
- ✅ 支持多轮对话格式
- ✅ 支持 temperature 和 max_tokens 参数

### 8. 辅助工具
**文件**: `backend_business/services/ai_proxy.py`

- ✅ chat_completion 方法，调用推理后端

### 9. 测试和文档
- ✅ `tests/test_requirements_extraction.py` - 功能测试脚本
- ✅ `docs/requirements_extraction_guide.md` - 完整使用文档

## 创建的新文件

1. `backend_business/services/ego_bundle_generator.py` - EgoBundle 生成器
2. `backend_business/services/requirements_executor.py` - 需求执行器
3. `backend_business/services/requirements_extraction_service.py` - 需求抽取服务
4. `tests/test_requirements_extraction.py` - 测试脚本
5. `docs/requirements_extraction_guide.md` - 使用指南

## 修改的文件

1. `backend_business/services/db_service.py` - 添加 requirements_l123 表
2. `backend_business/routes/requirements_route.py` - 添加新的 API 接口
3. `backend_business/services/ai_proxy.py` - 添加 chat_completion 方法
4. `backend_inference/routers/chat.py` - 添加 /completions 接口

## 核心设计特点

### 1. 符合 mission.txt 规范
- ✅ EgoBundle 概念完整实现
- ✅ 序列窗口和图邻域两种策略
- ✅ 短引用映射机制
- ✅ Agent toolcall 模式
- ✅ 执行器的校验流程
- ✅ 去重和落库机制

### 2. 防幻觉设计
- ✅ 短引用（S1..Sn）降低 UUID 幻觉
- ✅ 严格参数校验
- ✅ L3 句式约束
- ✅ 数量上限控制

### 3. 可复现性
- ✅ 记录 anchor_span_id 和 r 参数
- ✅ fingerprint 去重
- ✅ 证据不可变原则

### 4. 工程化设计
- ✅ 模块化、可扩展
- ✅ 错误处理完善
- ✅ 日志记录
- ✅ 分页和过滤支持
- ✅ RESTful API 设计

## 使用示例

### 1. 启动服务
```powershell
# 数据库
docker-compose up -d postgres

# 推理后端
cd backend_inference
python main.py

# 业务后端
cd backend_business
python app.py
```

### 2. 调用 API
```python
import requests

# 需求抽取
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

# 查询结果
response = requests.get(
    "http://localhost:5000/api/requirements/session/session_001"
)

# 按层级查询
response = requests.get(
    "http://localhost:5000/api/requirements/session/session_001?level=L1"
)

# 统计信息
response = requests.get(
    "http://localhost:5000/api/requirements/stats?session_id=session_001"
)
```

### 3. 运行测试
```powershell
cd tests
python test_requirements_extraction.py
```

## 推荐配置

### 序列窗口策略（推荐起步）
```json
{
  "bundle_strategy": "sequence",
  "anchor_strategy": "informative",
  "r": 2,
  "model": "deepseek-chat"
}
```

### 图邻域策略（需要先运行 Phase 2）
```json
{
  "bundle_strategy": "graph",
  "context_run_id": "run_001",
  "anchor_strategy": "all",
  "r": 1,
  "model": "deepseek-chat"
}
```

## 后续优化建议

1. **工具调用增强**：支持模型原生的 function calling API
2. **证据链追溯**：新增 requirement_evidence 表
3. **批处理优化**：支持多个 session 批量抽取
4. **流式输出**：支持 streaming 模式，实时返回进度
5. **前端可视化**：展示需求层级关系和证据链

## 依赖要求

- Python 3.8+
- PostgreSQL
- psycopg2
- Flask
- FastAPI
- requests

所有依赖已在 `requirements.txt` 中定义。

## 注意事项

1. 确保已完成阶段一（spans 已入库）
2. 如果使用 graph 策略，需要先完成阶段二（span_links 已生成）
3. 推理后端必须配置可用的模型（本地或 API）
4. 数据库连接字符串需在环境变量中配置（POSTGRES_DSN）

## 完成日期

2026年1月19日

---

实现完全符合 mission.txt 中"三、需求抽取"的设计要求，可直接投入使用。
