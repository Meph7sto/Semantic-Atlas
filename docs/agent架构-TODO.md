# Agent 架构实现 TODO

> 本文档对照 `agent架构-主方案.md`，根据项目当前实现状态，列出各阶段需要完成的工作项。  
> 状态标记：`[ ]` 待做 · `[~]` 进行中 · `[x]` 已完成

---

## 一、Sidebar / 通信层

> 对应主方案 §1.2。目前已初步实现基于能力的 Sidebar SDK。

- [x] **能力路由（Capability-Based Routing）**：实现了按 Worker/Agent 的"角色声明"路由，支持负载均衡。
  - 实现文件：`backend_business/services/agent/sidebar/capability_registry.py`
- [x] **健康检查与状态监控**：Sidebar 层实现 Worker 健康检查（HTTP）与状态同步。
  - 实现文件：`backend_business/services/agent/sidebar/health.py`
- [x] **熔断 / 限流 / 重试**：实现了基于令牌桶的限流、三态熔断器以及指数退避重试策略。
  - 实现文件：`backend_business/services/agent/sidebar/middleware.py`
- [x] **Sidebar SDK 封装**：封装了 `MessageBus`，提供统一的 `sidebar.send({capability, payload})` 接口。
  - 实现文件：`backend_business/services/agent/sidebar/sidebar.py`
- [ ] **执行图 span 自动注入**：Sidebar 在转发/接收消息时自动生成 `span_id`，记录跨容器边，与执行图存储打通。

---

## 二、会话层 Agent

> 对应主方案 §一。目前已有基础 Runner 和部分 Agent 定义。

- [~] **会话总控 Agent（Conductor）**：已有定义，需补充对无法匹配拓扑模板时的分支判断——明确何时激活计划 Agent。
  - 定义文件：`backend_business/services/agent/agents/conductor_agent.py`
- [~] **通用执行循环（Agent Runner）**：实现了基于工具调用和 MessageBus 集成的通用执行逻辑。
  - 实现文件：`backend_business/services/agent/runner.py`
- [ ] **计划 Agent（Planner）**：目前完全缺失。需实现：意图拆解为有依赖关系的步骤序列、路径动态调整。
- [ ] **拓扑模板自动注入**：框架层在创建 AgentContainer 时，根据指令类型自动匹配并注入拓扑建议。
- [ ] **Dispatching 状态（用户确认等待）**：实现对不可逆操作的挂起等待机制。

---

## 三、领域层（RequirementActor）

> 对应主方案 §二。已完整实现虚拟 Actor 模式与事件溯源。

- [x] **RequirementActor 类**：封装单条需求状态，通过 Command 驱动变更，支持内存快照直读。
  - 实现文件：`backend_business/services/actor/actors/requirement_actor.py`
- [x] **事件溯源（Event Sourcing）**：实现事件仅追加、状态重放重建逻辑。
  - 实现文件：`backend_business/services/event_store/event_store.py`
- [x] **快照机制**：实现定期/手动快照，优化状态重建速度。
  - 实现文件：`backend_business/services/event_store/event_store.py`
- [x] **虚拟 Actor 生命周期**：实现 Actor 的透明激活、自动休眠（空闲回收）及分布式锁协调。
  - 实现文件：`backend_business/services/actor/actor_manager.py`
- [x] **RequirementActor 状态机**：实现严格的需求生命周期转换逻辑。
  - 实现文件：`backend_business/services/actor/actors/state_machine.py`
- [~] **ActorContainer 记录**：目前 Actor 操作已在 `dev_trace.py` 追踪，需正式接入执行图存储。
- [x] **Command Queue 审计**：实现了命令队列记录与状态更新。
  - 实现文件：`backend_business/services/event_store/event_store.py`

---

## 四、Read-Your-Writes 强一致保障

> 对应主方案 §2.5。利用 Actor 内存状态解决最终一致性问题。

- [x] **Actor Ask（强一致直读）**：Agent 可直接向 Actor 请求内存中最新状态，绕过读库。
  - 实现文件：`backend_business/services/actor/actors/requirement_actor.py` (`_handle_query_state`)
- [ ] **Version Fencing**：读模型查询接口支持 `min_version` 阻塞等待。
- [ ] **增量上下文注入（injected_context）**：Worker 结果返回时直接携带变更后的关键数据。

---

## 五、执行层（Worker）

> 对应主方案 §三。已有任务队列框架，具体 Worker 封装待完善。

- [~] **任务队列（Task Queue）**：已有基础实现。
  - 实现文件：`backend_business/services/agent/tasks/queue.py`
- [~] **需求更新执行器**：初步实现了需求更新任务的异步执行逻辑。
  - 实现文件：`backend_business/services/agent/tasks/executors/requirement_update.py`
- [ ] **LLM / 向量 / 冲突 Worker 封装**：将 `backend_inference` 中的服务逻辑封装为标准 Worker 节点。
- [ ] **Worker 幂等性与心跳**：统一实现 Worker 端的重复执行校验与长耗时任务心跳。
- [ ] **Worker 直写 Actor**：实现 Worker 计算完成后直接向 Actor 发送更新 Command。

---

## 六、专项业务 Agent

- [~] **需求管理助手（Requirements Agent）**：已有定义，支持基础查询与更新申请。
  - 定义文件：`backend_business/services/agent/agents/requirements_agent.py`
- [ ] **质检 / 冲突 / 追溯 / 评审 Agent**：待根据专业领域逻辑逐一实现。

---

## 七、执行图 / 图结构存储

> 对应主方案 §四.3 和 §六。已有基础 CRUD 服务。

- [x] **执行图基础 CRUD**：支持图、容器、节点、边的全生命周期管理。
  - 实现文件：`backend_business/services/execution_graph_service.py`
- [ ] **AgentNode 增量存储**：对齐主方案，仅存储 delta messages，运行时动态重建上下文。
- [ ] **跨容器边自动生成**：逻辑层集成 `ExecutionGraphService`，实现调用边、返回边、重试边的自动记录。
- [ ] **并行调用与汇合节点**：实现多入边汇聚的图结构表达与逻辑控制。

---

## 八、Agent Checkpoint 机制

- [ ] **Checkpoint 写入与恢复**：Agent 进入 Waiting 前持久化索引，结果到达时从执行图重建上下文并继续。
- [ ] **断点恢复流转**：实现 `Suspended` 状态到恢复执行的完整闭环。

---

## 优先级建议

| 优先级 | 模块 | 理由 |
|--------|------|------|
| P0 | 执行图 AgentNode 增量存储对齐 | **当前最紧迫**：基础架构已就绪，需将存储模型与主方案对齐 |
| P0 | Checkpoint 机制 | 实现 Agent 异步化和长流程的基础 |
| P1 | Worker 封装（LLM/RAG/冲突矩阵） | 补全执行层缺口，充分利用 `backend_inference` 现有能力 |
| P1 | Sidebar Span 注入 | 提升分布式环境下的可观测性 |
| P2 | Version Fencing | 优化前端用户体验，消除最终一致性延迟感知 |
| P2 | 计划 Agent (Planner) | 提升系统处理复杂、非标准流程的能力 |
| P3 | 前端执行图可视化增强 | 配合后端新图结构进行 UI 升级 |
