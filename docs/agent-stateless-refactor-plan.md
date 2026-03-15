# Agent 无状态化改造计划
## 任务队列化 + 状态机（Stateless Workers）

> 状态更新（2026-03-02）：`/api/ai-chat/*`、`/api/agent-tasks/*`、`/api/agent-monitor/*` 已从当前代码移除；`ai_chat_sessions`、`ai_chat_messages`、`agent_pending_tasks` 已列入下线表。本文中的相关段落仅保留为历史方案记录。

**目标**：将现有的有状态 Agent 系统改造为无状态 Worker 架构，支持 100+ 并发用户。

**核心思想**：Agent 变成无状态的工人（Stateless Worker），所有对话上下文和消息全部存在数据库或 Redis 里，任何空闲的 Worker 都可以处理任何用户的消息。

---

## 一、现有架构分析

### 1.1 当前架构问题

**现状**：
- **AgentRunner** (`runner.py`)：每次请求创建完整的内存上下文，执行完成后销毁
- **MessageBus** (`bus.py`)：基于内存的消息路由，消息历史存储在 `deque`（最多 1000 条）
- **AgentContext**：执行状态完全在内存中，包括 `messages` 列表、`round_number` 等
- **临时订阅机制**：Worker 在处理请求期间临时订阅 bus，完成后取消订阅

**问题**：
1. **不可扩展**：每个用户的请求绑定到特定的 Worker 线程，无法横向扩展
2. **无容错性**：服务器重启或崩溃会丢失所有进行中的对话上下文
3. **资源浪费**：100 个在线用户需要 100 个常驻 Worker（即使大部分时间空闲）
4. **无断点续传**：长时间运行的任务无法中断后继续

### 1.2 现有数据库表

已有的相关表：
```sql
-- 用户聊天会话
ai_chat_sessions (session_id, user_id, agent_id, project_id, created_at)
ai_chat_messages (message_id, session_id, user_id, role, content, metadata, is_read, created_at)

-- Agent 任务审批（非真正的任务队列）
agent_pending_tasks (task_id, session_id, project_id, user_id, task_type, status, created_at)

-- Agent 消息记录
agent_channels (channel_id, channel_type, project_id, created_by)
agent_channel_members (channel_id, agent_id, role)
agent_messages (message_id, channel_id, sender_id, message_type, content, created_at)
```

**缺失的表**：
- ❌ 没有真正的任务队列表（存储待处理的用户消息）
- ❌ 没有 Agent 执行状态表（存储 tool-calling 轮次、中间结果）
- ❌ 没有 Worker 注册表（追踪哪些 Worker 在线、处理能力）
- ❌ 没有分布式锁表（防止多个 Worker 同时处理同一任务）

---

## 二、改造方案设计

### 2.1 架构总览

```
┌──────────────────────────────────────────────────────────────┐
│                      前端用户请求                              │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│               Flask Route (API Gateway)                      │
│  • POST /api/ai-chat/stream                                  │
│  • 接收用户消息，创建 Task 放入队列，立即返回                   │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     ▼
┌──────────────────────────────────────────────────────────────┐
│                  任务队列 (Task Queue)                         │
│  • Redis List: agent_task_queue:pending                     │
│  • PostgreSQL Table: agent_work_tasks                        │
│  • 状态: pending → processing → completed/failed             │
└────────────────────┬─────────────────────────────────────────┘
                     │
                     ▼
         ┌───────────┴───────────┐
         │                       │
         ▼                       ▼
┌─────────────────┐     ┌─────────────────┐
│   Worker Pool   │     │   Worker Pool   │
│   (容器/进程 1)   │     │   (容器/进程 N)   │
│                 │     │                 │
│  • 竞争抢任务    │     │  • 竞争抢任务    │
│  • 无状态执行    │     │  • 无状态执行    │
│  • 断点续传      │     │  • 断点续传      │
└─────────┬───────┘     └─────────┬───────┘
          │                       │
          └───────────┬───────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────┐
│              状态存储 (State Store)                           │
│  • PostgreSQL: agent_execution_states                        │
│  • Redis Cache: 热数据缓存                                    │
│  • 存储: messages, tool_results, round_number 等              │
└──────────────────────────────────────────────────────────────┘
                      │
                      ▼
┌──────────────────────────────────────────────────────────────┐
│              结果推送 (Result Delivery)                        │
│  • SSE Stream: 推送给前端用户                                  │
│  • WebSocket: 实时更新                                        │
│  • PostgreSQL: ai_chat_messages (持久化)                     │
└──────────────────────────────────────────────────────────────┘
```

### 2.2 核心组件

#### 2.2.1 任务队列 (Task Queue)

**双重存储策略**：
- **Redis List**：快速的 FIFO 队列，用于任务调度
- **PostgreSQL Table**：可靠的持久化存储，用于状态追踪和故障恢复

**新增数据库表**：
```sql
-- 工作任务队列表
CREATE TABLE agent_work_tasks (
    task_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES ai_chat_sessions(session_id) ON DELETE CASCADE,
    user_id TEXT NOT NULL,
    agent_id TEXT NOT NULL,
    project_id TEXT REFERENCES manage_projects(project_id) ON DELETE SET NULL,

    -- 任务内容
    user_message_id TEXT NOT NULL REFERENCES ai_chat_messages(message_id),
    user_content TEXT NOT NULL,

    -- 状态机
    status TEXT NOT NULL DEFAULT 'pending'
        CHECK (status IN ('pending', 'processing', 'completed', 'failed', 'cancelled')),

    -- Worker 信息
    worker_id TEXT,                           -- 当前处理该任务的 Worker ID
    locked_at TIMESTAMPTZ,                    -- 任务被锁定的时间
    lock_expires_at TIMESTAMPTZ,              -- 锁过期时间（防止 Worker 崩溃）

    -- 优先级和重试
    priority INT DEFAULT 0,                   -- 优先级（数字越大越优先）
    retry_count INT DEFAULT 0,                -- 重试次数
    max_retries INT DEFAULT 3,                -- 最大重试次数

    -- 时间戳
    created_at TIMESTAMPTZ DEFAULT NOW(),
    started_at TIMESTAMPTZ,                   -- 开始处理时间
    completed_at TIMESTAMPTZ,                 -- 完成时间

    -- 结果和错误
    result JSONB,                             -- 执行结果
    error_message TEXT,                       -- 错误信息

    -- 元数据
    metadata JSONB DEFAULT '{}'               -- 扩展字段
);

-- 索引优化
CREATE INDEX idx_agent_work_tasks_status ON agent_work_tasks(status)
    WHERE status IN ('pending', 'processing');
CREATE INDEX idx_agent_work_tasks_session ON agent_work_tasks(session_id);
CREATE INDEX idx_agent_work_tasks_user ON agent_work_tasks(user_id);
CREATE INDEX idx_agent_work_tasks_priority ON agent_work_tasks(priority DESC, created_at ASC)
    WHERE status = 'pending';
CREATE INDEX idx_agent_work_tasks_lock_expires ON agent_work_tasks(lock_expires_at)
    WHERE status = 'processing' AND lock_expires_at IS NOT NULL;
```

**Redis 队列结构**：
```
# 优先级队列（使用 Sorted Set 实现优先级）
agent_task_queue:pending           # ZSET: score = priority, member = task_id
agent_task_queue:processing        # HASH: task_id -> worker_id
agent_task_queue:dead_letter       # LIST: 失败任务

# 任务锁（使用 Redis 分布式锁）
agent_task_lock:{task_id}          # STRING: worker_id, TTL = 60s
```

#### 2.2.2 执行状态存储 (Execution State)

**新增数据库表**：
```sql
-- Agent 执行状态表（存储 tool-calling 循环的中间状态）
CREATE TABLE agent_execution_states (
    execution_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL REFERENCES agent_work_tasks(task_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL REFERENCES ai_chat_sessions(session_id) ON DELETE CASCADE,
    agent_id TEXT NOT NULL,

    -- 执行上下文
    messages JSONB NOT NULL,                  -- LLM 对话历史（包含 system/user/assistant/tool）
    current_round INT DEFAULT 0,              -- 当前 tool-calling 轮次
    max_rounds INT DEFAULT 6,                 -- 最大轮次

    -- Tool-calling 状态
    tool_calls_pending JSONB,                 -- 等待执行的 tool calls
    tool_results JSONB DEFAULT '[]',          -- 已执行的 tool 结果
    tasks_created JSONB DEFAULT '[]',         -- 创建的待审批任务列表

    -- Agent 上下文
    agent_context JSONB,                      -- BaseContext, ExecutionContext, MessagingContext

    -- 流式输出累积
    assistant_content TEXT DEFAULT '',        -- 累积的 assistant 回复
    thinking_content TEXT DEFAULT '',         -- 累积的思考内容（if reasoning mode）

    -- 状态机
    state TEXT NOT NULL DEFAULT 'initializing'
        CHECK (state IN ('initializing', 'llm_calling', 'tool_executing',
                         'waiting_approval', 'completed', 'failed')),

    -- 时间戳
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- 检查点（用于断点续传）
    checkpoint_data JSONB,                    -- 额外的检查点数据
    last_checkpoint_at TIMESTAMPTZ
);

-- 索引
CREATE INDEX idx_agent_execution_states_task ON agent_execution_states(task_id);
CREATE INDEX idx_agent_execution_states_session ON agent_execution_states(session_id);
CREATE UNIQUE INDEX idx_agent_execution_states_task_active
    ON agent_execution_states(task_id)
    WHERE state NOT IN ('completed', 'failed');
```

**Redis 缓存策略**：
```
# 热数据缓存（TTL = 30 分钟）
agent_exec_state:{execution_id}    # HASH: 完整的执行状态
agent_exec_messages:{execution_id} # LIST: messages 数组（为了节省空间，可以只缓存最近 20 条）

# 会话活跃追踪
agent_active_sessions              # ZSET: score = last_activity_timestamp
```

#### 2.2.3 Worker 注册与健康检查

**新增数据库表**：
```sql
-- Worker 注册表
CREATE TABLE agent_workers (
    worker_id TEXT PRIMARY KEY,
    hostname TEXT NOT NULL,
    process_id INT NOT NULL,

    -- 能力声明
    supported_agents TEXT[] NOT NULL,         -- 支持的 Agent 类型列表
    max_concurrent_tasks INT DEFAULT 5,       -- 最大并发任务数
    current_load INT DEFAULT 0,               -- 当前负载（处理中的任务数）

    -- 状态
    status TEXT NOT NULL DEFAULT 'idle'
        CHECK (status IN ('idle', 'busy', 'offline', 'error')),

    -- 健康检查
    last_heartbeat TIMESTAMPTZ DEFAULT NOW(),
    heartbeat_interval INT DEFAULT 10,        -- 心跳间隔（秒）

    -- 时间戳
    started_at TIMESTAMPTZ DEFAULT NOW(),

    -- 元数据
    version TEXT,                             -- Worker 版本号
    metadata JSONB DEFAULT '{}'
);

-- 索引
CREATE INDEX idx_agent_workers_status ON agent_workers(status);
CREATE INDEX idx_agent_workers_heartbeat ON agent_workers(last_heartbeat);
```

**Redis 结构**：
```
# Worker 在线列表（TTL = 30s，由 heartbeat 刷新）
agent_workers:online               # SET: worker_id
agent_worker:{worker_id}:heartbeat # STRING: timestamp, TTL = 30s
agent_worker:{worker_id}:load      # STRING: current_load
```

#### 2.2.4 分布式锁机制

**使用 Redis 实现分布式锁**：
```python
# 伪代码示例
def acquire_task_lock(task_id: str, worker_id: str, ttl: int = 60) -> bool:
    """尝试获取任务锁（基于 Redis SETNX）"""
    lock_key = f"agent_task_lock:{task_id}"
    return redis.set(lock_key, worker_id, nx=True, ex=ttl)

def release_task_lock(task_id: str, worker_id: str) -> bool:
    """释放任务锁（使用 Lua 脚本保证原子性）"""
    lock_key = f"agent_task_lock:{task_id}"
    lua_script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    return redis.eval(lua_script, [lock_key], [worker_id]) == 1

def extend_task_lock(task_id: str, worker_id: str, ttl: int = 60) -> bool:
    """延长锁的过期时间（在长时间运行的任务中定期调用）"""
    lock_key = f"agent_task_lock:{task_id}"
    lua_script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("expire", KEYS[1], ARGV[2])
    else
        return 0
    end
    """
    return redis.eval(lua_script, [lock_key], [worker_id, ttl]) == 1
```

---

## 三、改造实施步骤

### 3.1 Phase 1: 基础设施准备（第 1-2 周）

#### 3.1.1 数据库迁移

**文件位置**：`backend_business/services/db_service_parts/schema.py`

**新增表创建**：
1. `agent_work_tasks` - 任务队列表
2. `agent_execution_states` - 执行状态表
3. `agent_workers` - Worker 注册表

**修改现有表**：
- `ai_chat_sessions` 可能需要增加字段：
  - `last_activity_at TIMESTAMPTZ` - 最后活动时间
  - `state TEXT` - 会话状态（active, waiting_user, waiting_agent）

#### 3.1.2 Redis 配置

**文件位置**：`backend_business/config.py`

**新增配置项**：
```python
# Redis 配置
REDIS_HOST = os.getenv("REDIS_HOST", "localhost")
REDIS_PORT = int(os.getenv("REDIS_PORT", 6379))
REDIS_DB = int(os.getenv("REDIS_DB", 0))
REDIS_PASSWORD = os.getenv("REDIS_PASSWORD")

# 任务队列配置
TASK_QUEUE_ENABLED = os.getenv("TASK_QUEUE_ENABLED", "true").lower() == "true"
TASK_LOCK_TTL = int(os.getenv("TASK_LOCK_TTL", 60))  # 任务锁过期时间（秒）
WORKER_HEARTBEAT_INTERVAL = int(os.getenv("WORKER_HEARTBEAT_INTERVAL", 10))  # 心跳间隔
WORKER_MAX_CONCURRENT_TASKS = int(os.getenv("WORKER_MAX_CONCURRENT_TASKS", 5))
```

#### 3.1.3 新增服务类

**创建文件**：`backend_business/services/agent/queue/`

**目录结构**：
```
backend_business/services/agent/queue/
├── __init__.py
├── task_queue.py           # 任务队列核心逻辑
├── state_store.py          # 执行状态存储
├── worker_registry.py      # Worker 注册与健康检查
├── lock_manager.py         # 分布式锁管理
└── redis_client.py         # Redis 客户端封装
```

**核心接口设计**：
```python
# task_queue.py
class TaskQueue:
    def enqueue(self, task: WorkTask) -> str:
        """将任务加入队列，返回 task_id"""

    def dequeue(self, worker_id: str) -> Optional[WorkTask]:
        """Worker 从队列取出一个任务（带锁）"""

    def complete_task(self, task_id: str, result: dict) -> None:
        """标记任务完成"""

    def fail_task(self, task_id: str, error: str) -> None:
        """标记任务失败"""

    def retry_task(self, task_id: str) -> bool:
        """重试失败的任务"""

    def get_task_status(self, task_id: str) -> dict:
        """查询任务状态"""

# state_store.py
class ExecutionStateStore:
    def create_state(self, task_id: str, initial_data: dict) -> str:
        """创建执行状态，返回 execution_id"""

    def get_state(self, execution_id: str) -> Optional[dict]:
        """获取执行状态（优先从 Redis 读取，miss 时从 PG 读取）"""

    def update_state(self, execution_id: str, updates: dict) -> None:
        """更新执行状态（同时写 Redis 和 PG）"""

    def append_message(self, execution_id: str, message: dict) -> None:
        """向 messages 数组追加消息"""

    def save_checkpoint(self, execution_id: str) -> None:
        """保存检查点（用于断点续传）"""

    def restore_from_checkpoint(self, execution_id: str) -> dict:
        """从检查点恢复状态"""

# worker_registry.py
class WorkerRegistry:
    def register_worker(self, worker_id: str, capabilities: dict) -> None:
        """注册 Worker"""

    def unregister_worker(self, worker_id: str) -> None:
        """注销 Worker"""

    def heartbeat(self, worker_id: str) -> None:
        """发送心跳"""

    def get_available_workers(self) -> List[str]:
        """获取可用的 Worker 列表"""

    def update_load(self, worker_id: str, load: int) -> None:
        """更新 Worker 负载"""

    def cleanup_stale_workers(self) -> int:
        """清理过期的 Worker（心跳超时）"""
```

### 3.2 Phase 2: 无状态 Runner 改造（第 3-4 周）

#### 3.2.1 创建无状态 Worker

**新建文件**：`backend_business/services/agent/worker.py`

**核心改造点**：
```python
class StatelessAgentWorker:
    """无状态 Agent Worker，可以处理任何用户的任务"""

    def __init__(self, worker_id: str):
        self.worker_id = worker_id
        self.task_queue = TaskQueue()
        self.state_store = ExecutionStateStore()
        self.worker_registry = WorkerRegistry()
        self.lock_manager = LockManager()

    def run_forever(self) -> None:
        """主循环：不断从队列取任务并处理"""
        self.worker_registry.register_worker(self.worker_id, {
            "supported_agents": agent_registry.list_agent_ids(),
            "max_concurrent_tasks": WORKER_MAX_CONCURRENT_TASKS
        })

        try:
            while True:
                # 1. 发送心跳
                self.worker_registry.heartbeat(self.worker_id)

                # 2. 从队列取任务（阻塞式，带超时）
                task = self.task_queue.dequeue(self.worker_id)
                if not task:
                    time.sleep(1)
                    continue

                # 3. 处理任务
                try:
                    self._process_task(task)
                except Exception as e:
                    logger.error(f"Worker {self.worker_id} failed to process task {task.task_id}: {e}")
                    self.task_queue.fail_task(task.task_id, str(e))

        finally:
            self.worker_registry.unregister_worker(self.worker_id)

    def _process_task(self, task: WorkTask) -> None:
        """处理单个任务（无状态执行）"""
        # 1. 加载或创建执行状态
        execution_id = self._get_or_create_execution_state(task)

        # 2. 从数据库恢复上下文
        state = self.state_store.get_state(execution_id)
        if not state:
            raise ValueError(f"Execution state {execution_id} not found")

        # 3. 运行 Agent tool-calling 循环
        while state["current_round"] < state["max_rounds"]:
            # 3.1 定期续约锁
            self.lock_manager.extend_lock(task.task_id, self.worker_id)

            # 3.2 调用 LLM
            llm_result = self._call_llm(state["messages"], state["agent_id"])

            # 3.3 处理 tool calls
            if llm_result["finish_reason"] == "tool_calls":
                tool_results = self._execute_tools(llm_result["tool_calls"], state)

                # 3.4 更新状态
                state["messages"].extend([
                    {"role": "assistant", "content": None, "tool_calls": llm_result["tool_calls"]},
                    *tool_results
                ])
                state["current_round"] += 1
                state["assistant_content"] += llm_result.get("content", "")

                # 3.5 持久化状态
                self.state_store.update_state(execution_id, state)

                # 3.6 如果有写操作，创建待审批任务
                if tool_results_contain_write_tasks:
                    # 任务进入 waiting_approval 状态
                    state["state"] = "waiting_approval"
                    self.state_store.update_state(execution_id, state)
                    # 暂停处理，等待用户审批
                    break
            else:
                # 完成
                state["assistant_content"] += llm_result.get("content", "")
                state["state"] = "completed"
                self.state_store.update_state(execution_id, state)
                break

        # 4. 持久化最终结果到 ai_chat_messages
        self._save_assistant_message(task.session_id, state["assistant_content"])

        # 5. 标记任务完成
        self.task_queue.complete_task(task.task_id, {"execution_id": execution_id})

        # 6. 释放锁
        self.lock_manager.release_lock(task.task_id, self.worker_id)

    def _get_or_create_execution_state(self, task: WorkTask) -> str:
        """获取或创建执行状态"""
        # 检查是否已存在（断点续传场景）
        existing = self.state_store.find_by_task_id(task.task_id)
        if existing:
            return existing["execution_id"]

        # 创建新状态
        return self.state_store.create_state(task.task_id, {
            "session_id": task.session_id,
            "agent_id": task.agent_id,
            "messages": self._build_initial_messages(task),
            "current_round": 0,
            "max_rounds": 6,
            "state": "initializing"
        })

    def _build_initial_messages(self, task: WorkTask) -> List[dict]:
        """构建初始消息列表（从数据库加载历史）"""
        # 从 ai_chat_messages 表加载历史消息
        history = ai_chat_service.list_messages(task.session_id, limit=20)

        # 构建 system prompt
        agent_def = agent_registry.get(task.agent_id)
        system_prompt = agent_def.system_prompt
        if task.project_id:
            system_prompt += f"\n\n当前项目ID: {task.project_id}"

        messages = [{"role": "system", "content": system_prompt}]

        # 添加历史对话
        for msg in history:
            if msg["role"] in ("user", "assistant"):
                messages.append({"role": msg["role"], "content": msg["content"]})

        return messages
```

#### 3.2.2 修改 API Gateway

**历史文件位置**：`backend_business/routes/ai_chat_routes.py`（该文件已删除）

**改造前**（同步模型）：
```python
@ai_chat_bp.route("/stream", methods=["POST"])
def stream_chat():
    # 直接调用 agent_runner.stream()
    return Response(agent_runner.stream(...), mimetype="text/event-stream")
```

**改造后**（异步模型）：
```python
@ai_chat_bp.route("/stream", methods=["POST"])
def stream_chat():
    """接收用户消息，创建任务，立即返回 task_id"""
    payload = request.get_json()
    user_id = _get_actor()
    session_id = payload.get("session_id")
    user_content = payload.get("content")
    agent_id = payload.get("agent_id", "conductor_agent")
    project_id = payload.get("project_id")

    # 1. 持久化用户消息
    user_msg = ai_chat_service.create_message(
        session_id=session_id,
        user_id=user_id,
        role="user",
        content=user_content,
        is_read=True
    )

    # 2. 创建任务并加入队列
    task = task_queue.enqueue(WorkTask(
        session_id=session_id,
        user_id=user_id,
        agent_id=agent_id,
        project_id=project_id,
        user_message_id=user_msg["message_id"],
        user_content=user_content,
        priority=0  # 可根据用户等级设置优先级
    ))

    # 3. 返回 SSE 流（监听任务进度）
    return Response(
        _stream_task_progress(task["task_id"]),
        mimetype="text/event-stream"
    )

def _stream_task_progress(task_id: str):
    """通过 SSE 流式返回任务进度"""
    # 订阅 Redis Pub/Sub 或轮询数据库
    pubsub = redis_client.pubsub()
    pubsub.subscribe(f"agent_task_progress:{task_id}")

    try:
        for message in pubsub.listen():
            if message["type"] == "message":
                data = json.loads(message["data"])
                event_type = data.get("event")

                if event_type == "token":
                    yield f"event: token\ndata: {json.dumps(data)}\n\n"
                elif event_type == "tool_call":
                    yield f"event: tool_call\ndata: {json.dumps(data)}\n\n"
                elif event_type == "completed":
                    yield f"event: done\ndata: {json.dumps(data)}\n\n"
                    break
                elif event_type == "error":
                    yield f"event: error\ndata: {json.dumps(data)}\n\n"
                    break
    finally:
        pubsub.unsubscribe()
```

**新增进度推送机制**：

在 `StatelessAgentWorker._process_task()` 中添加进度发布：
```python
def _publish_progress(self, task_id: str, event: str, data: dict) -> None:
    """发布任务进度到 Redis Pub/Sub"""
    redis_client.publish(
        f"agent_task_progress:{task_id}",
        json.dumps({"event": event, **data})
    )

# 在 LLM streaming 时调用
for chunk in llm_stream:
    if chunk["type"] == "content":
        self._publish_progress(task.task_id, "token", {"content": chunk["content"]})
```

### 3.3 Phase 3: 审批流程集成（第 5 周）

#### 3.3.1 待审批任务处理

**场景**：Agent 调用写操作 Tool 时，需要创建 `agent_pending_tasks` 并等待用户审批。

**改造点**：
1. **暂停任务执行**：
   - 将 `agent_work_tasks.status` 更新为 `processing`（保持锁）
   - 将 `agent_execution_states.state` 更新为 `waiting_approval`
   - Worker 释放该任务，继续处理其他任务

2. **用户审批后恢复**：
   - 用户点击「批准」或「拒绝」后，前端调用 `/api/agent-tasks/<task_id>/approve`
   - 后端在 `approve_task()` 中执行写操作
   - 创建一个新的 `agent_work_tasks` 任务（类型为 `resume`），让 Worker 继续执行

**代码示例**：
```python
# agent/queue/task_queue.py
def pause_for_approval(self, task_id: str, pending_task_ids: List[str]) -> None:
    """暂停任务，等待审批"""
    with db_service._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE agent_work_tasks
                SET metadata = metadata || jsonb_build_object('pending_approvals', %s::jsonb)
                WHERE task_id = %s
                """,
                (json.dumps(pending_task_ids), task_id)
            )

            # 执行状态更新为 waiting_approval
            cur.execute(
                """
                UPDATE agent_execution_states
                SET state = 'waiting_approval', updated_at = NOW()
                WHERE task_id = %s
                """,
                (task_id,)
            )

def resume_after_approval(self, original_task_id: str) -> str:
    """审批完成后，创建恢复任务"""
    # 查询原任务
    original_task = self.get_task(original_task_id)
    if not original_task:
        raise ValueError("Original task not found")

    # 创建恢复任务（复用原任务的 session_id, agent_id 等）
    resume_task_id = f"resume_{uuid.uuid4().hex[:12]}"
    with db_service._connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO agent_work_tasks (
                    task_id, session_id, user_id, agent_id, project_id,
                    user_message_id, user_content, status, priority,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, 'pending', 10, %s)
                """,
                (
                    resume_task_id,
                    original_task["session_id"],
                    original_task["user_id"],
                    original_task["agent_id"],
                    original_task["project_id"],
                    original_task["user_message_id"],
                    "[RESUME] Continue from approval",
                    json.dumps({"resume_from": original_task_id})
                )
            )

    # 加入 Redis 队列（高优先级）
    redis_client.zadd("agent_task_queue:pending", {resume_task_id: 10})

    return resume_task_id
```

### 3.4 Phase 4: 监控和运维（第 6 周）

#### 3.4.1 管理 API

**历史 Route 位置**：`backend_business/routes/agent_monitor_routes.py`（该文件已删除）

**端点设计**：
```python
# 任务监控
GET  /api/agent-monitor/tasks?status=processing&limit=50
GET  /api/agent-monitor/tasks/<task_id>
POST /api/agent-monitor/tasks/<task_id>/cancel
POST /api/agent-monitor/tasks/<task_id>/retry

# Worker 监控
GET  /api/agent-monitor/workers
GET  /api/agent-monitor/workers/<worker_id>
POST /api/agent-monitor/workers/<worker_id>/shutdown

# 队列统计
GET  /api/agent-monitor/queue/stats
GET  /api/agent-monitor/queue/metrics

# 死信队列
GET  /api/agent-monitor/dead-letter
POST /api/agent-monitor/dead-letter/<task_id>/requeue
```

#### 3.4.2 健康检查

**锁过期清理**（定时任务）：
```python
# backend_business/services/agent/queue/maintenance.py
class QueueMaintenance:
    def cleanup_expired_locks(self) -> int:
        """清理过期的任务锁（Worker 崩溃导致）"""
        with db_service._connect() as conn:
            with conn.cursor() as cur:
                # 查找锁过期但状态仍为 processing 的任务
                cur.execute(
                    """
                    UPDATE agent_work_tasks
                    SET status = 'pending', worker_id = NULL, locked_at = NULL, lock_expires_at = NULL
                    WHERE status = 'processing' AND lock_expires_at < NOW()
                    RETURNING task_id
                    """
                )
                expired_tasks = [row[0] for row in cur.fetchall()]

        # 重新加入 Redis 队列
        for task_id in expired_tasks:
            redis_client.zadd("agent_task_queue:pending", {task_id: 0})

        return len(expired_tasks)

    def cleanup_stale_workers(self) -> int:
        """清理心跳超时的 Worker"""
        timeout_threshold = datetime.now() - timedelta(seconds=30)

        with db_service._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE agent_workers
                    SET status = 'offline'
                    WHERE status != 'offline' AND last_heartbeat < %s
                    RETURNING worker_id
                    """,
                    (timeout_threshold,)
                )
                stale_workers = [row[0] for row in cur.fetchall()]

        # 从 Redis 移除
        for worker_id in stale_workers:
            redis_client.srem("agent_workers:online", worker_id)

        return len(stale_workers)
```

**启动定时任务**（Flask-APScheduler 或 Celery Beat）：
```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
maintenance = QueueMaintenance()

# 每 30 秒执行一次
scheduler.add_job(maintenance.cleanup_expired_locks, 'interval', seconds=30)
scheduler.add_job(maintenance.cleanup_stale_workers, 'interval', seconds=30)

scheduler.start()
```

#### 3.4.3 Metrics 和可观测性

**新增 Prometheus Metrics**：
```python
from prometheus_client import Counter, Gauge, Histogram

# 任务计数
tasks_enqueued = Counter('agent_tasks_enqueued_total', 'Total tasks enqueued')
tasks_completed = Counter('agent_tasks_completed_total', 'Total tasks completed')
tasks_failed = Counter('agent_tasks_failed_total', 'Total tasks failed')

# 队列长度
queue_length = Gauge('agent_queue_length', 'Current queue length', ['status'])

# Worker 数量
workers_online = Gauge('agent_workers_online', 'Number of online workers')

# 任务处理时长
task_duration = Histogram('agent_task_duration_seconds', 'Task processing duration')

# 在相应的代码位置埋点
def enqueue(self, task: WorkTask) -> str:
    tasks_enqueued.inc()
    queue_length.labels(status='pending').inc()
    # ...

def complete_task(self, task_id: str, result: dict) -> None:
    tasks_completed.inc()
    queue_length.labels(status='pending').dec()
    # ...
```

**暴露 Metrics 端点**：
```python
# backend_business/routes/metrics_routes.py
from flask import Blueprint
from prometheus_client import generate_latest

metrics_bp = Blueprint("metrics", __name__)

@metrics_bp.route("/metrics", methods=["GET"])
def prometheus_metrics():
    return generate_latest(), 200, {"Content-Type": "text/plain; charset=utf-8"}
```

### 3.5 Phase 5: 部署和扩展（第 7-8 周）

#### 3.5.1 Docker 化

**新增 Dockerfile**：
```dockerfile
# Dockerfile.worker
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend_business/ ./backend_business/
COPY backend_inference/ ./backend_inference/

# Worker 启动脚本
CMD ["python", "-m", "backend_business.services.agent.worker_main"]
```

**Worker 启动脚本**：`backend_business/services/agent/worker_main.py`
```python
import os
import uuid
import signal
import logging
from worker import StatelessAgentWorker

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def main():
    worker_id = os.getenv("WORKER_ID") or f"worker_{uuid.uuid4().hex[:8]}"
    worker = StatelessAgentWorker(worker_id)

    # 优雅关闭
    def signal_handler(sig, frame):
        logger.info(f"Worker {worker_id} received shutdown signal")
        worker.shutdown()

    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    logger.info(f"Worker {worker_id} starting...")
    worker.run_forever()

if __name__ == "__main__":
    main()
```

#### 3.5.2 Docker Compose 配置

**更新 `docker-compose.yml`**：
```yaml
version: '3.8'

services:
  postgres:
    image: postgres:15
    # ... 现有配置 ...

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

  backend-business:
    build:
      context: .
      dockerfile: Dockerfile
    depends_on:
      - postgres
      - redis
    environment:
      TASK_QUEUE_ENABLED: "true"
      REDIS_HOST: redis
      REDIS_PORT: 6379
    # ... 现有配置 ...

  # Worker 节点（可扩展多个）
  agent-worker-1:
    build:
      context: .
      dockerfile: Dockerfile.worker
    depends_on:
      - postgres
      - redis
      - backend-business
    environment:
      WORKER_ID: "worker-1"
      REDIS_HOST: redis
      REDIS_PORT: 6379
      DATABASE_URL: ${DATABASE_URL}
      INFERENCE_BASE_URL: http://backend-inference:8000
    restart: unless-stopped

  agent-worker-2:
    build:
      context: .
      dockerfile: Dockerfile.worker
    depends_on:
      - postgres
      - redis
      - backend-business
    environment:
      WORKER_ID: "worker-2"
      REDIS_HOST: redis
      REDIS_PORT: 6379
      DATABASE_URL: ${DATABASE_URL}
      INFERENCE_BASE_URL: http://backend-inference:8000
    restart: unless-stopped

  # ... 可以继续添加 worker-3, worker-4 等 ...

volumes:
  redis_data:
```

#### 3.5.3 横向扩展

**自动扩展（Kubernetes）**：
```yaml
# k8s/worker-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: agent-worker
spec:
  replicas: 3  # 初始 3 个 Worker
  selector:
    matchLabels:
      app: agent-worker
  template:
    metadata:
      labels:
        app: agent-worker
    spec:
      containers:
      - name: worker
        image: semantic-atlas-worker:latest
        env:
        - name: WORKER_ID
          valueFrom:
            fieldRef:
              fieldPath: metadata.name  # 使用 Pod 名称作为 Worker ID
        - name: REDIS_HOST
          value: "redis-service"
        - name: DATABASE_URL
          valueFrom:
            secretKeyRef:
              name: db-secret
              key: url
        resources:
          requests:
            cpu: 500m
            memory: 1Gi
          limits:
            cpu: 2000m
            memory: 4Gi
---
# HPA（水平自动扩展）
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: agent-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: agent-worker
  minReplicas: 3
  maxReplicas: 20
  metrics:
  - type: Resource
    resource:
      name: cpu
      target:
        type: Utilization
        averageUtilization: 70
  - type: Pods
    pods:
      metric:
        name: agent_queue_length
      target:
        type: AverageValue
        averageValue: "10"  # 每个 Worker 平均处理 10 个任务时触发扩展
```

---

## 四、兼容性方案

### 4.1 渐进式迁移策略

为了不影响现有功能，采用**双模式运行**策略：

**配置开关**：
```python
# backend_business/config.py
TASK_QUEUE_ENABLED = os.getenv("TASK_QUEUE_ENABLED", "false").lower() == "true"
```

**API 路由适配**：
```python
# backend_business/routes/ai_chat_routes.py（历史示例，文件已删除）
@ai_chat_bp.route("/stream", methods=["POST"])
def stream_chat():
    if TASK_QUEUE_ENABLED:
        # 新模式：任务队列
        return _stream_chat_queue_mode()
    else:
        # 旧模式：同步执行
        return _stream_chat_legacy_mode()

def _stream_chat_legacy_mode():
    """现有的同步模式（保持向后兼容）"""
    # 现有代码不变
    return Response(agent_runner.stream(...), mimetype="text/event-stream")

def _stream_chat_queue_mode():
    """新的队列模式"""
    # 创建任务并加入队列
    task = task_queue.enqueue(...)
    return Response(_stream_task_progress(task["task_id"]), mimetype="text/event-stream")
```

### 4.2 数据迁移

**现有数据不受影响（历史描述，现已过时）**：
- `ai_chat_sessions` 和 `ai_chat_messages` 在当前代码中已移除，不再作为保留表
- 新增的表只用于队列和状态管理

**迁移路径**：
1. **Phase 1-2**：基础设施搭建，但不启用（`TASK_QUEUE_ENABLED=false`）
2. **Phase 3**：在测试环境启用，验证功能
3. **Phase 4**：在生产环境灰度发布（少量用户）
4. **Phase 5**：全量切换

---

## 五、性能和容量规划

### 5.1 性能指标

**目标**：
- **吞吐量**：单 Worker 处理 5-10 个并发任务
- **响应时间**：P99 延迟 < 5s（从入队到开始处理）
- **扩展性**：支持 100+ 并发用户，通过增加 Worker 线性扩展

**瓶颈分析**：
1. **PostgreSQL 写入**：每个任务需要写入 3-5 次（状态更新）
   - 优化：使用连接池，批量更新
2. **Redis 操作**：队列操作频繁
   - 优化：使用 Pipeline 批量操作
3. **LLM 推理**：最大瓶颈（10-30s 每轮）
   - 优化：异步执行，多个 Worker 并行

### 5.2 容量估算

**假设**：
- 100 个并发用户
- 每个用户平均每分钟发送 1 条消息
- 每条消息平均需要 3 轮 tool-calling
- 每轮 LLM 调用耗时 10s

**计算**：
- 总 QPS = 100 用户 × 1 消息/分钟 ÷ 60s ≈ 1.67 QPS
- 平均任务耗时 = 3 轮 × 10s = 30s
- 所需 Worker 数 = QPS × 平均耗时 = 1.67 × 30 ≈ 50 个并发任务
- 如果单 Worker 处理 5 个并发任务，需要 **10 个 Worker**

**推荐配置**：
- **小规模（10-20 用户）**：2-3 个 Worker
- **中规模（50-100 用户）**：5-10 个 Worker
- **大规模（100+ 用户）**：10-20 个 Worker（配合 HPA 自动扩展）

### 5.3 Redis 内存估算

**数据结构**：
- 任务队列：每个 task_id 64 字节
- 执行状态缓存：每个 execution_state ~10KB（messages 数组）
- Worker 在线列表：每个 worker_id 32 字节

**估算**：
- 1000 个待处理任务：64B × 1000 = 64KB
- 100 个活跃会话（缓存状态）：10KB × 100 = 1MB
- 20 个 Worker：32B × 20 = 640B

**总计**：< 10MB（Redis 非常轻量）

---

## 六、测试计划

### 6.1 单元测试

**测试文件**：`tests/agent/queue/`

**覆盖范围**：
- `TaskQueue` 的 enqueue/dequeue/complete/fail
- `ExecutionStateStore` 的 CRUD 操作
- `LockManager` 的分布式锁逻辑
- `WorkerRegistry` 的注册和心跳

### 6.2 集成测试

**场景**：
1. **基本流程**：用户发消息 → Worker 处理 → 返回结果
2. **并发处理**：10 个用户同时发消息，多个 Worker 并行处理
3. **锁竞争**：2 个 Worker 尝试抢同一个任务
4. **断点续传**：Worker 处理到一半崩溃，另一个 Worker 从检查点恢复
5. **审批流程**：Agent 调用写操作 → 创建待审批任务 → 用户批准 → 恢复执行

### 6.3 压力测试

**工具**：Locust 或 JMeter

**场景**：
- 100 个虚拟用户，每人每分钟发送 1 条消息
- 持续 10 分钟
- 监控指标：
  - 队列长度变化
  - Worker CPU/内存使用率
  - 数据库连接池状态
  - P50/P95/P99 响应时间

---

## 七、潜在风险和缓解措施

### 7.1 风险识别

| 风险 | 影响 | 概率 | 缓解措施 |
|------|------|------|----------|
| Redis 单点故障 | 任务队列不可用 | 中 | 使用 Redis Sentinel 或 Redis Cluster 实现高可用 |
| PostgreSQL 写入瓶颈 | 状态更新延迟 | 中 | 使用连接池、批量更新、读写分离 |
| 锁泄漏（Worker 崩溃未释放锁） | 任务永久阻塞 | 高 | 锁带 TTL，定时任务清理过期锁 |
| 任务堆积（Worker 不足） | 用户等待时间过长 | 中 | HPA 自动扩展，死信队列监控 |
| 状态不一致（Redis 和 PG 不同步） | 执行错误 | 低 | 以 PostgreSQL 为 source of truth，Redis 只做缓存 |

### 7.2 回滚策略

**如果新架构出现问题，可以快速回滚**：
1. 设置 `TASK_QUEUE_ENABLED=false`
2. 重启 backend_business 服务
3. 恢复到旧的同步模式（现有代码保持不变）

---

## 八、总结

### 8.1 改造前 vs 改造后

| 维度 | 改造前 | 改造后 |
|------|--------|--------|
| **并发能力** | 受限于单进程线程数 | 支持 100+ 并发用户（横向扩展） |
| **可靠性** | 服务重启丢失上下文 | 状态持久化，断点续传 |
| **资源利用** | 100 用户需要 100 线程 | 10 个 Worker 即可处理 100 用户 |
| **扩展性** | 无法横向扩展 | 增加 Worker 数量线性扩展 |
| **运维复杂度** | 低（单体应用） | 中（需要 Redis、任务队列监控） |

### 8.2 实施时间表

| 阶段 | 周期 | 产出 |
|------|------|------|
| Phase 1: 基础设施准备 | 1-2 周 | 数据库表、Redis 配置、服务类 |
| Phase 2: 无状态 Runner 改造 | 3-4 周 | StatelessAgentWorker、API Gateway 改造 |
| Phase 3: 审批流程集成 | 5 周 | 待审批任务处理、恢复机制 |
| Phase 4: 监控和运维 | 6 周 | 管理 API、健康检查、Metrics |
| Phase 5: 部署和扩展 | 7-8 周 | Docker 化、K8s 部署、压力测试 |

**总计**：约 2 个月（8 周）

### 8.3 下一步行动

1. **评审本文档**：与团队讨论技术选型和架构设计
2. **搭建测试环境**：启动 Redis，创建测试数据库
3. **实现 Phase 1**：先完成基础设施（表、Redis 客户端、服务类）
4. **开发 MVP**：实现最小可用版本（单个 Worker + 基本队列）
5. **逐步迭代**：按照 Phase 2-5 逐步完善功能

---

## 附录

### A. 术语表

- **Worker**：无状态的任务处理进程，从队列取任务并执行
- **Task Queue**：存储待处理用户消息的队列
- **Execution State**：Agent 执行过程的中间状态（messages, round_number 等）
- **Distributed Lock**：分布式锁，防止多个 Worker 同时处理同一任务
- **Checkpoint**：检查点，用于断点续传

### B. 参考资料

- [Celery Documentation](https://docs.celeryproject.org/)（类似的分布式任务队列）
- [Redis as a Message Queue](https://redis.io/docs/manual/patterns/pub-sub/)
- [PostgreSQL Advisory Locks](https://www.postgresql.org/docs/current/explicit-locking.html#ADVISORY-LOCKS)（可选的锁机制）
- [Kubernetes HPA](https://kubernetes.io/docs/tasks/run-application/horizontal-pod-autoscale/)

### C. 配置示例

**.env 文件**：
```bash
# Redis
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# Task Queue
TASK_QUEUE_ENABLED=true
TASK_LOCK_TTL=60
WORKER_HEARTBEAT_INTERVAL=10
WORKER_MAX_CONCURRENT_TASKS=5

# PostgreSQL
DATABASE_URL=postgresql://user:password@localhost:5432/semantic_atlas

# Inference
INFERENCE_BASE_URL=http://localhost:8000
```

---

**文档版本**：v1.0
**最后更新**：2026-02-10
**作者**：Claude Sonnet 4.5
