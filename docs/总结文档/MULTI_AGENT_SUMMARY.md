# Multi-Agent 协同架构总结

> 本文档浓缩自 `docs/开发文档/Agent方案_updated.md` 与代码实现，是拓扑图、执行图、多Agent协同机制的全局视图。

---

## 一、四层架构

```
┌─────────────────────────────────────────────────┐
│  会话层  │  用户入口，意图识别，流程编排，结果呈现  │
├─────────────────────────────────────────────────┤
│  执行层  │  专项Agent（质检/冲突检测/需求管理…）  │
├─────────────────────────────────────────────────┤
│  领域层  │  RequirementActor（状态权威，一致性保障）│
├─────────────────────────────────────────────────┤
│  数据层  │  PostgreSQL（事件存储/读模型/执行图存储）│
└─────────────────────────────────────────────────┘
```

---

## 二、拓扑图 — 静态建模

### 2.1 核心元素

| 元素 | 说明 |
|------|------|
| **Container** | 职责边界单元，对应一个Agent/human/system角色 |
| **拓扑节点** | 三种类型：`llm`（推理）、`invoke`（跨容器调用）、`handoff`（交还用户） |
| **拓扑边** | `seq`（容器内顺序）、`call`/`return`/`retry`（跨容器） |

### 2.2 节点类型详解

| 类型 | 执行模型 | 完成信号 |
|------|---------|---------|
| `start` | 透传，注入payload | 直接流转 |
| `llm` | input → LLM → output + tool calls → results | 模型调用 `complete_phase` |
| `handoff` | 挂起，等待用户输入 | 用户输入到达 |
| `invoke` | 跨容器同步调用 | return边到达 |
| `end` | 透传，最终输出 | 节点完成=图完成 |

### 2.3 Container 角色类型

| role_type | 语义 | 典型对应 |
|-----------|------|---------|
| `human` | 用户侧，流程发起者与介入点 | 用户输入/确认 |
| `agent` | AI推理侧，LLM驱动决策执行 | 会话总控、专项Agent |
| `system` | 系统侧，确定性状态管理与校验 | RequirementActor |

### 2.4 跨容器边

- **call边**：发起跨容器调用，调用方进入 `Waiting` 状态
- **return边**：结果回流，调用方恢复 `Running`
- **retry边**：基于上次结论的修正重试，携带约束变化记录

---

## 三、执行图 — 运行时实例

### 3.1 模板 → 运行时映射

```
用户指令到达
    ↓
TopologyInstantiator 实例化执行图骨架
    ├── 为每个 Container 创建 RuntimeContainer
    ├── 为每个拓扑节点创建 RuntimeSubgraph（Pending）
    ├── 注入 start/end 边界节点
    └── 映射拓扑边 → RuntimeEdge
    ↓
SubgraphRunner.run() 开始推进
```

### 3.2 Subgraph — 确定性拓扑与非确定性执行的缓冲层

```
拓扑节点（静态） = 一个语义单元
    ↓ 实例化
RuntimeSubgraph（运行时）
    ├── 内部包含多个 LLM 执行节点（非确定）
    ├── 通过 complete_phase 显式完成
    └── 对外承诺：入口payload + 出口结构化结论
```

**为什么需要Subgraph？**
- 拓扑图规定"经过哪些阶段"，LLM决定"每个阶段内部怎么推理"
- 同一拓扑节点在不同上下文下可能经历不同轮次的tool call
- Subgraph作为缓冲层：对外语义稳定，对内执行步骤灵活伸缩

### 3.3 Scratchpad — 跨阶段信息蒸馏

```
Subgraph A 执行
    ├── LLM 写入 notes / tool_excerpts
    └── complete_phase → 自动追加 stage_output
          ↓
Scratchpad（container 级，container 内全局可见）
          ↓
Subgraph B 启动 → 从 Scratchpad 读取上游结论
```

Scratchpad 对外不可见，外部只能通过 `return` 边看到结构化结论。

### 3.4 执行状态机

**Graph 级（五态）：**

| 状态 | 含义 | 进入条件 |
|------|------|---------|
| `Running` | 节点正在推进 | 初始或从 Waiting/Suspended 恢复 |
| `Waiting` | 等待内部异步结果 | invoke 已发出，return 未到 |
| `Suspended` | 等待用户输入 | handoff 触发或重试耗尽 |
| `Succeeded` | 正常结束 | end 节点完成 |
| `Failed` | 不可恢复错误 | 异常无降级路径 |

**Subgraph 级（四态）：** `Pending` → `Running` → `Completed` / `Failed`

---

## 四、多Agent协同 — MessageBus + Channel

### 4.1 架构概览

```
┌─────────────────────────────────────────┐
│              MessageBus（单例）           │
│  ┌─────────┐  ┌──────────┐  ┌────────┐ │
│  │Middleware│  │ Message  │  │Routing  │ │
│  │Pipeline  │  │ Router   │  │ Rules  │ │
│  └────┬────┘  └────┬─────┘  └────────┘ │
│       │            │                    │
│  publish() → resolve recipients → deliver│
└─────────────────────────────────────────┘
        ↑                           ↓
   ┌────────┐  ┌────────┐    ┌──────────┐
   │ Agent  │  │ Agent   │    │ ChannelMgr│
   │ A      │  │ B       │    │ (in-mem) │
   └────────┘  └────────┘    └──────────┘
```

### 4.2 Channel 类型

| 类型 | 语义 |
|------|------|
| `DIRECT` | 1:1 私有通道 |
| `GROUP` | 多方协作通道 |
| `BROADCAST` | 系统级广播 |

### 4.3 消息类型

| 类型 | 语义 | 行为 |
|------|------|------|
| `REQUEST` | 请求对方执行任务 | 等待 RESPONSE |
| `RESPONSE` | 响应 REQUEST | 触发 Future 回填 |
| `NOTIFY` | 通知（fire-and-forget） | 无需回复 |
| `VOTE` | 投票（组决策） | 等待收集 |
| `TASK_RESULT` | 任务完成结果 | 异步通知 |
| `HEARTBEAT` | 心跳保活 | 维护连接 |

### 4.4 MessageBus 核心方法

```python
message_bus.publish(message)                    # 发布消息（含middleware链）
message_bus.send_request(channel, payload)      # 发送REQUEST，返回message_id
message_bus.send_response(request_id, payload)  # 回复RESPONSE
message_bus.send_notify(channel, payload)       # 发送NOTIFY
message_bus.request_and_wait(request, timeout)  # 同步请求-响应，等待Future
```

### 4.5 Middleware 栈（默认加载）

| Middleware | 职责 |
|-----------|------|
| `LoggingMiddleware` | 记录每次发布与投递 |
| `RateLimitMiddleware` | token-bucket 限流（100 msg / 60s） |
| `AuthorizationMiddleware` | 发送者须为通道成员 |
| `MetricsMiddleware` | 计数器：published/delivered/by type |

### 4.6 协作模式

**会话总控 → 专项Agent：**
```
用户输入 → 会话总控(意图识别)
    ├── 判断不相关 → 直接回复
    └── 判断相关 → 编排委托指令 → 发送 REQUEST
                            ↓
                    专项Agent（invoke/call边）
                            ↓
                    RequirementActor（Command驱动）
                            ↓
                    return 结论 → 会话总控 → 回复用户
```

**并行invoke（Waiting状态）：**
- 多个invoke并发执行时，调用方整体进入 `Waiting`
- 各目标container并行LLM调用，不串行等待
- return全部到达后恢复 `Running`

---

## 五、会话链 — 多轮上下文

```
session_id
  └── graph_id_1（第1轮）
        └── graph_id_2（第2轮，通过 prev_graph_id 引用)
              └── graph_id_3（第3轮）
```

- 每轮用户意图 = 一张独立的 RuntimeGraph
- 新图通过 `prev_graph_id` 增量引用前图上下文
- **Suspended** = 同一意图中途需要用户补充信息
- **新建Graph** = 用户发起了新的意图

---

## 六、关键设计原则

1. **职责隔离**：会话层不透明领域，执行层不持有状态，领域层不参与编排
2. **写入口唯一**：需求管理Agent是唯一写入入口 → RequirementActor
3. **事件溯源**：Actor所有变更 → 不可变Event → 事件存储是唯一真相来源
4. **并发安全**：Actor串行信箱从架构层面消除写入冲突
5. **可审计**：完整执行轨迹（节点/边/状态变更）持久化于执行图
6. **Virtual Actor**：按需激活/休眠，逻辑支持海量需求，物理内存仅维持活跃子集

---

## 七、关键文件索引

| 文件 | 职责 |
|------|------|
| `services/agent/messaging/bus.py` | MessageBus 单例核心 |
| `services/agent/messaging/channel.py` | ChannelManager |
| `services/agent/messaging/router.py` | MessageRouter + RoutingRule |
| `services/agent/execution/graph_executor.py` | GraphExecutor（execute/resume） |
| `services/agent/execution/subgraph_runner.py` | SubgraphRunner（run/resume） |
| `services/agent/topology/topology_instantiator.py` | 拓扑图 → 执行图骨架实例化 |
| `services/agent/topology/agent_container.py` | AgentContainer |
| `services/agent/runtime/scratchpad.py` | Scratchpad 读写 |
| `services/agent/runtime/graph_recorder.py` | 运行时执行图记录器 |
