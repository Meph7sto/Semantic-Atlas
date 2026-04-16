# Multi-Agent 协同架构总结

> 本文档根据当前代码实际情况整理，覆盖 `backend_business/services/agent` 与相关路由的现状。已删除的 `messaging/` 与 `sidebar/` 不再属于现行架构。

---

## 一、当前总体分层

```text
┌────────────────────────────────────────────────────────────┐
│ 会话 / API 层                                             │
│ agent_chat / session_controller / conflict / classification│
├────────────────────────────────────────────────────────────┤
│ Agent 服务层                                              │
│ SessionControllerService / RequirementAgent / ...         │
├────────────────────────────────────────────────────────────┤
│ 执行编排层                                                │
│ GraphExecutor / SubgraphRunner / ToolLoopRunner           │
│ TopologyInstantiator / TopologyExecutionService           │
├────────────────────────────────────────────────────────────┤
│ 领域状态层                                                │
│ RequirementActor + ActorManager + EventStore              │
├────────────────────────────────────────────────────────────┤
│ 数据与轨迹层                                              │
│ PostgreSQL: chat session / execution graph / event store  │
└────────────────────────────────────────────────────────────┘
```

- 会话层负责 session、SSE 输出、权限校验、图链查询。
- Agent 服务层负责各类专职 Agent 的 prompt、tool loop、图记录和上下文策略。
- 执行编排层负责把拓扑模板实例化为运行时图，或直接驱动单轮/多轮工具调用。
- 领域状态层当前核心仍是 RequirementActor，负责需求状态权威写入。

---

## 二、拓扑图与静态建模

### 2.1 核心对象

| 对象 | 当前作用 |
|------|------|
| `Container` | 拓扑中的职责边界，运行时映射为 execution graph container |
| `Node` | 模板中的节点定义，包含 `node_type` / prompt / schema / config |
| `Edge` | 容器间或节点间连线，支持 `seq` / `call` / `return` / `retry` 等 |

### 2.2 当前稳定支持的业务节点

当前新执行链路 `TopologyInstantiator` 和 `StructureValidator` 稳定支持的业务节点是：

| node_type | 含义 |
|------|------|
| `llm` | 一个可多轮 tool-call 的阶段 |
| `invoke` | 跨容器调用阶段 |
| `handoff` | 等待用户补充输入的挂起阶段 |

补充说明：

- `start` / `end` 在新执行链路里主要是运行时自动注入的边界节点。
- `topology/node_handlers/decision_handler.py` 仍然存在结构定义代码，但当前主执行链路并未把 `decision` 作为稳定业务子图节点支持；文档不再把它视为现网能力。

### 2.3 Container 角色类型

| role_type | 语义 |
|------|------|
| `human` | 用户介入点 |
| `agent` | LLM/Agent 容器 |
| `system` | 系统容器、状态管理或校验容器 |

### 2.4 跨容器边

- `call`：父容器调用子容器。
- `return`：子容器完成后把结果回流到父容器。
- `retry`：带条件或约束的重试路径。
- `seq`：同一路径中的顺序推进。

---

## 三、运行时执行图

### 3.1 新主执行链路

```text
用户消息
  ↓
GraphExecutor
  ├── 可先运行 judge 节点，判断是否展开拓扑
  ├── TopologyInstantiator 将模板实例化为 runtime graph skeleton
  └── SubgraphRunner 按 subgraph 推进执行
```

新链路的几个关键点：

- `GraphExecutor` 支持两种分支：
  - 直接回复：judge 判断任务简单，不展开拓扑。
  - 展开拓扑：选择模板后，在同一 runtime graph 内继续执行。
- `TopologyInstantiator` 会把模板中的业务节点映射为 `RuntimeSubgraph`，并为每个 subgraph 自动注入 `start/end` 运行时节点。
- `SubgraphRunner` 按 subgraph 顺序驱动 `llm / invoke / handoff` 三类阶段。

### 3.2 Subgraph 的职责

`Subgraph` 是当前运行时的最小阶段单元：

- 对外承诺一个稳定的阶段输入 / 输出。
- 对内允许多轮 LLM + tool call。
- 通过 `complete_phase` 工具显式完成阶段。

### 3.3 Scratchpad

Scratchpad 是当前容器级共享工作记忆：

- 同一容器内的多个 subgraph 可读写。
- 常见条目类型包括 `note`、`tool_excerpt`、`stage_output`。
- Session controller 会把跨轮摘要写入 graph meta 中的 `scratchpad_entries`。
- 新一轮 graph 可通过 `prev_graph_id` 继承上一轮 scratchpad。

### 3.4 执行状态

**Graph 级状态：**

| 状态 | 含义 |
|------|------|
| `running` | 正在执行 |
| `waiting` | 有 `invoke` 子图在推进 |
| `suspended` | 卡在 `handoff` 等待用户输入 |
| `succeeded` | 正常完成 |
| `failed` | 执行失败 |

**Subgraph 级状态：**

`pending` → `running` → `completed` / `failed`

---

## 四、当前多 Agent 协作方式

### 4.1 不是 MessageBus，而是工具内联委托

当前代码里已经没有 `MessageBus + Channel` 运行链路。现行协作方式是：

```text
SessionController LLM
  ↓ 调用工具
invoke_requirement_agent / invoke_conflict_detection /
invoke_requirement_classification_agent
  ↓
SessionControllerTools
  ├── 在 execution graph 中创建 call 边
  ├── 内联执行被委托 Agent 的 tool loop
  ├── 记录子容器节点轨迹
  └── 创建 return 边并恢复父节点游标
```

这意味着：

- “多 Agent” 在当前实现里主要表现为多个专职 Agent service 的内联协作，不是进程间消息总线。
- 跨容器协作首先体现为 execution graph 里的 `call/return` 边，而不是独立的消息对象。

### 4.2 Session Controller 的职责

`SessionControllerService + SessionControllerTools` 是当前会话总控入口，负责：

- 浏览型查询：`list_requirements`、`search_requirements`
- 委托需求管理 Agent
- 委托冲突检测 Agent
- 委托需求分类 Agent
- 维护跨轮 scratchpad 摘要

### 4.3 Requirement Agent 与领域状态

需求写入并不是直接落数据库，而是经由：

```text
RequirementAgentTools
  ↓
RequirementAgentActorRuntime
  ↓
ActorManager.send_command(...)
  ↓
RequirementActor / EventStore
```

因此文档里的“写入口唯一”仍基本成立：需求类状态变更仍以 Actor 命令为中心。

### 4.4 冲突检测与分类 Agent

- `ConflictDetectionAgentService` 同时保留：
  - classic tool-loop 路径
  - graph executor 路径
- `RequirementClassificationAgentService` 当前主要是独立 tool-loop Agent，可被 Session Controller 内联委托。

### 4.5 旧执行器仍存在

`TopologyExecutionService` 仍被 `execution_graph` 路由使用，用于“模板克隆后单路径执行”。它和 `GraphExecutor + SubgraphRunner` 是两套并存实现：

- `TopologyExecutionService`：偏旧，按模板节点直接克隆并执行单一路径。
- `GraphExecutor`：偏新，带 judge、subgraph、scratchpad、complete_phase 等能力。

---

## 五、会话链与上下文继承

```text
session_id
  └── active_graph_id
        ├── 当前图若 suspended，则继续在原图 resume
        └── 当前图若已完成，则新建 graph，并通过 prev_graph_id 串联
```

- 每轮消息通常对应一张新的 runtime graph。
- `prev_graph_id` 用来形成图链。
- `active_graph_id` 标记 session 当前活跃图。
- `prompt_payload_format`、`context_mode` 由各 Agent session 配置控制。

当前常见 `context_mode`：

- `full`
- `incremental`
- `scratchpad`

---

## 六、关键设计原则

1. **图即轨迹**：跨容器调用、阶段推进、工具执行都会尽量落到 execution graph 中。
2. **委托显式化**：Session controller 的“调用别的 Agent”要显式形成 `call/return` 轨迹。
3. **领域写入收口**：需求状态修改继续通过 Actor / EventStore 收口。
4. **上下文可继承**：通过 `prev_graph_id` 和 `scratchpad_entries` 保留多轮上下文。
5. **新旧链路并存**：当前仓库同时存在 `GraphExecutor` 新链路和 `TopologyExecutionService` 旧链路，文档必须区分主路径与兼容路径。

---

## 七、关键文件索引

| 文件 | 当前职责 |
|------|------|
| `backend_business/services/agent/execution/graph_executor.py` | 新执行主入口，负责 judge + 拓扑展开 + 运行结果汇总 |
| `backend_business/services/agent/execution/topology_instantiator.py` | 拓扑模板 → runtime skeleton |
| `backend_business/services/agent/execution/subgraph_runner.py` | 按 subgraph 推进 `llm/invoke/handoff` |
| `backend_business/services/agent/execution/tool_loop_runner.py` | 通用 LLM + tool call 循环，支持 `complete_phase` |
| `backend_business/services/agent/execution/topology_execution_service.py` | 旧版模板执行器，仍被 execution_graph 路由使用 |
| `backend_business/services/agent/runtime/graph_recorder.py` | 记录运行时 graph / node / edge / meta |
| `backend_business/services/agent/runtime/scratchpad.py` | 容器级 scratchpad |
| `backend_business/services/agent/agents/session_controller/service.py` | 会话总控 Agent service |
| `backend_business/services/agent/agents/session_controller/tools.py` | 会话总控的工具定义与内联委托实现 |
| `backend_business/services/agent/agents/requirement_agent/service.py` | 需求管理 Agent service |
| `backend_business/services/agent/agents/conflict_detection_agent/service.py` | 冲突检测 Agent service |
| `backend_business/services/agent/agents/requirement_classification_agent/service.py` | 需求分类 Agent service |
| `backend_business/services/agent/agents/requirement_agent/actor_runtime.py` | Requirement Agent 使用的 actor runtime 适配层 |
| `backend_business/services/agent/actor/actor_runtime.py` | 通用 Actor runtime，封装 ActorManager / EventStore / 协调器访问 |
