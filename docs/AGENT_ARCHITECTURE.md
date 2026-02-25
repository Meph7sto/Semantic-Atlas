# Semantic-Atlas 多 Agent 通信架构设计

## 1. 概述

本设计文档旨在将 Semantic-Atlas 从单 Agent 系统升级为支持多 Agent 协作的通信架构。参考 WhatsApp 通信模型，采用 **消息总线 (MessageBus) + 通道 (Channel)** 的设计模式，解耦 Agent 之间的直接依赖。

## 2. 核心设计理念

- **去中心化通信**：Agent 之间不直接调用，而是通过消息总线交换信息。
- **通道抽象**：支持私聊 (Direct)、群聊 (Group)、广播 (Broadcast) 三种模式。
- **组合式上下文**：通过组合模式 (Composition) 灵活携带不同场景所需的上下文信息。
- **可观测性**：所有通信经过总线，天然支持审计、日志和回放。

## 3. 目录结构

```
backend_business/services/agent/
├── __init__.py                        # 启动引导
├── context/                           # [已实现] 组合式上下文
│   ├── __init__.py
│   ├── base.py
│   ├── execution.py
│   ├── messaging.py
│   ├── workflow.py
│   └── memory.py
├── registry.py                        # Agent 注册表
├── runner.py                          # Agent 执行引擎
│
├── messaging/                         # [新增] 通信层
│   ├── __init__.py
│   ├── message.py                     # 消息协议定义
│   ├── bus.py                         # 消息总线（核心枢纽）
│   ├── channel.py                     # 通道管理
│   ├── router.py                      # 路由策略
│   └── middleware.py                  # 中间件（日志/限流/鉴权）
│
├── orchestration/                     # [新增] 编排层
│   ├── __init__.py
│   ├── supervisor.py                  # Agent 生命周期管理
│   ├── workflow.py                    # 多 Agent 工作流定义
│   └── strategies.py                  # 协作策略（顺序/并行/投票）
│
├── agents/                            # Agent 定义
│   ├── requirements_agent.py          # 需求管理 Agent
│   ├── conflict_agent.py              # [计划] 冲突检测 Agent
│   └── traceability_agent.py          # [计划] 追溯性 Agent
│
├── tools/                             # 工具层
│   ├── requirement_tools.py
│   └── messaging_tools.py             # [新增] 通信工具（send_message, ask_agent）
│
└── tasks/                             # 任务层
    └── queue.py                       # 审批队列
```

## 4. 关键组件详解

### 4.1 消息协议 (AgentMessage)

定义 Agent 间通信的统一格式：

```python
@dataclass
class AgentMessage:
    message_id: str              # 唯一标识
    channel_id: str              # 所属通道
    sender_id: str               # 发送者 agent_id
    message_type: str            # request, response, notify, vote, heartbeat
    content: dict                # 消息载荷
    reply_to: str | None         # 引用回复
    timestamp: datetime
    metadata: dict               # 扩展字段
```

### 4.2 消息总线 (MessageBus)

通信系统的中央枢纽：
- **职责**：接收消息 → 路由分发 → 持久化 → 触发中间件。
- **实现**：初期使用进程内内存队列，支持未来迁移至 Redis/RabbitMQ。
- **特性**：支持同步请求（等待回复）和异步通知（发完即走）。

### 4.3 通道管理 (Channel)

模拟即时通讯软件的会话概念：

| 类型 | 说明 | 典型场景 |
|------|------|----------|
| `direct` | 1:1 私聊 | Agent A 向 Agent B 请教问题 |
| `group` | 多人协作 | 需求评审会议（需求+冲突+追溯 Agent） |
| `broadcast` | 广播 | 系统级通知（如"项目配置已变更"） |

### 4.4 上下文设计 (AgentContext)

采用组合模式，按需携带上下文信息（已在 `agent/context/` 实现）：

```python
@dataclass
class AgentContext:
    base: BaseContext                  # 基础信息 (user_id, session_id)
    execution: ExecutionContext        # 执行状态 (agent_id, tool_call_id)
    messaging: MessagingContext        # 通信状态 (channel_id, peer_agents)
    workflow: WorkflowContext          # 工作流状态 (step_index, strategy)
    memory: MemoryContext              # 记忆状态 (short_term_memory)
```

## 5. 数据库设计

新增表结构以支持通信持久化：

```sql
-- Agent 消息记录
CREATE TABLE agent_messages (
    message_id   TEXT PRIMARY KEY,
    channel_id   TEXT NOT NULL,
    sender_id    TEXT NOT NULL,
    message_type TEXT NOT NULL,
    content      JSONB,
    reply_to     TEXT REFERENCES agent_messages(message_id),
    metadata     JSONB DEFAULT '{}',
    created_at   TIMESTAMPTZ DEFAULT NOW()
);

-- 通信通道
CREATE TABLE agent_channels (
    channel_id    TEXT PRIMARY KEY,
    channel_type  TEXT CHECK (channel_type IN ('direct','group','broadcast')),
    name          TEXT,
    project_id    TEXT REFERENCES manage_projects(project_id),
    created_by    TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    is_archived   BOOLEAN DEFAULT FALSE
);

-- 通道成员
CREATE TABLE agent_channel_members (
    channel_id  TEXT REFERENCES agent_channels(channel_id) ON DELETE CASCADE,
    agent_id    TEXT NOT NULL,
    role        TEXT DEFAULT 'member',
    joined_at   TIMESTAMPTZ DEFAULT NOW(),
    PRIMARY KEY (channel_id, agent_id)
);
```

## 6. 实施路线图

1.  **Phase 1: 基础设施** ✅
    - [x] 重构 `AgentContext` 为模块化结构
    - [x] 实现 `messaging/` 核心层 (Message, Bus, Channel, Router, Middleware)
    - [x] 创建数据库表结构 (agent_channels, agent_channel_members, agent_messages)

2.  **Phase 2: Agent 能力增强** ✅
    - [x] 实现 `messaging_tools.py`，Agent 间通信全部通过 MessageBus 路由
    - [x] 在 `AgentRunner` 中集成 `MessageBus` (subscribe/unsubscribe + handle_bus_request)

3.  **Phase 3: 编排与工作流** ✅
    - [x] 实现 `orchestration/supervisor.py` 管理 Agent 生命周期
    - [x] 实现 `orchestration/workflow.py` 多 Agent 工作流定义
    - [x] 实现 `orchestration/strategies.py` 多 Agent 协作策略 (Sequential/Parallel/Vote)

4.  **Phase 4: 前端集成** (待实施)
    - [ ] 升级 UI 支持多 Agent 头像和群聊视图
    - [ ] 展示工作流执行进度
