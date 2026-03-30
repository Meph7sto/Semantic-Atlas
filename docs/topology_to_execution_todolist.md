# 拓扑图→执行图映射 — 分阶段 TODO

> **目标**：按 `docs/implementation_plan.md`（v3）完成从**执行拓扑图（静态模板）**到**运行时执行图（动态轨迹）**的通用映射引擎。
>
> **策略**：保留现有 `TopologyExecutionService`（老模式）不动，新建独立实现。前端提供手动切换：**"执行图模式"（新）** vs **"经典模式"（老）**。
>
> **日期**：2026-03-20 创建

---

## 现状盘点

| 模块 | 状态 | 说明 |
|------|------|------|
| `ToolLoopRunner` | ✅ 可复用 | `complete_phase` + `route_key` + Scratchpad 集成已完备 |
| `Scratchpad` | ✅ 可复用 | 三类写入（note / tool_excerpt / stage_output）+ `format_for_prompt()` |
| DB Schema | ✅ 已就绪 | 五张表均已建好（graphs / containers / subgraphs / nodes / edges） |
| `TopologyExecutionService` | ✅ 保留不动 | 老模式，继续作为经典模式运行 |
| `topology_instantiator.py` | ✅ 已完成 | 骨架实例化器 + RuntimeGraphSkeleton 数据类 |
| `subgraph_runner.py` | ✅ 已完成 | Subgraph 运行时推进引擎（含 run / resume） |
| `subgraph_state.py` | ✅ 已完成 | Subgraph 四态 + Graph 五态状态机定义 |
| `graph_executor.py` | ✅ 已完成 | 顶层编排（调用 Instantiator + Runner）+ ExecutionResult + IntentJudge |
| 意图判断门控节点 | ✅ 已实现 | `IntentJudge` 类已定义 + 已集成到 `ConflictDetectionAgentService` |
| 前端模式切换 | ✅ 已实现 | 执行图模式 / 经典模式切换 UI |
| subgraph `status` 字段 | ✅ 已修复 | `execution_subgraphs` 表已含 status 列 + CRUD 已补全 |
| 自动化测试 | ✅ 已编写 | `test_graph_executor.py`（14 个用例全通过） |

---

## 阶段一：数据层 & 状态机定义

> **目标**：为新引擎建立数据基础和状态约束，不涉及任何运行时逻辑。

### 1.1 Subgraph 表增加 `status` 字段

- [x] 在 `execution_schema.py` 中为 `execution_subgraphs` 表添加 `status` 列
  - 类型：`TEXT NOT NULL DEFAULT 'pending'`
  - CHECK 约束：`status IN ('pending', 'running', 'completed', 'failed')`
  - 编写 migration（`ALTER TABLE ... ADD COLUMN IF NOT EXISTS`）
- [x] 验证：现有拓扑模板的 subgraph 不受影响（默认值 `pending`）
- [x] `_subgraph_repository.py` CRUD 操作补全 `status` 字段
- [x] `execution_edges` 表 edge_type CHECK 约束增加 `seq` 类型 + migration

### 1.2 创建 `subgraph_state.py` — 状态机定义

- [ ] 新建 `services/agent/execution/subgraph_state.py`
- [ ] 定义 Subgraph 四态枚举：`PENDING | RUNNING | COMPLETED | FAILED`
- [ ] 定义 Graph 五态枚举：`RUNNING | WAITING | SUSPENDED | SUCCEEDED | FAILED`
- [ ] 实现 Subgraph 状态转移验证函数 `validate_subgraph_transition(current, target) -> bool`
  - `PENDING → RUNNING`
  - `RUNNING → COMPLETED`
  - `RUNNING → FAILED`
- [ ] 实现 Graph 状态派生函数 `derive_graph_status(subgraphs, containers) -> GraphStatus`
  - 任何 subgraph 因 invoke 等待 return → `WAITING`
  - 任何 subgraph 因 handoff 挂起 → `SUSPENDED`
  - return 边到达 / 用户输入到达 → `RUNNING`
  - 所有 container 的末尾 subgraph 均 Completed → `SUCCEEDED`
  - 不可恢复错误 → `FAILED`

### 1.3 定义异常类型

- [ ] 在 `subgraph_state.py` 或独立文件中定义：
  - `SuspendSignal(subgraph_id)` — handoff subgraph 触发挂起
  - `ContainerExecutionError(container_id, subgraph_id, cause)` — container 执行失败

### 1.4 单元测试 — 状态机

- [ ] 编写 `tests/agent_chat/test_subgraph_state.py`
  - 四态合法转移全覆盖
  - 非法转移断言拒绝
  - Graph 派生状态在各种 subgraph 组合下正确

### ✅ 阶段一完成标准

- [ ] `execution_subgraphs` 表有 `status` 字段，现有数据不受影响
- [ ] 状态机枚举和转移验证可被后续阶段直接引用
- [ ] 所有状态机单元测试通过

---

## 阶段二：骨架实例化（TopologyInstantiator）

> **目标**：实现纯数据变换——输入拓扑图模板，输出全部 subgraph 为 Pending 的运行时执行图骨架。

### 2.1 创建 `topology_instantiator.py`

- [x] 新建 `services/agent/execution/topology_instantiator.py`
- [x] 实现 `TopologyInstantiator` 类，核心方法 `instantiate(template_graph_id) -> RuntimeGraphSkeleton`
- [x] 实例化步骤（纯确定性，不涉及 LLM）：
  1. [x] 分配 `graph_id`，创建运行时执行图（`graph_type='agent_runtime_execution'`、`status='running'`）
  2. [x] 遍历拓扑 container → 创建运行时 container（继承 `role_type`、`container_key`）
  3. [x] 遍历拓扑节点 → 创建运行时 subgraph（`status='pending'`），每个 subgraph 自动注入 start/end 节点对
  4. [x] 遍历边 → 创建运行时边
     - container 内 `seq` 边就绪
     - 跨容器 `call` / `return` / `retry` 标记 Inactive
  5. [x] 返回包含完整骨架的 `RuntimeGraphSkeleton` 数据结构

### 2.2 定义 `RuntimeGraphSkeleton` 数据类

- [x] 设计不可变数据结构（`@dataclass(frozen=True)` 或类似），包含：
  - `graph_id: str`
  - `containers: list[RuntimeContainer]`
  - `subgraphs: list[RuntimeSubgraph]`（每个含 `status='pending'`）
  - `nodes: list[RuntimeNode]`
  - `edges: list[RuntimeEdge]`
  - 便捷查询方法：
    - `get_entry_container() -> RuntimeContainer`
    - `get_subgraphs_for_container(container_id) -> list[RuntimeSubgraph]`（按 order_index 排序）
    - `get_outgoing_edges(subgraph_id) -> list[RuntimeEdge]`

### 2.3 拓扑节点 → subgraph 映射规则

- [x] 拓扑图中的每个业务节点（`node_type` 为 `llm` / `invoke` / `handoff`）映射为一个运行时 subgraph
- [x] 每个 subgraph 内自动注入 `start` 节点和 `end` 节点
- [x] 拓扑节点的 `task_prompt` 原样挂载到对应 subgraph 的 `task_description`
- [x] 拓扑节点的 `conditional_edges` 原样挂载到对应 subgraph 的 config 中
- [x] 拓扑节点的 `phase_label` 映射为 subgraph 的 `label`

### 2.4 单元测试 — 骨架实例化

- [x] 编写 `tests/agent_chat/test_topology_instantiator.py`
  - 3 节点拓扑图 → 3 个 subgraph + 自动 start/end 节点
  - container 继承关系正确
  - 边类型正确（seq vs call/return）
  - 所有 subgraph 初始状态均为 `pending`
  - 空模板 / 无效模板抛出清晰错误

### ✅ 阶段二完成标准

- [x] 给定任意合法拓扑模板，`instantiate()` 能生成正确的骨架
- [x] 骨架中所有 subgraph 的 `status='pending'`，graph 的 `status='running'`
- [x] 所有单元测试通过
- [x] 骨架数据已持久化到 DB

---

## 阶段三：运行时推进引擎（SubgraphRunner）

> **目标**：以 subgraph 为单位驱动运行时执行图推进，实现 `run()` / `resume()` / 条件路由 / 跨容器调用。

### 3.1 创建 `subgraph_runner.py`

- [x] 新建 `services/agent/execution/subgraph_runner.py`
- [x] 实现 `SubgraphRunner` 类

### 3.2 实现 `run()` — 全新执行

- [x] 接受参数：`skeleton`、`tool_executor`、`ai_proxy_client`、`actor`
- [x] 从入口 container 的第一个 Pending subgraph 开始
- [x] 调用 `_execute_container()` 推进 container 内全部 subgraph

### 3.3 实现 `_execute_container()` — container 级编排

- [x] 创建 container 级 `Scratchpad` 实例（container 内所有 subgraph 共享）
- [x] 按 `order_index` 排序 subgraph 后逐个推进
- [x] 调用 `_advance_subgraph()` 推进单个 subgraph
- [x] 处理条件路由：`_resolve_next_subgraph()` 决定下一个 subgraph
- [x] 返回末尾 subgraph 的 `complete_phase conclusion`（return 边回流的唯一内容）

### 3.4 实现 `_advance_subgraph()` — 单 subgraph 推进

- [x] **`llm` 类型**：
  - 构造上下文：`task_prompt` + `scratchpad.format_for_prompt()`
  - 启动 `ToolLoopRunner`（`enable_complete_phase=True`）
  - `complete_phase` 的 conclusion 自动追加到 Scratchpad
  - 返回 `route_key`（可能为 None）
  - 标记 subgraph 为 `completed`
- [x] **`invoke` 类型**：
  - 从 start 节点读取 payload
  - 沿 `call` 边找到目标 container
  - **同步阻塞**执行目标 container 的全部 subgraph（递归调用 `_execute_container`）
  - `return` 边的结论注入当前 subgraph 上下文
  - 标记 subgraph 为 `completed`
- [x] **`handoff` 类型**：
  - subgraph 保持 `running`，不标记 completed
  - 抛出 `SuspendSignal(subgraph_id=...)`
  - graph 状态由上层派生为 `Suspended`

### 3.5 实现 `_resolve_next_subgraph()` — 条件路由

- [x] 如果拓扑节点有 `conditional_edges` 且 `route_key` 非空：逐一比对，激活第一条匹配的目标 subgraph
- [x] 否则沿 `seq` 边无条件流转到下一个 subgraph
- [x] 无匹配时返回 `None`（container 执行结束）

### 3.6 实现 `resume()` — 从 Suspended 恢复

- [x] 加载已有执行图
- [x] 定位状态为 `running` 的 `handoff` subgraph（即挂起点）
- [x] 将 `user_input` 注入该 subgraph 的上下文
- [x] 标记该 subgraph 为 `completed`
- [x] 解析后续 subgraph，继续推进

### 3.7 上下文管理

- [x] 每个 container 持有一个 `Scratchpad` 实例
- [x] subgraph 切换时，下游 subgraph 的 start 节点注入 `scratchpad.format_for_prompt()` 作为跨阶段上下文
- [x] Scratchpad 是 container 内部的工作记忆，**不对外暴露**
- [x] return 边回流的唯一内容是末尾 subgraph 的 `complete_phase conclusion`

### 3.8 单元测试 — 运行时推进

- [x] 编写 `tests/agent_chat/test_subgraph_runner.py`
  - llm subgraph：Pending → Running → Completed
  - handoff subgraph：触发 `SuspendSignal`
  - invoke subgraph：同步跨容器调用 + return 回流
  - 条件路由：`route_key` 匹配正确的目标
  - Scratchpad 蒸馏：上游 conclusion 自动追加，下游 start 读取
  - `resume()` 从挂起点继续推进

### ✅ 阶段三完成标准

- [x] `run()` 可以驱动单 container 内多个 subgraph 顺序执行
- [x] `invoke` subgraph 可以同步阻塞调用另一个 container
- [x] `handoff` subgraph 正确挂起，`resume()` 正确恢复
- [x] 条件路由按 `route_key` 正确匹配
- [x] 所有单元测试通过

---

## 阶段四：顶层编排 & 意图判断门控

> **目标**：实现 `GraphExecutor` 顶层入口，整合 Instantiator + Runner，并加入意图判断门控节点。

### 4.1 创建 `graph_executor.py` — 顶层编排

- [x] 新建 `services/agent/execution/graph_executor.py`
- [x] 实现 `GraphExecutor` 类，对外暴露统一接口：
  - `execute(template_graph_id, user_message, tool_executor, ai_proxy, actor) -> ExecutionResult`
  - `resume(graph_id, user_input, tool_executor, ai_proxy, actor) -> ExecutionResult`
- [x] `execute()` 内部流程：
  1. [x] 调用 `TopologyInstantiator.instantiate()` 生成骨架
  2. [x] 调用 `SubgraphRunner.run()` 推进执行
  3. [x] 捕获 `SuspendSignal`，返回 `Suspended` 状态
  4. [x] 捕获异常，标记 graph 为 `Failed`
  5. [x] 正常结束，标记 graph 为 `Succeeded`
- [x] `resume()` 内部流程：
  1. [x] 验证 graph 当前状态为 `Suspended`
  2. [x] 委托 `SubgraphRunner.resume()`
  3. [x] 同样处理 `SuspendSignal` 和异常

### 4.2 Graph 状态派生集成

- [x] 在 `GraphExecutor` 执行结束时，调用 `derive_graph_status()` 更新 graph 状态
- [x] 确保状态更新持久化到 DB

### 4.3 意图判断门控节点（`intent_judge`）

- [x] 定义 `IntentJudge` 类（`graph_executor.py` 内）：
  - 轻量 LLM 调用，判断 `is_relevant: bool`
  - 解析失败 / API 异常时保守返回 `True`
- [x] 编写 intent 判断 prompt（参照 implementation_plan.md 中的示例）
- [x] intent_judge 节点属性：
  - `node_key = 'intent_judge'`
  - `node_type = 'llm'`
  - `role_type = 'agent'`
  - `container_key = 'conflict_detection_agent'`
- [x] 集成到 `ConflictDetectionAgentService`（已完成）

### 4.4 `ExecutionResult` 数据结构

- [x] 定义不可变返回值结构：
  - `status: str`（succeeded / suspended / failed）
  - `graph_id: str`
  - `final_output: str | None`
  - `suspended_subgraph_id: str | None`
  - `error: str | None`

### 4.5 单元测试 — 顶层编排

- [x] 编写 `tests/agent_chat/test_graph_executor.py`
  - 完整 happy-path：模板 → 骨架 → 推进 → Succeeded
  - handoff 挂起 → resume 恢复 → Succeeded
  - 执行失败 → Failed 状态正确
  - 意图判断 `is_relevant=false` 时不实例化拓扑图
  - 意图判断 `is_relevant=true` 时正常走拓扑映射

### ✅ 阶段四完成标准

- [x] `GraphExecutor` 是新模式的唯一入口
- [x] 意图判断门控正确工作
- [x] 所有状态（Succeeded / Suspended / Failed）正确持久化
- [x] `resume()` 可以从 Suspended 恢复完整流程
- [x] 所有单元测试通过

---

## 阶段五：前端集成 & 端到端验证

> **目标**：前端增加执行模式切换 UI，并进行端到端验证，确保新引擎在真实环境中正确工作。

### 5.1 前端执行模式切换

- [x] 在 agent 聊天界面添加 **"执行模式"** 选择器（下拉 / Toggle）：
  - `执行图模式`（新引擎，调用 `GraphExecutor`）
  - `经典模式`（老引擎，调用 `TopologyExecutionService`）
- [x] 模式选择持久化到用户偏好 / Session 级
- [x] 后端 API 路由根据 `execution_mode` 参数分发到对应引擎

### 5.2 Traceability 视图适配

- [x] 执行图详情页按 **subgraph** 组织展示执行轨迹（而非扁平节点列表）
- [x] 每个 subgraph 展示：
  - 状态（Pending / Running / Completed / Failed）
  - 阶段任务（`task_prompt`）
  - Scratchpad 条目
  - ToolLoopRunner 的工具调用记录
- [x] 跨容器调用（invoke → call → return）在视图中以视觉化方式呈现

### 5.3 端到端手动验证

- [ ] **验证项 1**：前端拓扑图编辑器创建的模板能被新引擎正确实例化
- [x] **验证项 2**：前端 "执行模式切换" 按钮工作正常
- [x] **验证项 3**：Traceability 视图正确展示按 subgraph 组织的执行轨迹
- [x] **验证项 4**：经典模式不受新引擎影响，老测试全部通过
- [ ] **验证项 5**：handoff 挂起 → 用户输入 → resume 恢复完整流程

### 5.4 端到端自动化测试

- [x] 编写集成测试：从 API 层发起完整的 模板创建 → 实例化 → 推进 → 完成 流程
- [x] 确保老模式测试不受回归：
  ```bash
  python -m pytest tests/agent_chat/test_topology_execution_service.py -v
  ```
- [x] 新模式测试覆盖：
  ```bash
  python -m pytest tests/agent_chat/test_graph_executor.py -v
  ```

### 5.5 文档与清理

- [ ] 更新 `implementation_plan.md` 中的实现清单（勾选已完成项）
- [ ] 为新引擎编写 README 或使用说明
- [ ] 清理临时代码 / TODO 注释

### ✅ 阶段五完成标准

- [x] 前端可以在两种模式间无缝切换
- [ ] 新引擎端到端流程在真实环境中验证通过
- [x] 老模式无回归
- [ ] 所有手动验证项通过
- [ ] 文档更新完毕

---

## 实现文件清单

| 阶段 | 文件 | 操作 |
|------|------|------|
| 一 | `services/db_service_parts/schemas/execution_schema.py` | 修改 — subgraph 增加 status |
| 一 | `services/agent/execution/subgraph_state.py` | **新建** — 状态机 + 异常 |
| 一 | `tests/agent_chat/test_subgraph_state.py` | **新建** — 状态机测试 |
| 二 | `services/agent/execution/topology_instantiator.py` | **新建** — 骨架实例化器 |
| 二 | `tests/agent_chat/test_topology_instantiator.py` | **新建** — 实例化测试 |
| 三 | `services/agent/execution/subgraph_runner.py` | **新建** — 运行时推进引擎 |
| 三 | `tests/agent_chat/test_subgraph_runner.py` | **新建** — 推进引擎测试 |
| 四 | `services/agent/execution/graph_executor.py` | **新建** — 顶层编排 |
| 四 | `tests/agent_chat/test_graph_executor.py` | **新建** — 编排测试 |
| 五 | `前端 agent 界面（Vue 组件）` | 修改 — 模式切换 UI |
| 五 | `后端 API 路由` | 修改 — 根据模式分发 |

## 依赖关系

```mermaid
graph LR
    A["阶段一<br/>数据层 & 状态机"] --> B["阶段二<br/>骨架实例化"]
    B --> C["阶段三<br/>运行时推进"]
    C --> D["阶段四<br/>顶层编排 & 门控"]
    D --> E["阶段五<br/>前端集成 & E2E"]

    style A fill:#4a90d9,color:#fff
    style B fill:#50b77a,color:#fff
    style C fill:#e6a23c,color:#fff
    style D fill:#f56c6c,color:#fff
    style E fill:#9b59b6,color:#fff
```

## 保留不动的文件

| 文件 | 说明 |
|------|------|
| `topology_execution_service.py` | 老模式，完整保留 |
| `tool_loop_runner.py` | 直接复用，llm subgraph 的内部引擎 |
| `scratchpad.py` | 直接复用，三类写入已完备 |
| Session 链（`session_id` / `prev_graph_id`） | 执行图已有现成实现，新引擎直接沿用 |
