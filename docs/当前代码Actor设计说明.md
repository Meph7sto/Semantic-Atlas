# 当前代码 Actor 设计说明

本文描述的是仓库里已经落地的 Actor 相关设计，不是理想方案，也不是历史草案。当前代码里的 Actor 主要分成两层：

1. `RequirementActor`：面向单条需求 (`requirement_id`) 的领域运行时。
2. `AgentActorRuntime` / `RequirementAgentActorRuntime`：给智能体工具链调用 `RequirementActor` 提供的异步适配层。

可以先把这套实现理解为一套“基于 `asyncio.Queue`、事件溯源和单例 Manager 的轻量 Actor 机制”，而不是完整的 Actor 框架。

## 1. 为什么这里要用 Actor

当前实现想解决的是“单条需求的写入串行化”和“状态恢复”两个核心问题。

- 单条需求在同一时刻只允许一条命令进入真正的状态变更逻辑，避免并发写把状态打乱。
- 状态不直接以数据库字段为唯一真相，而是以事件流为真相，内存状态只是运行时投影。
- Actor 生命周期不暴露给调用方，外部只管发命令，不关心对象是否刚被激活、是否已经空闲回收。
- 智能体工具链本身有大量同步/生成器式编排代码，需要一个专门的桥接层安全地调用异步 Actor 主链路。

## 2. 代码范围

### 2.1 RequirementActor 主链路

- `backend_business/services/actor/actors/requirement_actor.py`
- `backend_business/services/actor/actor_manager.py`
- `backend_business/services/actor/actors/state_machine.py`
- `backend_business/services/event_store/event_store.py`
- `backend_business/services/read_projections/requirement_projection.py`
- `backend_business/api/routers/requirement_actor.py`
- `backend_business/services/actor/dev_trace.py`

### 2.2 Agent 侧适配层

- `backend_business/services/agent/actor/actor_runtime.py`
- `backend_business/services/agent/agents/requirement_agent/actor_runtime.py`
- `backend_business/services/agent/agents/requirement_agent/service.py`

### 2.3 配套界面与测试

- `frontend/src/views/alpha/ActorVisualTester.vue`
- `tests/requirements/test_requirement_actor_runtime_safety.py`
- `tests/requirements/test_actor_manager_coordination.py`
- `tests/agent_chat/test_agent_infrastructure_runtime.py`

## 3. RequirementActor 的设计思路

### 3.1 Actor 身份边界

这里的 Actor 粒度是“单条需求”。

- 一个 `requirement_id` 对应一个 `RequirementActor` 实例。
- 这个实例持有该需求的内存状态 `RequirementState`。
- 对该需求的所有命令都必须先进这个实例的邮箱，再串行执行。

这意味着系统不是按“模块”建 Actor，而是按“聚合根实例”建 Actor。

### 3.2 单写者模型

`RequirementActor` 内部有一个 `asyncio.Queue` 作为邮箱：

- `send_command()` 只负责把命令和一个 `Future` 放入邮箱。
- `_process_mailbox()` 是唯一消费者。
- 每次只出队一个命令，再进入 `_handle_command()`。
- 命令处理完成后，结果回填到对应 `Future`。

这样做的本质，是把“并发请求”变成“单线程逻辑上的串行消息处理”。

### 3.3 事件溯源而不是直接改库

Actor 不直接把完整状态对象整块覆盖到数据库。写入主链路是：

```text
HTTP / Tool Call
  -> ActorManager.send_command()
  -> RequirementActor.send_command()
  -> mailbox enqueue
  -> RequirementActor._handle_xxx()
  -> EventStore.append_event()
  -> RequirementActor._apply_event()
  -> 返回 version / event_id
```

也就是说：

- 先产生领域事件。
- 事件落库成功后，再把事件应用到内存状态。
- 当前版本号来自事件序号 `event_sequence`。

这种设计让“恢复”和“审计”都更自然。

### 3.4 内存状态结构

`RequirementState` 当前包含这些核心字段：

- `requirement_id`
- `version`
- `content`
- `status`
- `quality_markers`
- `evidence_links`
- `priority`
- `created_at`
- `updated_at`
- `is_deleted`

其中 `status` 由 `RequirementStateMachine` 约束，当前状态包括：

- `Draft`
- `PendingReview`
- `UnderReview`
- `Approved`
- `Rejected`
- `Baselined`
- `ChangeRequested`

### 3.5 命令和事件的分层

当前主链路里真正实现的命令只有 4 类：

- `CreateRequirement`
- `UpdateRequirementContent`
- `ChangeStatus`
- `AddQualityMarker`

当前代码能识别并应用的事件比命令更多，还包括：

- `RequirementEvidenceLinkAdded`
- `RequirementPriorityChanged`
- `RequirementDeleted`

这说明现状是：

- 事件模型为后续扩展预留了空间。
- 但并不是每一种事件都已经有对应的命令入口和主链路实现。

### 3.6 激活和恢复

Actor 被激活时，不是假设内存里已经有状态，而是从持久化层恢复：

1. 先查最新快照。
2. 如果有快照，先从快照恢复状态，并记住快照版本。
3. 再重放快照之后的事件。
4. 最后启动邮箱消费协程。

因此 `RequirementActor` 的状态来源优先级是：

```text
快照 + 增量事件重放 > 全量事件重放 > 空状态
```

### 3.7 快照策略

快照不是每次写都做，而是按版本间隔做：

- `SNAPSHOT_INTERVAL = 100`
- 每处理到 100 的倍数版本时，触发一次定期快照。
- `stop()` 时也会先尝试做一次快照。

快照写入失败会抛出 `InfrastructureException`，Manager 会据此拒绝真正卸载 Actor，避免“内存没了但状态没存下来”。

### 3.8 故障语义

代码里把异常分成两类：

- `DomainException`
  - 业务规则不允许，不重试。
  - 例如：修改已基线需求、非法状态流转、重复创建。
- `InfrastructureException`
  - 基础设施异常，可重试。
  - 例如：事件落库失败、快照落库失败、协调器不可用。

邮箱消费时的处理策略是：

- 业务异常直接返回失败。
- 基础设施异常按指数退避重试。
- 超过 `MAX_RETRIES` 后，Actor 进入 `is_faulted = True` 的熔断状态。
- 熔断后会主动失败化邮箱里尚未处理的积压请求，避免调用方一直挂起。

## 4. ActorManager 的职责

`ActorManager` 是 `RequirementActor` 的运行时外壳，负责把“虚拟 Actor”这层抽象做出来。

### 4.1 它负责什么

- `requirement_id -> RequirementActor` 的实例索引。
- 首次访问时自动激活 Actor。
- 分布式协调器初始化和心跳启动。
- 空闲 Actor 的定时回收。
- 统一统计信息输出。
- 进程关闭时的整体 shutdown。

### 4.2 为什么要有 Manager

如果没有 Manager，外部代码就必须知道：

- Actor 什么时候创建。
- Actor 是否已存在。
- Actor 什么时候需要回收。
- 回收前是否要做快照。
- 集群场景下是否需要拿分布式锁。

现在这些都收敛到 `ActorManager`，业务调用方只做一件事：

```python
await manager.send_command(requirement_id, command)
```

### 4.3 空闲回收

当前回收策略是：

- `IDLE_TIMEOUT_SECONDS = 600`
- `PASSIVATION_SCAN_INTERVAL_SECONDS = 60`
- 只有当 Actor 超时未访问且邮箱为空时，才允许进入回收流程

回收流程本身是：

1. 触发 `passivation_started` 调试事件。
2. 调用 `actor.stop()`。
3. 如果快照失败，放弃本次回收并刷新 `last_accessed`。
4. 如果成功，移出 `_actors`，并释放分布式锁。

### 4.4 当前的统计与巡检能力

Manager 可输出：

- 总 Actor 数
- 活跃 Actor 数
- 熔断 Actor 数
- Actor ID 列表
- 每个 Actor 的邮箱长度

这些能力同时被以下端点和前端界面使用：

- `/api/v2/requirement-actor/stats`
- `/api/v2/_internals/actors/stats`
- `frontend/src/views/alpha/ActorVisualTester.vue`

## 5. 持久化设计

### 5.1 事件存储

`EventStore` 是 RequirementActor 的持久化核心。

主表：

- `requirement_events`
- `requirement_snapshots`

此外还会更新 `manage_requirements` 上的辅助字段：

- `current_version`
- `last_event_id`
- `last_snapshot_id`
- `actor_status`

### 5.2 事件表的作用

`requirement_events` 的关键价值是：

- 追加写，不覆盖历史。
- 用 `(requirement_id, event_sequence)` 保证单需求内的事件顺序。
- 可直接拿来做审计、回放、投影重建。

### 5.3 快照表的作用

`requirement_snapshots` 保存某个版本下的完整状态，目的是减少激活时的重放成本。

### 5.4 命令队列表的现状

Schema 里还有 `requirement_command_queue`，`EventStore` 也有：

- `log_command()`
- `update_command_status()`

但当前 `RequirementActor -> ActorManager -> Router` 主链路并没有接入这套命令审计表。也就是说，这部分更像是预留能力，而不是现行执行路径的一部分。

## 6. 读写分离与查询模型

这里其实有两种查询路径，语义不同。

### 6.1 Ask：直接问 Actor 内存态

`QueryState` 命令会直接命中当前 Actor 的内存状态。

特点：

- 一致性最强。
- 必须经过 Actor。
- 更偏内部运行时查询或工具链调用。

### 6.2 Query：查读模型

`GET /api/v2/requirement-actor/query` 走的是 `RequirementProjection` 读模型。

它支持 `min_version` 版本围栏：

- 如果读模型版本还没追到 `min_version`，会轮询等待。
- 等到目标版本再返回。
- 超时返回 503。

这条链路的设计意图是把“用户查询”和“Actor 内存态”解耦，避免所有读都压到 Actor 本身。

## 7. API 与调试接口

当前 Router 前缀是：

```text
/api/v2/requirement-actor
```

这点要特别注意，因为 README 里还保留过 `/api/v2/actor` 的旧描述，现状以代码为准。

### 7.1 命令接口

- `POST /command`
- `POST /command/create`
- `POST /command/update-content`
- `POST /command/change-status`
- `POST /command/add-quality-marker`
- `POST /command/query-state`

### 7.2 查询与回放接口

- `GET /query`
- `GET /events/{requirement_id}`
- `GET /snapshot/{requirement_id}`
- `GET /versions/{requirement_id}`
- `GET /replay/{requirement_id}/{version}`
- `GET /transitions`

### 7.3 运维与调试接口

- `GET /health/{requirement_id}`
- `GET /stats`
- `POST /force-activate/{requirement_id}`
- `POST /force-passivate/{requirement_id}`
- `POST /cleanup`
- `GET /api/v2/_internals/actors/stats`
- `WS /api/v2/_internals/actors/ws`

### 7.4 开发态观测

`backend_business/services/actor/dev_trace.py` 提供了一个轻量广播器：

- Actor 生命周期和命令处理阶段会调用 `emit_actor_trace()`
- WebSocket 客户端通过 `subscribe()` / `unsubscribe()` 接入
- 队列满了会丢弃最老消息
- 广播失败不会影响主业务链路

前端 `ActorVisualTester.vue` 就是在消费这个调试流，并定时轮询 stats。

## 8. 分布式协调设计

当前代码考虑了“同一个 `requirement_id` 在集群中只能有一个活动 Actor”的问题。

实现位置：

- `backend_business/services/agent/coordinator/distributed_coordinator.py`
- `backend_business/services/actor/actor_manager.py`

核心思路是 Redis 协调：

- 激活前先检查协调器可用性。
- 通过 `lock:actor:{requirement_id}` 尝试获取排他锁。
- 成功后记录 `instance:actor:{requirement_id}`。
- Manager 启动心跳，维持实例注册和锁相关状态。

这部分说明当前实现已经不是“纯进程内单例”了，而是预留了跨节点唯一性的入口。

## 9. AgentActorRuntime 的设计思路

`AgentActorRuntime` 不是第二套领域 Actor，而是“智能体调用 RequirementActor 的桥接器”。

### 9.1 它要解决什么问题

`RequirementAgentChatService` 和工具调用链里有不少同步方法、生成器式流式输出和线程外调用场景，而 `ActorManager.send_command()` 是异步协程。

如果直接在这些位置硬拼事件循环，容易出现：

- 没有可用 loop
- 嵌套 loop
- 跨线程 await
- 工具调用阻塞/超时边界不清楚

### 9.2 它的做法

`AgentActorRuntime` 会：

- 独立创建一个后台线程
- 在线程里跑一个专用 `asyncio` event loop
- 用 `asyncio.run_coroutine_threadsafe()` 把 Actor 协程投递进去
- 用同步的 `future.result(timeout=...)` 把结果拿回来

因此，它把“异步 Actor 主链路”包装成了“同步可调用的适配能力”。

### 9.3 对外暴露的最小接口

- `get_actor_manager()`
- `ensure_actor_loop()`
- `run_actor_coro()`
- `actor_query()`
- `actor_write()`

其中：

- `actor_query()` 固定发 `{"type": "QueryState", "source": ...}`
- `actor_write()` 透传写命令

### 9.4 RequirementAgentActorRuntime

`RequirementAgentActorRuntime` 是一个很薄的子类，只是把默认值改成更贴近需求智能体场景：

- `query_source = "requirement_agent_chat"`
- `loop_thread_name = "requirement-agent-actor-loop"`

### 9.5 在需求智能体中的接入方式

`RequirementAgentChatService` 初始化工具集时，把 Actor 相关能力注入给工具层：

- `actor_query_fn=self._actor_query`
- `actor_write_fn=self._actor_write`

所以当前智能体对 RequirementActor 的访问路径是：

```text
RequirementAgentChatService
  -> RequirementAgentActorRuntime
  -> ActorManager
  -> RequirementActor
```

## 10. 当前实现的边界和注意点

这部分不是否定设计，而是帮助后续维护时快速知道“哪里已经闭环，哪里还只是半步”。

### 10.1 已经比较完整的部分

- 单需求单邮箱串行执行
- 事件落库后更新内存态
- 快照恢复和回收前快照保护
- 业务异常 / 基础设施异常分流
- 熔断后失败化积压 Future
- 读模型版本围栏查询
- 调试 WebSocket 和前端可视化测试页
- Agent 侧专用 event loop 适配

### 10.2 仍然是当前边界的部分

- 分布式协调器的 `forward_request()` 还是 TODO
  - 当前拿不到锁时会拒绝激活，而不是转发到持锁节点
- `ActorManager` 的实例表 `_actors` 仍然是进程内字典
  - Redis 协调解决的是“唯一性约束”，不是“远程调用路由”
- `events/stream/{requirement_id}` 现在主要是心跳型 SSE
  - 不是完整的实时领域事件推送总线
- 事件模型比命令模型更完整
  - 一些事件类型已定义，但还没有对应写命令进入主链路
- `requirement_command_queue` 审计表当前未进入主写链路

## 11. 一句话总结

当前代码里的 Actor 设计，本质上是：

“用 `ActorManager + RequirementActor + EventStore + Projection` 把单需求写入收敛为串行消息处理，再用 `AgentActorRuntime` 把这条异步主链路安全地暴露给智能体工具层。”

如果后续继续演进，这套设计最自然的方向会是：

- 把未接入的命令审计链路接到主路径
- 补齐跨节点转发
- 统一实时事件推送
- 让事件模型和命令模型完全对齐
