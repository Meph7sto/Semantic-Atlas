# Agent 架构实现 TODO（对齐 `agent架构-Agent方案.md`）

> 本文档以 `docs/agent架构-Agent方案.md` 为准，替换旧版以 Sidebar SDK / Worker 为中心的拆分方式。  
> 新版目标是把工作拆成三条可并行推进的线路：`A. 模板与编排`、`B. Sidebar 与运行时`、`C. 领域读写与专项能力`。  
> 状态标记：`[ ]` 待做 · `[~]` 进行中 · `[x]` 已完成

---

## 一、对齐结论

- [x] **已具备的基础能力**：执行拓扑图基础 CRUD、结构构建/校验、`MessageBus`、`RequirementActor`、事件溯源、快照、基础 Agent 定义均已存在。
- [ ] **当前最大差距不是“有没有 Agent”**，而是**图模型和运行时语义还没完全对齐 Agent 方案**：
  - 当前 `ExecutionGraphService` 仍是 `graph + container + node + edge` 扁平模型。
  - 当前节点类型仍偏旧（如 `start / node / decision / handoff / end`），尚未对齐方案中的 `start / llm / handoff / invoke / end`。
  - 当前还没有把 `subgraph`、`seq`、`Waiting/Suspended`、`Checkpoint`、`tool-call → call/return/retry` 这些运行时语义完整打通。
- [ ] **旧版 TODO 中的部分项需要降级为“兼容层事项”而非主线目标**：
  - `capability-based routing`
  - Worker 健康检查 / 负载均衡
  - Worker 心跳
  - 通用 Worker 扩张
  - 这些能力可保留，但不再作为 Agent 主架构的完成标准。

---

## 二、三条并行线路总览

| 线路 | 核心目标 | 主要输出 | 对其他线路的接口 |
| ---- | -------- | -------- | ---------------- |
| A. 模板与编排 | 把 Agent 方案沉淀为可执行的静态模板 | 容器边界、subgraph、模板一/二/三、会话总控编排 | 向 B 提供容器入口和边语义；向 C 提供委托 payload 结构 |
| B. Sidebar 与运行时 | 把 tool call、执行图追踪、挂起恢复和并发汇合跑通 | 工具名到容器入口映射、call/return/retry 自动写边、Checkpoint、状态推进 | 消费 A 的模板定义；消费 C 的 Actor/Agent 结果 |
| C. 领域读写与专项能力 | 落实 RequirementActor 唯一写入口和两个只读专项 Agent | Requirements Agent、QA Agent、Conflict Agent、Version Fencing、约束闭环 | 消费 A 的模板与委托协议；通过 B 完成路由与追踪 |

并行原则：

- A 先定义静态结构，不等待 B/C 完全落地。
- B 优先打通最小运行链路，不等待所有专项 Agent 完成。
- C 先补齐“修改需求 + 自动质检”闭环，再扩展冲突检测。

---

## 三、线路 A：模板与编排层

> 目标：先把“会话总控统一编排 + 专项 Agent 单一职责 + container/subgraph 分层”沉淀为标准模板。

### A1. 图结构与模板模型升级

- [x] **执行图基础 CRUD 已完成**：`backend_business/services/execution_graph_service.py`
- [x] **结构构建器与边校验已完成**：`backend_business/services/agent/topology/`
- [ ] **图模型补齐 `subgraph` 层**：支持 `container -> subgraph -> node` 的三层结构，而不是只用扁平 node 表达所有语义。
- [ ] **节点类型升级**：将当前节点模型对齐为 `start / llm / handoff / invoke / end`。
- [ ] **边类型补齐**：在保留 container 级 `call / return / retry` 的同时，增加 subgraph 内部 `seq`。
- [ ] **兼容迁移策略**：明确旧节点类型（如 `decision` / `node`）如何映射到新模型，避免现有图模板直接失效。

### A2. 会话总控 Agent 对齐

- [~] **会话总控 Agent 已有定义**：`backend_business/services/agent/agents/conductor_agent.py`
- [ ] **意图识别对齐方案**：明确输入属于修改、质检、冲突检测、复合意图还是需澄清。
- [ ] **统一委托编排**：所有专项 Agent 协作都经由会话总控发起，不允许专项 Agent 之间直连。
- [ ] **重试决策节点**：支持“质检不通过 → 带约束重试需求修改”，上限 3 次。
- [ ] **挂起决策节点**：对 Actor 校验失败、信息不足、不可逆操作确认等场景进入 `handoff/Suspended`。
- [ ] **结果聚合节点**：会话总控负责把多个专项 Agent 返回结果合并为最终自然语言回复。

### A3. 专项 Agent 容器边界

- [~] **需求管理 Agent 已有定义**：`backend_business/services/agent/agents/requirements_agent.py`
- [ ] **需求管理 Agent 收敛为唯一写入口**：只负责创建/修改/补全需求，并通过 `RequirementActor` 落地。
- [ ] **新增质检 Agent 容器**：只读、不写，只输出结构化质量结论与修改约束。
- [ ] **新增冲突检测 Agent 容器**：只读、不写，只输出冲突报告与裁决依据。
- [ ] **显式禁止专项 Agent 互调**：模板层不允许 Requirements Agent 直接连到 QA/Conflict Agent。

### A4. 标准模板沉淀

- [ ] **模板一：修改需求 + 自动质检**
  - 最优先，作为首条端到端闭环。
- [ ] **模板二：修改需求 + 质检通过后检查冲突**
  - 在模板层显式建模串联路径，不在代码里隐式拼接。
- [ ] **模板三：需要用户澄清的挂起路径**
  - 把 `handoff` 和 `Suspended` 路径提前固化到模板中。
- [ ] **模板自动匹配与注入**
  - 会话总控根据意图选择模板，而不是把全部编排硬编码在 Runner 中。

### A5. 可复用 subgraph 库

- [ ] **需求管理 Agent subgraph**
  - `build_change_command`
  - `invoke_requirement_actor`
  - `summarize_write_result`
- [ ] **质检 Agent subgraph**
  - `load_latest_requirement`
  - `qa_dimension_review`
  - `qa_pass_decision`
- [ ] **冲突检测 Agent subgraph**
  - `collect_requirement_set`
  - `detect_conflicts`
  - `compose_conflict_report`

---

## 四、线路 B：Sidebar 与运行时

> 目标：把“tool call 路由 + 执行图事实沉淀 + Waiting/Suspended/恢复 + 会话内并发汇合”跑通。

### B1. Sidebar 职责收敛

- [x] **已有可复用基础设施**：
  - `backend_business/services/agent/messaging/`
  - `backend_business/services/agent/sidebar/sidebar.py`
- [ ] **Sidebar 从“能力路由”收敛为“静态工具路由”**
  - 工具名 → container 入口在启动时静态确定。
  - 会话总控只感知 `invoke_requirements_agent` / `invoke_qa_agent` / `invoke_conflict_agent` 这类工具语义。
- [ ] **明确降级项**
  - `capability_registry.py`
  - `health.py`
  - 负载均衡 / 健康检查 / 实例心跳
  - 这些不再是新版 Agent 方案主链路上的必要前置。

### B2. 跨容器消息协议

- [ ] **定义跨容器消息信封**
  - 至少包含 `session_id`、`graph_id`、调用方节点、目标容器、业务 payload、trace 元数据。
- [ ] **业务 payload 与追踪元数据分层**
  - 避免把路由字段混入 Agent 业务输入。
- [ ] **超时与失败语义显式化**
  - 通信级失败由 Sidebar 处理。
  - 业务失败（如 Actor 校验失败、质检不通过）回到会话总控决策。

### B3. 执行图事实自动写入

- [ ] **tool call 发出时自动写 `call` 边**
- [ ] **结果回流时自动写 `return` 边**
- [ ] **通信级重试时自动写 `retry` 边**
- [ ] **节点级 input/output 持久化**
  - 至少记录每个节点实际收到的 `input_messages` 和产出的结构化结果。
- [ ] **delta context 规则落地**
  - 后继节点默认只取直接前驱输出。
  - 按 tool 的 `context_mode` 控制结果是否向后传播。

### B4. 运行时状态机

- [ ] **执行图状态推进**
  - `Running`
  - `Waiting`
  - `Suspended`
  - `Succeeded`
  - `Failed`
- [ ] **Waiting 状态进入条件**
  - 发出跨容器调用后，等待 `return`。
- [ ] **Suspended 状态进入条件**
  - `handoff`
  - 重试耗尽
  - Actor 校验失败后需用户决策

### B5. Checkpoint 与恢复

- [ ] **Checkpoint 轻量索引**
  - 记录 `graph_id`、等待时间、pending task 列表。
- [ ] **按 `graph_id` 重建上下文**
  - 恢复时从执行图存储重建，而不是依赖内存态。
- [ ] **会话内恢复不新建执行图**
  - 用户补充输入后在原图上追加节点继续推进。
- [ ] **挂起恢复闭环**
  - `Suspended -> Running`
  - `Waiting -> Running`

### B6. 会话内并发汇合

- [ ] **并行调用计数器**
  - 一个节点内并发发起多个调用时维护 pending task 计数。
- [ ] **汇合缓冲区**
  - 所有结果回齐后统一注入下一节点输入。
- [ ] **多返回边收敛到同一汇合节点**
  - 不额外引入新的边类型。
- [ ] **异常汇合策略**
  - 明确是“立即中断整批”还是“等待剩余结果后统一上报”。

### B7. 开关、回退与观测

- [ ] **Sidebar 可开关**
  - 支持按环境或链路灰度启用。
- [ ] **执行图追踪可对账**
  - 路由记录、节点执行记录、最终回复能串成完整链路。
- [ ] **核心指标**
  - 路由成功率
  - 超时率
  - 重试率
  - 恢复成功率

---

## 五、线路 C：领域读写与专项能力

> 目标：落实 RequirementActor 唯一写入口，先完成“修改需求 + 自动质检”，再补齐冲突检测。

### C1. RequirementActor 与事件源基座

- [x] **RequirementActor 已实现**：`backend_business/services/actor/actors/requirement_actor.py`
- [x] **事件溯源已实现**：`backend_business/services/event_store/event_store.py`
- [x] **快照机制已实现**
- [x] **虚拟 Actor 生命周期已实现**：`backend_business/services/actor/actor_manager.py`
- [x] **状态机已实现**：`backend_business/services/actor/actors/state_machine.py`
- [~] **Actor 操作追踪目前仍偏开发态**
  - 已有 `backend_business/services/actor/dev_trace.py`
  - 需要正式接入执行图存储，而不是只做调试痕迹。

### C2. 读写边界收敛

- [x] **Actor Ask（强一致直读）已具备**
- [ ] **明确唯一写入口**
  - 只有需求管理 Agent 可以对 `RequirementActor` 发写 Command。
- [ ] **QA Agent / Conflict Agent 强制只读**
  - 只能通过 Actor Ask 获取最新状态。
- [ ] **禁止绕过 Actor 直写底层存储**
  - 现有异步执行器、任务队列、服务封装都要逐步收敛到 Actor 命令入口。

### C3. 强一致读取与版本栅栏

- [ ] **Version Fencing**
  - 读取时支持 `min_version` 栅栏。
- [ ] **质检链路按写后版本读取**
  - 需求修改成功后，把新版本作为 QA 读取下界。
- [ ] **冲突检测链路按最新状态批量读取**
  - 对一组需求做强一致读取和聚合。
- [ ] **必要时再补 `injected_context`**
  - 作为性能优化项，而不是第一阶段前置。

### C4. 需求管理 Agent 闭环

- [ ] **结构化变更命令生成**
  - 从用户意图或 QA 约束生成标准写 Command。
- [ ] **Actor 写入结果标准化**
  - 返回 `requirement_id`、`version`、修改摘要、失败原因。
- [ ] **Actor 业务约束失败显式化**
  - 例如 `Baselined/Locked` 不允许直接修改。
- [ ] **与会话总控重试闭环打通**
  - QA 不通过时回到需求管理 Agent，而不是直接失败。

### C5. 质检 Agent

- [ ] **质检 Agent 实现**
  - 输入：`requirement_id` + `min_version`
  - 输出：通过/不通过、维度评分、修改约束
- [ ] **高频 subgraph**
  - `load_latest_requirement`
  - `qa_dimension_review`
  - `qa_pass_decision`
- [ ] **重试约束标准化**
  - 质检结论要能直接作为需求管理 Agent 的下一轮输入。

### C6. 冲突检测 Agent

- [ ] **冲突检测 Agent 实现**
  - 输入：主需求 ID + 关联需求集合或检索条件
  - 输出：冲突报告、冲突级别、裁决依据
- [ ] **高频 subgraph**
  - `collect_requirement_set`
  - `detect_conflicts`
  - `compose_conflict_report`
- [ ] **明确不承担修复写入职责**
  - 如需自动修复，后续新增独立 Agent，不让冲突检测 Agent 越权。

---

## 六、跨线路对齐点

- [ ] **A → B**
  - 固定 container key、工具名、模板入口节点命名。
- [ ] **A → C**
  - 固定委托 payload 和结构化返回 schema。
- [ ] **B → C**
  - 固定 Actor/专项 Agent 的调用信封、超时、失败语义。
- [ ] **C → A**
  - 固定“修改结果”“质检结论”“冲突报告”的结构化输出，供模板节点引用。

---

## 七、联合里程碑

### M1：最小闭环可跑

- [ ] A1 图模型升级方案定稿
- [ ] A2 会话总控完成基础编排
- [ ] A4 模板一落地
- [ ] B1 静态工具路由跑通
- [ ] B3 `call/return` 自动写边
- [ ] C2 唯一写入口约束生效
- [ ] C4 需求管理 Agent 写入闭环可跑

### M2：修改需求 + 自动质检

- [ ] B4/B5 `Waiting`、`Suspended`、Checkpoint 打通
- [ ] C5 质检 Agent 落地
- [ ] 会话总控支持最多 3 次 QA 失败重试

### M3：复合意图与挂起恢复

- [ ] A4 模板二、模板三落地
- [ ] B6 会话内并发汇合
- [ ] C6 冲突检测 Agent 落地
- [ ] 原图恢复执行闭环打通

---

## 八、非主线但需处理的兼容事项

- [~] **保留现有 `MessageBus` 和 Sidebar 代码作为底层能力**，但不再把“能力路由/实例治理”当成 Agent 架构主目标。
- [ ] **评估旧 Worker/Task Queue 的定位**
  - 能复用于底层执行器的保留。
  - 会破坏“Agent 是静态图定义、RequirementActor 是唯一权威写入口”边界的部分，需要逐步收敛或下线。
- [ ] **清理文档表述**
  - 后续相关文档统一区分“执行拓扑模板”与“运行时执行图”，避免继续混用。
