# Agent 通用设施抽取方案

---

## 概述

当前需求管理 Agent (`backend_business/services/agent/agents/requirement_agent/`) 的实现中包含了大量可复用的通用逻辑。本文档分析哪些组件应抽取为独立的基础设施，以支持后续质检 Agent、冲突检测 Agent 等其他 Agent 的开发。

---

## 一、现状分析

### 1.1 当前需求管理 Agent 组件结构

```
backend_business/services/agent/agents/requirement_agent/
├── __init__.py
├── service.py                      # 主体服务编排
├── actor_runtime.py                # Actor 运行时
├── runtime_graph_recorder.py       # 运行时图记录器
├── tool_loop_runner.py             # 工具循环运行器
├── prompt_builder.py               # Prompt 构建器（业务特定）
├── constants.py                    # 常量定义
├── payload_codec.py                # Payload 编解码
└── utils.py                        # 工具函数

backend_business/services/agent/
├── execution_graph_service.py      # 执行图 CRUD 服务（已独立）
├── tools/
│   └── requirement_agent_tools.py  # 工具定义
├── coordinator/
│   └── distributed_coordinator.py  # 分布式协调器
└── (其他模块)
```

### 1.2 执行图数据流

```
用户输入
    ↓
stream_requirement_agent_reply()
    ↓
create_message (用户消息)
    ↓
RuntimeGraphRecorder 初始化/加载
    ↓
start_stage(user_input, start节点, human_input容器)
    ↓
ToolLoopRunner.run()
    ├─ start_stage(tool_loop_round_N, llm节点, requirements_agent容器)
    ├─ ai_proxy.chat_completion_with_tools()
    ├─ tools.execute() → record_tool_call_result()
    ├─ complete_stage()
    └─ 最多6轮循环
    ↓
start_stage(conductor_reply, end节点, conductor容器)
    ↓
LLM 生成最终回复
    ↓
succeed_graph() / suspend_graph()
```

---

## 二、组件通用性分类

### 2.1 第一层：完全通用的基础设施

| 组件 | 当前位置 | 通用性 | 抽取建议 |
|------|---------|--------|---------|
| **ExecutionGraphService** | `agent/execution_graph_service.py` | 100% | 已是独立模块，无需修改 |
| **运行时图记录器** | `requirement_agent/runtime_graph_recorder.py` | 90% | 需去掉硬编码容器定义 |
| **工具循环运行器** | `requirement_agent/tool_loop_runner.py` | 80% | 抽取 LLM 循环和工具执行逻辑 |
| **Actor 运行时** | `requirement_agent/actor_runtime.py` | 100% | 已独立，命名需中性化 |

### 2.2 第二层：半通用组件

| 组件 | 当前位置 | 通用性 | 抽取建议 |
|------|---------|--------|---------|
| **PromptBuilder** | `requirement_agent/prompt_builder.py` | 40% | 抽取通用框架，业务 prompt 由子类实现 |
| **ToolManager** | `agent/tools/requirement_agent_tools.py` | 60% | 定义通用接口，工具由各 Agent 注册 |

### 2.3 第三层：完全业务特定（保持不变）

| 组件 | 原因 |
|------|------|
| **RequirementAgentChatService** | 整体编排逻辑，各 Agent 差异大 |
| **业务 Prompt 内容** | 领域知识，不可通用 |
| **具体工具实现** | 如 `update_requirement_content` 是需求领域特定 |

---

## 三、抽取方案详解

### 3.1 RuntimeGraphRecorder 通用化

#### 当前问题

容器定义硬编码在实现中：
```python
# requirement_agent/runtime_graph_recorder.py
class _RuntimeGraphRecorder:
    _CONTAINERS = (
        ("human_input", "Human Input", "human"),
        ("conductor", "Conductor", "agent"),
        ("requirements_agent", "Requirements Agent", "agent"),
        ("requirements_tools", "Requirement Tools", "system"),
    )
```

#### 抽取方案

```
agent/runtime/
├── __init__.py
├── graph_recorder.py              # 通用运行时图记录器
│   ├── RuntimeGraphRecorder       # 容器定义可配置
│   ├── StageNode                  # 节点数据类
│   └── ContainerConfig            # 容器配置
└── context.py                     # 上下文管理
    ├── ExecutionContext           # 执行上下文
    └── ContextEntry               # 上下文条目
```

#### API 设计

```python
# agent/runtime/graph_recorder.py
from typing import Protocol
from dataclasses import dataclass

@dataclass
class ContainerConfig:
    container_key: str
    label: str
    role_type: str  # "human", "agent", "system"

@dataclass
class StageNode:
    node_id: str
    node_key: str
    label: str
    node_type: str
    role_type: str
    container_id: str

class RuntimeGraphRecorder:
    def __init__(
        self,
        *,
        execution_graph_service: ExecutionGraphService,
        container_configs: list[ContainerConfig],
        project_id: str,
        user_id: str,
        session_id: str,
        user_message: str,
        graph_id: str | None = None,
    ) -> None:
        self._service = execution_graph_service
        self._container_configs = {c.container_key: c for c in container_configs}
        # ... 其余初始化逻辑

    def start_stage(
        self,
        *,
        node_key: str,
        label: str,
        node_type: str,
        role_type: str,
        container_key: str,
        created_by: str,
        input_summary: Any,
        edge_type_from_previous: str | None = "call",
    ) -> StageNode:
        # ... 通用实现

    def record_tool_call_result(
        self,
        node_key: str,
        *,
        created_by: str,
        tool_name: str,
        request_payload: Any,
        result_payload: Any,
    ) -> None:
        # ... 通用实现

    def complete_stage(
        self,
        node_key: str,
        *,
        created_by: str,
        output_summary: Any,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        # ... 通用实现

    def succeed_graph(self, *, created_by: str, final_reply: str) -> None:
        # ... 通用实现

    def suspend_graph(self, *, created_by: str, final_reply: str) -> None:
        # ... 通用实现

    def fail_graph(self, *, created_by: str, error: str) -> None:
        # ... 通用实现

    @property
    def historical_node_context(self) -> list[dict[str, Any]]:
        # ... 通用实现
```

#### 使用示例

```python
# 需求 Agent
containers = [
    ContainerConfig("human_input", "Human Input", "human"),
    ContainerConfig("conductor", "Conductor", "agent"),
    ContainerConfig("requirements_agent", "Requirements Agent", "agent"),
    ContainerConfig("requirements_tools", "Requirement Tools", "system"),
]
recorder = RuntimeGraphRecorder(
    execution_graph_service=service,
    container_configs=containers,
    project_id=project_id,
    user_id=user_id,
    session_id=session_id,
    user_message=user_message,
)

# 质检 Agent
qa_containers = [
    ContainerConfig("human_input", "Human Input", "human"),
    ContainerConfig("conductor", "Conductor", "agent"),
    ContainerConfig("qa_agent", "QA Agent", "agent"),
]
qa_recorder = RuntimeGraphRecorder(
    execution_graph_service=service,
    container_configs=qa_containers,
    # ...
)
```

### 3.2 ToolLoopRunner 通用化

#### 当前问题

工具循环运行器与 Prompt 构建耦合：
```python
# requirement_agent/tool_loop_runner.py
class RequirementAgentToolLoopRunner:
    def run(
        self,
        *,
        recorder: _RuntimeGraphRecorder,
        # ...
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.prompt_builder.build_tool_loop_system_prompt()},
            {"role": "user", "content": self.prompt_builder.build_tool_loop_user_message(...)},
        ]
        # ...
```

#### 抽取方案

```
agent/execution/
├── __init__.py
├── tool_loop_runner.py           # 通用工具循环运行器
│   ├── ToolLoopRunner            # 不含 prompt 构建
│   ├── ToolExecutionContext      # 执行上下文
│   └── ToolCallEvent            # 工具调用事件
└── prompt_interface.py           # Prompt 构建接口
    ├── PromptBuilderProtocol     # 抽象协议
    ├── SystemPromptBuilder       # system_prompt 构建
    └── UserPromptBuilder        # user_prompt 构建
```

#### API 设计

```python
# agent/execution/prompt_interface.py
from typing import Protocol, Any

class PromptBuilderProtocol(Protocol):
    def build_system_prompt(
        self,
        context: dict[str, Any],
    ) -> str: ...

    def build_user_message(
        self,
        user_message: str,
        context: dict[str, Any],
    ) -> str: ...

    def get_tools_list(self) -> list[dict[str, Any]]: ...

# agent/execution/tool_loop_runner.py
@dataclass
class ToolCallEvent:
    graph_id: str
    node_key: str
    tool: str
    tool_call_id: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None

@dataclass
class ToolLoopResult:
    tool_loop_reply: str
    context: dict[str, Any]
    rounds: int

class ToolLoopRunner:
    def __init__(
        self,
        *,
        ai_proxy_client: Any,
        tool_executor: Any,  # 工具执行器接口
        prompt_builder: PromptBuilderProtocol,
        max_tool_call_rounds: int = 6,
    ) -> None:
        self.ai_proxy = ai_proxy_client
        self.tool_executor = tool_executor
        self.prompt_builder = prompt_builder
        self.max_tool_call_rounds = max_tool_call_rounds

    def run(
        self,
        *,
        recorder: Any,  # RuntimeGraphRecorder 协议
        user_id: str,
        user_message: str,
        context: dict[str, Any],
    ) -> Generator[dict[str, Any], None, ToolLoopResult]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.prompt_builder.build_system_prompt(context)},
            {"role": "user", "content": self.prompt_builder.build_user_message(user_message, context)},
        ]

        for round_index in range(1, self.max_tool_call_rounds + 1):
            # ... 通用循环逻辑

            response = self.ai_proxy.chat_completion_with_tools(
                messages=messages,
                tools=self.prompt_builder.get_tools_list(),
                # ...
            )

            # 工具执行
            for tool_call in tool_calls:
                result = self.tool_executor.execute(tool_name, arguments, context)
                # ...

            if no_more_tool_calls:
                return ToolLoopResult(...)

        raise RuntimeError(f"工具调用轮数超过上限 {self.max_tool_call_rounds}")
```

#### 使用示例

```python
# 需求 Agent 的实现
class RequirementAgentPromptBuilder:
    def build_system_prompt(self, context: dict[str, Any]) -> str:
        return "你是需求管理 Agent..."

    def build_user_message(self, user_message: str, context: dict[str, Any]) -> str:
        return serialize_prompt_payload({...})

    def get_tools_list(self) -> list[dict[str, Any]]:
        return RequirementAgentTools().get_tools_list()

runner = ToolLoopRunner(
    ai_proxy_client=ai_proxy,
    tool_executor=tools,
    prompt_builder=RequirementAgentPromptBuilder(),
    max_tool_call_rounds=6,
)
```

### 3.3 ActorRuntime 中性化

#### 当前问题

命名绑定到需求领域：
```python
# requirement_agent/actor_runtime.py
class RequirementAgentActorRuntime:
    def get_actor_manager(self):
        # ...
```

#### 抽取方案

```
agent/actor/
├── __init__.py
└── actor_runtime.py             # 中性化命名
    └── AgentActorRuntime         # 通用 Actor 运行时
```

#### API 设计

```python
# agent/actor/actor_runtime.py
import asyncio
import threading
from typing import Any

class AgentActorRuntime:
    """通用 Agent Actor 运行时，提供异步事件循环和 Actor 访问"""

    def __init__(self) -> None:
        self._actor_loop: asyncio.AbstractEventLoop | None = None
        self._actor_loop_thread: threading.Thread | None = None

    def get_actor_manager(self) -> Any:
        """获取 ActorManager 实例（单例）"""
        from backend_business.services.actor.actor_manager import ActorManager
        from backend_business.services.agent.coordinator.distributed_coordinator import (
            DistributedActorCoordinator,
        )
        from backend_business.services.event_store.event_store import EventStore

        from backend_business.config import settings

        event_store = EventStore(settings.POSTGRES_DSN)
        coordinator = None
        if settings.REDIS_URL:
            coordinator = DistributedActorCoordinator(
                redis_url=settings.REDIS_URL,
                instance_id=self._get_instance_id(),
            )
        return ActorManager.get_instance(event_store, coordinator=coordinator)

    def ensure_actor_loop(self) -> asyncio.AbstractEventLoop:
        """确保 Actor 事件循环已创建"""
        if self._actor_loop and self._actor_loop_thread and self._actor_loop_thread.is_alive():
            return self._actor_loop

        loop = asyncio.new_event_loop()

        def _runner():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(
            target=_runner,
            name="agent-actor-loop",
            daemon=True,
        )
        thread.start()
        self._actor_loop = loop
        self._actor_loop_thread = thread
        return loop

    def run_actor_coro(self, coro: Any) -> Any:
        """在 Actor 线程中运行协程"""
        loop = self.ensure_actor_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)

    def actor_query(self, actor_manager: Any, entity_id: str) -> dict[str, Any]:
        """Actor Ask 查询"""
        return self.run_actor_coro(
            actor_manager.send_command(
                entity_id,
                {"type": "QueryState", "source": "agent"},
            )
        )

    def actor_write(self, actor_manager: Any, entity_id: str, command: dict[str, Any]) -> dict[str, Any]:
        """Actor 写命令"""
        return self.run_actor_coro(actor_manager.send_command(entity_id, command))

    @staticmethod
    def _get_instance_id() -> str:
        """获取实例 ID，用于分布式协调"""
        import socket
        import os
        return f"{socket.gethostname()}-{os.getpid()}"
```

### 3.4 工具管理通用化

#### 抽取方案

```
agent/tools/
├── __init__.py
├── base.py                        # 工具基类 [新建]
│   ├── ToolExecutorProtocol       # 工具执行器协议
│   ├── ToolDefinition             # 工具定义
│   └── ToolRegistry              # 工具注册表
└── requirement_agent_tools.py     # 继承基类
```

#### API 设计

```python
# agent/tools/base.py
from typing import Protocol, Any, Callable
from dataclasses import dataclass
from enum import Enum

class ContextMode(Enum):
    """工具结果上下文模式"""
    TRANSPARENT = "transparent"  # 结果保留在节点上下文中
    OPAQUE = "opaque"            # 结果仅在本节点内消费

@dataclass
class ToolDefinition:
    """工具定义"""
    name: str
    description: str
    parameters: dict[str, Any]  # JSON Schema 格式的参数定义
    context_mode: ContextMode = ContextMode.TRANSPARENT
    executor: Callable | None = None

class ToolExecutorProtocol(Protocol):
    """工具执行器协议"""

    def get_tools_list(self) -> list[dict[str, Any]]:
        """获取工具列表，用于 LLM 工具调用"""
        ...

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """执行工具"""
        ...

class ToolRegistry:
    """工具注册表"""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get_tools_list(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                },
            }
            for tool in self._tools.values()
        ]

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        tool = self._tools.get(tool_name)
        if not tool:
            raise ValueError(f"工具不存在: {tool_name}")
        if not tool.executor:
            raise ValueError(f"工具未实现执行器: {tool_name}")
        return tool.executor(arguments, context)
```

#### 使用示例

```python
# 需求 Agent 工具
class RequirementAgentTools:
    def __init__(
        self,
        requirements_service: Any,
        actor_query_fn: Callable,
        actor_write_fn: Callable,
    ) -> None:
        self.registry = ToolRegistry()
        self.requirements_service = requirements_service
        self.actor_query_fn = actor_query_fn
        self.actor_write_fn = actor_write_fn
        self._register_tools()

    def _register_tools(self) -> None:
        self.registry.register(ToolDefinition(
            name="list_requirements",
            description="查询需求列表",
            parameters={
                "type": "object",
                "properties": {
                    "project_id": {"type": "string"},
                    "filters": {"type": "object"},
                },
            },
            executor=self._execute_list_requirements,
        ))
        # ... 注册其他工具

    def get_tools_list(self) -> list[dict[str, Any]]:
        return self.registry.get_tools_list()

    def execute(self, tool_name: str, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return self.registry.execute(tool_name, arguments, context)

    def _execute_list_requirements(self, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        # ... 具体实现
```

---

## 四、通用设施架构

### 4.1 建议的目录结构

```
backend_business/services/agent/
├── runtime/                       # 通用运行时基础设施 [新建]
│   ├── __init__.py
│   ├── graph_recorder.py          # 运行时图记录器
│   │   ├── RuntimeGraphRecorder   # 容器定义可配置
│   │   ├── StageNode              # 节点数据类
│   │   └── ContainerConfig        # 容器配置
│   └── context.py                 # 上下文管理
│       ├── ExecutionContext       # 执行上下文
│       └── ContextEntry           # 上下文条目
│
├── execution/                     # 通用执行引擎 [新建]
│   ├── __init__.py
│   ├── tool_loop_runner.py        # 工具循环运行器
│   │   ├── ToolLoopRunner         # 不含 prompt 构建
│   │   ├── ToolLoopResult        # 循环结果
│   │   └── ToolCallEvent         # 工具调用事件
│   └── prompt_interface.py       # Prompt 构建接口
│       ├── PromptBuilderProtocol  # 抽象协议
│       ├── SystemPromptBuilder    # system_prompt 构建
│       └── UserPromptBuilder     # user_prompt 构建
│
├── actor/                         # Actor 运行时 [新建]
│   ├── __init__.py
│   └── actor_runtime.py           # 通用 Actor 运行时
│       └── AgentActorRuntime
│
├── tools/                         # 工具管理 [重构]
│   ├── __init__.py
│   ├── base.py                    # 工具基类 [新建]
│   │   ├── ToolExecutorProtocol   # 工具执行器协议
│   │   ├── ToolDefinition         # 工具定义
│   │   ├── ToolRegistry          # 工具注册表
│   │   └── ContextMode          # 上下文模式枚举
│   └── requirement_agent_tools.py  # 需求 Agent 工具（保留）
│
├── agents/                        # Agent 实现 [重构]
│   ├── __init__.py
│   ├── base.py                    # Agent 基类 [新建]
│   │   └── BaseAgentChatService   # Agent 基类
│   └── requirement_agent/          # 需求 Agent
│       ├── __init__.py
│       ├── service.py             # 引用通用组件
│       ├── prompt_builder.py      # 业务特定 prompt
│       ├── constants.py           # 常量
│       ├── payload_codec.py       # Payload 编解码
│       └── utils.py               # 工具函数
│
├── execution_graph_service.py     # [保持不变]
├── coordinator/                   # [保持不变]
│   └── distributed_coordinator.py
└── (其他现有模块)
```

### 4.2 组件依赖关系

```
┌─────────────────────────────────────────────────────────────┐
│                     Agent 实现层                              │
│  ┌────────────────┐  ┌──────────────────────────────────┐  │
│  │ BaseAgent      │  │ RequirementAgentChatService       │  │
│  │ (基类)         │  │ - 继承 BaseAgent                │  │
│  │ - 使用通用组件 │  │ - RequirementAgentPromptBuilder │  │
│  └────────────────┘  │ - RequirementAgentTools         │  │
│                       └──────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │ 使用
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    通用运行时设施层                             │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ RuntimeGraph     │  │ ToolLoopRunner   │                │
│  │ Recorder         │  │ - LLM 循环       │                │
│  │ - 图记录         │  │ - 工具调用       │                │
│  │ - 节点管理       │  └──────────────────┘                │
│  └──────────────────┘                                       │
│                                                              │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ AgentActor       │  │ ToolRegistry     │                │
│  │ Runtime          │  │ - 工具注册       │                │
│  │ - Actor 访问     │  │ - 工具执行       │                │
│  └──────────────────┘  └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
                            │ 依赖
                            ▼
┌─────────────────────────────────────────────────────────────┐
│                    基础服务层                               │
│  ┌──────────────────┐  ┌──────────────────┐                │
│  │ ExecutionGraph  │  │ EventStore       │                │
│  │ Service          │  │ ActorManager     │                │
│  └──────────────────┘  └──────────────────┘                │
└─────────────────────────────────────────────────────────────┘
```

---

## 五、抽取优先级与计划

### 5.1 优先级矩阵

| 优先级 | 组件 | 收益 | 工作量 | 风险 |
|--------|------|------|--------|------|
| **P0** | RuntimeGraphRecorder 通用化 | 多 Agent 复用图记录能力 | 中 | 低 |
| **P0** | ToolLoopRunner 通用化 | 统一 LLM 循环逻辑 | 中 | 低 |
| **P1** | AgentActorRuntime 中性化 | 命名准确，便于复用 | 低 | 极低 |
| **P1** | ToolRegistry 抽象 | 规范工具接口 | 中 | 低 |
| **P2** | PromptBuilder 框架 | prompt 差异大，收益不明显 | 中 | 中 |
| **P3** | BaseAgent 基类 | 整合差异大 | 高 | 高 |

### 5.2 实施计划

#### 阶段一：核心设施抽取（2-3天）

1. **创建 `agent/runtime/` 模块**
   - `graph_recorder.py` - 从 `runtime_graph_recorder.py` 抽取
   - `context.py` - 上下文管理

2. **创建 `agent/execution/` 模块**
   - `tool_loop_runner.py` - 从 `tool_loop_runner.py` 抽取
   - `prompt_interface.py` - Prompt 构建接口

3. **创建 `agent/actor/` 模块**
   - `actor_runtime.py` - 从 `actor_runtime.py` 抽取

4. **重构需求 Agent 使用新模块**
   - 验证功能完整性
   - 确保向后兼容

#### 阶段二：工具管理抽象（1-2天）

1. **创建 `agent/tools/base.py`**
   - `ToolExecutorProtocol`
   - `ToolDefinition`
   - `ToolRegistry`

2. **重构 `requirement_agent_tools.py`**
   - 使用 `ToolRegistry`
   - 验证工具执行

#### 阶段三：Agent 基类（可选，2-3天）

1. **创建 `agent/agents/base.py`**
   - `BaseAgentChatService`
   - 定义通用生命周期

2. **重构需求 Agent**
   - 继承 `BaseAgentChatService`
   - 覆盖业务特定方法

#### 阶段四：其他 Agent 开发（并行）

基于通用设施开发：
- 质检 Agent
- 冲突检测 Agent
- 会话总控 Agent

---

## 六、核心原则

### 6.1 设计原则

1. **先抽取底层**：图记录、LLM 循环等基础设施优先
2. **配置化而非硬编码**：容器、节点等定义通过配置传入
3. **协议优于继承**：用 Protocol 定义接口，保持灵活性
4. **向后兼容**：抽取过程中不破坏现有需求 Agent 功能
5. **渐进式重构**：分阶段实施，每阶段独立可验证

### 6.2 接口设计原则

1. **显式依赖**：所有外部依赖通过参数传入
2. **单一职责**：每个类只负责一个核心职责
3. **可测试性**：便于 mock 和单元测试
4. **类型安全**：充分利用 Python 类型注解

---

## 七、后续 Agent 开发示例

### 7.1 质检 Agent 使用通用设施

```python
# backend_business/services/agent/agents/qa_agent/service.py
from agent.runtime.graph_recorder import RuntimeGraphRecorder, ContainerConfig
from agent.execution.tool_loop_runner import ToolLoopRunner, PromptBuilderProtocol
from agent.actor.actor_runtime import AgentActorRuntime

class QAAgentPromptBuilder:
    def build_system_prompt(self, context: dict[str, Any]) -> str:
        return "你是质检 Agent，负责评估需求质量..."

    def build_user_message(self, user_message: str, context: dict[str, Any]) -> str:
        return f"请评估需求 {context.get('requirement_id')} 的质量..."

    def get_tools_list(self) -> list[dict[str, Any]]:
        return QAAgentTools().get_tools_list()

class QAAgentChatService:
    def __init__(self, ...) -> None:
        self.actor_runtime = AgentActorRuntime()
        self.execution_graph_service = ExecutionGraphService(...)
        self.tool_runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy,
            tool_executor=QAAgentTools(...),
            prompt_builder=QAAgentPromptBuilder(),
        )

    def stream_qa_reply(self, ...) -> Generator[dict[str, Any], None, None]:
        # 使用通用 Recorder
        recorder = RuntimeGraphRecorder(
            execution_graph_service=self.execution_graph_service,
            container_configs=[
                ContainerConfig("human_input", "Human Input", "human"),
                ContainerConfig("conductor", "Conductor", "agent"),
                ContainerConfig("qa_agent", "QA Agent", "agent"),
            ],
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
        )

        # 使用通用 ToolLoopRunner
        tool_result = self.tool_runner.run(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            context={...},
        )
        # ...
```

---

## 八、总结

本方案通过分析需求管理 Agent 的实现，识别并规划了通用设施的抽取路径：

1. **第一层基础设施**：图记录、工具循环、Actor 运行时，应优先抽取
2. **第二层半通用组件**：Prompt 构建框架、工具管理接口，分阶段实施
3. **第三层业务特定**：保持不变，各 Agent 自己实现

抽取后的架构将为后续质检 Agent、冲突检测 Agent 等的开发提供坚实的基础设施支持，大幅减少重复代码，提高开发效率。
