# Agent 架构实现 TODO

> 本文档对照 `agent架构-主方案.md`，根据项目当前实现状态，列出各阶段需要完成的工作项。  
> 状态标记：`[ ]` 待做 · `[~]` 进行中 · `[x]` 已完成

---

## 一、Sidebar / 通信层

> 对应主方案 §1.2。当前有 `messaging/bus.py`（MessageBus）雏形，但与架构定义的 Sidebar 能力仍有差距。

- [ ] **将 MessageBus 重新定位为 Sidebar SDK**：梳理现有 `bus.py / router.py / middleware.py / channel.py` 与"逻辑 Sidebar"概念的对应关系，补充缺口，确保调用方只需 `sidebar.send({role, payload})`。
- [ ] **能力路由（Capability-Based Routing）**：Router 目前按 `agent_id` 直接寻址，需改为按 Worker/Agent 的"角色声明"路由，调度空闲且健康的实例。
- [ ] **健康检查与心跳**：Sidebar 层实现 Worker 心跳上报与超时检测；心跳中断时自动将任务重新投递，对上层业务代码不透明。
- [ ] **熔断 / 限流 / 重试**：目前 `middleware.py` 有 `RateLimitMiddleware` 骨架，需接入真正的熔断逻辑（最多重试 3 次，超限报 Suspended）。
- [ ] **执行图 span 自动注入**：Sidebar 在转发/接收消息时自动生成 `span_id`，记录跨容器边（调用边、返回边、重试边），与执行图存储打通，业务代码零感知。

---

## 二、会话层 Agent

> 对应主方案 §一。`agents/conductor_agent.py` 已有初步实现，但功能尚不完整。

- [~] **会话总控 Agent（Conductor）**：`conductor_agent.py` 已存在，但缺乏对无法匹配拓扑模板时的分支判断——需明确何时激活计划 Agent。
- [ ] **计划 Agent（Planner）**：目前完全缺失。需实现：意图拆解为有依赖关系的步骤序列、中间结果驱动的路径动态调整、重试/降级/澄清三条出口。
- [ ] **拓扑模板自动注入**：框架层在创建 AgentContainer 时，根据指令类型匹配计算拓扑图，将软建议注入第一个节点的 `injected_context`，无需 Agent 主动查询。
- [ ] **Dispatching 状态（用户确认等待）**：Agent 对不可逆写操作（如修改需求条目）需进入 `Dispatching` 状态，等待用户显式确认后继续执行，结果作为新节点增量输入。

---

## 三、领域层（RequirementActor）

> 对应主方案 §二。现有代码以 Service 形式操作 DB，缺乏 Actor 语义封装。

- [ ] **RequirementActor 类**：新建 `services/actor/requirement_actor.py`，封装单条需求的所有状态变更，外部只能通过 Command 交互，内部执行前置条件校验。
- [ ] **事件溯源（Event Sourcing）**：Actor 处理 Command 时追加不可变 Event 至事件流（Event Store），当前状态通过重放重建。需设计 Event 表结构与重放逻辑。
- [ ] **快照机制**：周期性写入快照，将重建复杂度从 O(n) 压缩为 O(k)；快照触发策略（按事件数/时间）待定。
- [ ] **虚拟 Actor 生命周期**：Command 到达时透明激活（重放事件流）；无消息时自动休眠释放内存；调用方始终以 `requirement_id` 寻址。
- [ ] **ActorContainer 记录**：每次 Actor 处理 Command 对应一个 `ActorContainer`（命令接收→校验→Event 写入→返回），纳入执行图存储。
- [ ] **Command Queue 可视化**：为每个 Actor 维护命令队列，排队等待的 Command 以"待处理"状态挂在执行图的 Actor 节点上。

---

## 四、Read-Your-Writes 强一致保障

> 对应主方案 §2.5。属于 Actor + CQRS 联合工作项。

- [ ] **Version Fencing**：Actor 每次成功处理 Command 后返回单调递增 `Version`；读模型查询接口支持 `min_version` 参数，未追平时阻塞等待。
- [ ] **Actor Ask（强一致直读）**：Agent 可向 Actor 发 `QueryCommand`，Actor 直接返回内存中最新状态快照，绕过读库，仅对内部核心逻辑开放。
- [ ] **增量上下文注入（injected_context）**：Worker 写回 Actor 后，在唤醒 Agent 的消息体中携带变更后的关键数据作为增量上下文，Agent 无需额外查询即可获得强一致数据。

---

## 五、执行层（Worker）

> 对应主方案 §三。`tasks/queue.py` 有任务队列雏形，各类 Worker 尚未完整实现。

- [~] **任务队列（Task Queue）**：`tasks/queue.py` 已有基础实现，需验证"至少一次"投递语义和幂等性约束。
- [ ] **LLM Worker**：封装 LLM 调用（构造 prompt → 调用 API → 解析结果 → 写回 Actor），各步骤作为 `WorkerStepNode` 记录在执行图中。
- [ ] **向量检索 Worker**：RAG 检索封装，供冲突检测、追溯等场景使用。
- [ ] **冲突矩阵计算 Worker**：跨需求语义相似度计算，支持并行多实例触发，汇合节点等待全部返回。
- [ ] **Worker 幂等性**：对同一 `task_id` 的重复执行不产生额外副作用，需在各 Worker 实现中统一校验。
- [ ] **Worker 心跳**：长耗时任务（LLM 调用等）定期发送心跳；心跳中断后对应 WorkerContainer 标记 `TimedOut`，重试上限 3 次，超限置执行图为 `Suspended`。
- [ ] **Worker 直写 Actor**：Worker 完成计算后可绕过 Agent 直接向 Actor 发 Command（如 `UpdateL4ContentCommand`），无需 Agent 中转。

---

## 六、专项业务 Agent

> 对应主方案 §5.1。目前只有 `conductor_agent.py` 和 `requirements_agent.py`，其余均缺失。

- [~] **需求细化 Agent**：`requirements_agent.py` 有雏形，需补充 L1→L4 逐层分解逻辑和各层质量评判标准。
- [ ] **质检 Agent（QA Agent）**：在提交、评审、基线等关键节点执行质量门禁（可测试性、完整性、冲突、歧义），输出带问题定位的结构化结论。
- [ ] **冲突检测 Agent**：跨需求语义分析，对 Worker 返回的候选冲突对做最终语义裁决。
- [ ] **追溯 Agent**：需求上下游关联关系的语义理解与覆盖性推断。
- [ ] **评审 Agent**：将自然语言评审反馈解析为结构化变更动作，处理意见合并/拆分决策。

---

## 七、执行图 / 图结构存储

> 对应主方案 §四.3 和 §六。`execution_graph_service.py` 已存在，但部分能力待补齐。

- [~] **执行图基础 CRUD**：`execution_graph_service.py` 已有基础实现，需核对与主方案定义的数据结构是否对齐（`graph_id`、节点、边）。
- [ ] **AgentNode 增量存储**：每个节点只持久化本节点**新增的增量信息**（delta messages + injected_context + output），不做全量快照；重建时按 `sequence_index` 顺序拼接。
- [ ] **cross_container_call 边自动生成**：Agent output type 为 `cross_container_call` 时，自动创建调用边和对应的 WorkerContainer/AgentContainer；返回时生成返回边。
- [ ] **重试边**：质检失败触发重试时，新建 WorkerContainer 并生成重试边，原容器保留并标注为重试源。
- [ ] **并行调用汇合节点**：Agent 同时发起多个 Worker 调用时，所有返回边收敛至同一个 AgentNode（汇合节点），Agent 维护 pending task 计数器。
- [ ] **执行图最终状态**：`Succeeded / Failed / Suspended` 三态流转，Suspended 时等待用户补充输入后从断点恢复。
- [ ] **计算拓扑图存储与引用**：拓扑图存储于执行图存储中，与执行图通过关联关系双向引用；执行图沉淀后可归纳新拓扑候选。

---

## 八、Agent Checkpoint 机制

> 对应主方案 §4.4 和 §7.3。

- [ ] **Checkpoint 写入**：Agent 每次进入 `Waiting` 前写入 Checkpoint（Agent 标识、挂起时间点、等待的 `task_id` 列表、`graph_id`）。
- [ ] **Checkpoint 恢复**：结果到达时，从执行图节点序列重建完整上下文，定位到挂起点后继续执行；Checkpoint 仅作"正在等待哪些 task"的查找入口。
- [ ] **Suspended → 恢复**：用户补充输入后，将新输入作为新节点的增量 input 追加到原 AgentContainer 节点序列末尾，推理循环重建完整上下文继续执行。

---

## 九、质检失败处理

> 对应主方案 §1.3。

- [ ] **自动重试（≤3 次）**：质检结论作为新约束重新触发 Worker，执行图产生重试边，原 WorkerContainer 标注为重试源。
- [ ] **挂起澄清**：3 次重试后仍失败，执行图置 `Suspended`，会话总控向用户说明卡滞质检项、已重试次数，附当前最优结果。

---

## 十、读模型（CQRS Read Model）

> 对应主方案 §4.2。

- [ ] **事件订阅投影**：订阅 Event Store 的事件流，异步更新各读模型（需求列表视图、详情视图、冲突视图、基线差异视图）。
- [ ] **读模型独立重建**：读模型损坏时可从事件流从头重放重建，不影响写入侧。
- [ ] **`min_version` 阻塞查询接口**：读接口支持传入 `min_version`，若投影未追平则阻塞等待或轮询，防止拉旧。

---

## 十一、RequirementActor 状态机

> 对应主方案 §7.1。

- [ ] **五态状态机实现**：`Draft → PendingReview → UnderReview → Approved/Rejected → Baselined/ChangeRequested`，转换函数为偏函数（非法命令直接拒绝）。
- [ ] **状态守卫**：所有状态迁移由 Actor 内部 Command 处理逻辑校验，外部无法绕过直接操作底层存储。

---

## 十二、前端（执行图可视化）

> 对应 `frontend/src/components/alpha/` 下已有组件，需与后端新图结构对齐。

- [~] **ExecutionGraphCanvas.vue**：已有画布组件，需核对节点/边数据格式与主方案定义的 AgentContainer / WorkerContainer / ActorContainer 是否对齐。
- [ ] **ActorContainer 可视化**：补充 Actor 节点的 Command Queue 排队状态展示。
- [ ] **重试边 / 并行汇合可视化**：在画布上区分展示重试边（虚线？）和并行汇合节点（多入边汇聚）。
- [ ] **Suspended 状态 UI**：执行图置为 Suspended 时，前端高亮挂起点，展示卡滞的质检项和当前最优结果，提供用户输入补充入口。
- [ ] **计算拓扑图浏览器**：`TopologyStructureViewer.vue` 已有雏形，需支持查看拓扑图与执行图的双向引用关系。
- [ ] **执行图与 Checkpoint 状态联动**：Waiting 中的 AgentContainer 在画布上实时展示等待中的 task_id 列表。

---

## 十三、端到端可观测性

> 对应主方案 §4.5 四类存储关联关系。

- [ ] **全链路追踪**：从用户指令出发，经执行图 → Actor 调用节点 → 事件流，实现端到端完整追溯，任何业务操作都能找到对应的执行图节点。
- [ ] **`call_node_id` 反向关联**：Actor 处理 Command 产生的 Event 反向携带触发它的执行图节点 ID（`call_node_id`）。
- [ ] **执行图归纳为拓扑候选**：沉淀完成的执行图可提名为新的计算拓扑模板，或对现有模板进行修订，形成闭环优化。

---

## 优先级建议

| 优先级 | 模块 | 理由 |
|--------|------|------|
| P0 | RequirementActor + Event Sourcing | 核心数据一致性保障，其他所有写操作的基础 |
| P0 | Checkpoint 机制 | Agent 异步等待和断点恢复的核心 |
| P1 | Worker 完整实现（LLM/RAG/冲突矩阵） | 执行层当前缺口最大 |
| P1 | 质检 Agent + 自动重试 | 质量门禁是需求工程流程的核心 |
| P1 | 执行图 AgentNode 增量存储对齐 | 当前存储方式与主方案存在偏差 |
| P2 | Capability-Based Routing（Sidebar） | 通信解耦，扩容友好 |
| P2 | 计划 Agent（Planner） | 非默认路径，优先级低于标准路径 |
| P2 | Read Model + Version Fencing | CQRS 最终一致性保障 |
| P3 | 前端执行图可视化补齐 | 可在功能稳定后持续迭代 |
| P3 | 拓扑归纳→候选模板闭环 | 优化型功能，最后实现 |
