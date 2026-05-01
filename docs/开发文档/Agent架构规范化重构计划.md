# Agent 架构规范化重构计划

## 1. 文档定位

本文档用于统一 `backend_business/services/agent` 下 Agent 相关代码的后续规范化方向。

当前项目已经具备较完整的 Agent 运行时基础：

- `ToolLoopRunner` 负责单个 LLM 节点内的 tool-call 循环
- `GraphExecutor` 负责执行图入口、意图门控、拓扑展开、挂起与恢复
- `SubgraphRunner` 负责按 subgraph 推进运行时执行图
- `ExecutionGraphService` 负责执行图、节点、边、容器、运行状态的持久化
- `Scratchpad` / `ExecutionContext` 负责跨阶段工作记忆与局部上下文
- 各业务 Agent 通过 `prompt_builder`、`tools`、`service`、`tool_loop_runner` 接入上述运行时

后续目标不是推翻现有实现，而是将已有能力收口成清晰、可扩展、可测试的 Agent 架构规范。

## 2. 当前问题

### 2.1 核心运行时已经统一，外围适配仍然重复

`requirement_agent`、`conflict_detection_agent`、`requirement_classification_agent` 都使用了通用 `ToolLoopRunner`，但每个 Agent 仍各自维护相似的：

- session 创建、更新、删除、列表查询
- active graph 恢复与链式 graph 查询
- runtime graph 初始化与 meta patch
- tool-loop adapter
- final reply / result event 收尾逻辑
- experience skill 注入和回写逻辑

这导致新增 Agent 时需要复制较多样板代码，且不同 Agent 的细节容易漂移。

### 2.2 GraphExecutor 与 ToolLoopRunner 的边界需要明确

`GraphExecutor` 当前已经通过 `ToolLoopRunner` 实现了：

- intent judge 阶段
- normal conversation fallback
- subgraph 内 LLM 阶段的间接执行

因此工程口径应统一为：

```text
GraphExecutor owns the flow.
ToolLoopRunner owns the loop.
```

也就是说，`GraphExecutor` 可以作为对外统一入口，包含直接对话、执行图、拓扑展开和恢复能力；但不应吞并 `ToolLoopRunner` 的内部实现逻辑。

### 2.3 Agent 定义缺少统一契约

目前每个 Agent 的核心差异本质上是：

- `agent_type`
- `container_key`
- `label`
- `prompt_builder`
- `tool_executor`
- `max_tool_call_rounds`
- runtime binding 策略
- memory / quota / capability policy
- final result postprocess 规则

这些差异散落在多个 service 和 runner 文件中，尚未形成统一的 `AgentDefinition` 或注册机制。

### 2.4 SessionController 与子 Agent 测试入口均已收口到 graph/runtime

`SessionController` 主路径已经迁移到 `GraphExecutor`。alpha 测试界面仍保留单 Agent 测试入口，但这些入口只作为测试/诊断 API，不再代表独立 classic 执行链路：

- graph 是主路径
- 单 Agent 测试入口也必须进入 graph/runtime
- 新增能力默认接入 graph/runtime 体系
- experience target 使用 `*_tool_loop` 命名，不再保留 `*_classic` 目标

## 3. 目标架构

### 3.1 分层目标

规范化后，Agent 相关代码应分为五层：

```text
API Router
  ↓
Agent Application Service
  ↓
Agent Runtime Entry
  ├── GraphExecutor
  │     ├── intent gate
  │     ├── topology expand
  │     ├── SubgraphRunner
  │     └── normal conversation via ToolLoopRunner
  └── alpha single-agent test entry via GraphExecutor
        ↓
Agent Definition / Adapter
  ├── prompt builder
  ├── tool executor
  ├── context builder
  ├── result postprocessor
  └── runtime binding policy
        ↓
Domain Services / DB / Inference Proxy
```

### 3.2 GraphExecutor 与 ToolLoopRunner 的职责边界

`GraphExecutor` 负责：

- 判断是否需要展开拓扑
- 创建或恢复 runtime graph
- 实例化拓扑模板
- 调用 `SubgraphRunner`
- 处理 suspended / succeeded / failed 状态
- 对外返回统一 `ExecutionResult`
- 作为新式 Agent 的推荐入口

`ToolLoopRunner` 负责：

- 构建 LLM messages
- 调用 `chat_completion_with_tools`
- 并发执行同轮 tool calls
- 按稳定顺序合并 tool result
- 注入 `scratchpad_write`
- 注入 `complete_phase`
- 记录 stage / tool_result event
- 返回 `ToolLoopResult`

禁止方向：

- 不把 tool-call 循环实现复制进 `GraphExecutor`
- 不让业务 tools 控制父流程状态
- 不让 service 层直接拼接复杂运行时协议

推荐方向：

- `GraphExecutor` 对外提供统一执行能力
- `ToolLoopRunner` 保持独立、可复用、可单测
- `SubgraphRunner` 只依赖 prompt factory、tool executor 和 runtime binding，不依赖具体业务 service

## 4. 核心抽象设计

### 4.1 AgentDefinition

新增统一 Agent 定义，用于描述一个 Agent 的静态能力和运行策略。

建议位置：

```text
backend_business/services/agent/runtime/agent_definition.py
```

建议结构：

```python
from dataclasses import dataclass
from typing import Any, Callable

@dataclass(frozen=True)
class AgentDefinition:
    agent_type: str
    container_key: str
    label: str
    role_type: str = "agent"
    max_tool_call_rounds: int = 6
    prompt_builder_factory: Callable[[], Any] | None = None
    tool_executor_factory: Callable[[], Any] | None = None
    context_builder: Any | None = None
    result_postprocessor: Any | None = None
    runtime_profile: str = "default"
    capability_policy: dict[str, Any] | None = None
    quota_policy: dict[str, Any] | None = None
    memory_policy: dict[str, Any] | None = None
```

第一阶段不要求所有字段一次性启用，可以先覆盖 `agent_type`、`container_key`、`prompt_builder`、`tools`、`max_rounds`。

### 4.2 AgentRegistry

新增统一注册表，替代在 `SessionControllerService`、`SessionControllerTools` 中散落的子 Agent 配置。

建议位置：

```text
backend_business/services/agent/runtime/agent_registry.py
```

职责：

- 注册内置 Agent
- 按 `agent_type` 或 `container_key` 查询定义
- 生成 runtime binding specs
- 为 `SessionController` 提供可委托 Agent 列表
- 为拓扑模板生成 selectable containers

### 4.3 AgentSessionGraphStore

将当前多个业务 Agent 中重复的 session / graph 逻辑抽出。

建议位置：

```text
backend_business/services/agent/runtime/session_graph_store.py
```

职责：

- `create_or_get_session`
- `create_session`
- `update_session`
- `list_sessions`
- `delete_session`
- `hydrate_session_graph`
- `resolve_session_graph_target`
- `list_session_graph_chain`
- `get_graph_detail`
- `get_graph`

`SessionControllerSessionGraphStore` 可以作为参考实现，后续改造为通用版本。

### 4.4 BaseAgentToolLoopRunner

将各业务 Agent 的 `xxxToolLoopRunner` 收敛为通用模板方法。

建议位置：

```text
backend_business/services/agent/execution/base_agent_tool_loop_runner.py
```

通用流程：

```text
build_initial_context
  ↓
inject_experience_skill_context
  ↓
create ToolLoopRunner
  ↓
yield from ToolLoopRunner.run
  ↓
postprocess_result
  ↓
writeback_experience
  ↓
return normalized payload
```

各 Agent 只覆盖：

- `build_initial_context`
- `build_prompt_adapter`
- `build_meta_patch`
- `resolve_experience_target`
- `postprocess_result`

### 4.5 AgentExecutionService

抽象出薄 application service，减少每个业务 Agent service 的样板代码。

建议位置：

```text
backend_business/services/agent/runtime/agent_execution_service.py
```

职责：

- 校验 session
- 创建用户消息
- 选择 graph target
- 创建 recorder
- 调用 `GraphExecutor` 或 compatibility runner
- 持久化 assistant message
- 发送 SSE events

业务 Agent service 应逐步变薄，只负责提供 definition、tools、prompt 和少量业务收尾规则。

## 5. 迁移阶段

### Phase 1：文档与契约先行

目标：

- 明确 `GraphExecutor owns the flow, ToolLoopRunner owns the loop`
- 定义 `AgentDefinition` 字段草案
- 定义 `AgentService` 最小接口
- 标记 standalone classic 能力为 compatibility path

交付物：

- 本文档
- 代码中新增 protocol / dataclass，但不强制大规模替换
- 新增架构注释或 README 小节，说明新增 Agent 应优先注册 definition

验收标准：

- 团队对新增 Agent 的接入方式有统一口径
- 不再出现新的复制式 service / tool_loop_runner 文件作为默认方案

### Phase 2：抽出 AgentSessionGraphStore

目标：

- 先处理重复最多、风险最低的 session / graph 管理逻辑
- 让 requirement / conflict / classification 复用同一 store

改造范围：

- `RequirementAgentChatService`
- `ConflictDetectionAgentService`
- `RequirementClassificationAgentService`
- `SessionControllerSessionGraphStore` 泛化

验收标准：

- 三个业务 Agent 的 session CRUD 行为保持不变
- active graph、suspended graph、prev graph 逻辑保持一致
- 相关 API contract 测试通过

建议测试：

```text
tests/agent_chat/test_agent_session_graph_store.py
tests/test_fastapi_agent_chat_prompt_payload_contract.py
tests/test_fastapi_agent_chat_session_contract.py
```

### Phase 3：抽出 BaseAgentToolLoopRunner

目标：

- 消除 `requirement_agent`、`conflict_detection_agent`、`requirement_classification_agent` 的 tool-loop adapter 重复
- 保留每个 Agent 的上下文差异和结果后处理差异

改造范围：

- `backend_business/services/agent/agents/*/tool_loop_runner.py`
- 新增 `base_agent_tool_loop_runner.py`

验收标准：

- 三个 Agent 仍能独立运行 standalone tool-loop
- `ToolLoopRunner` 的工具并发、complete_phase、scratchpad 行为不变
- experience skill 注入和 writeback 行为不丢失

建议测试：

```text
tests/agent_chat/test_subgraph_runner.py
tests/test_agent_chat_prompt_payload.py
tests/test_fastapi_agent_chat_prompt_payload_contract.py
```

### Phase 4：引入 AgentDefinition / AgentRegistry

目标：

- 将 Agent 静态配置从 service 中抽出
- 统一 runtime binding specs 生成
- 让 `SessionController` 委托目标来自 registry，而不是手写分散配置

改造范围：

- 新增 `agent_definition.py`
- 新增 `agent_registry.py`
- 改造 `SessionControllerService._ensure_graph_runtime_bindings`
- 改造 `SessionControllerTools.resolve_runtime_tool_executor`
- 改造 `ensure_session_controller_template` 的 selectable containers 来源

验收标准：

- 新增一个 Agent 时，主要通过注册 `AgentDefinition` 完成
- runtime binding 的 capability / quota / memory policy 生成一致
- SessionController 的候选委托 Agent 列表与 registry 一致

### Phase 5：GraphExecutor 统一入口

目标：

- 新式入口统一走 `GraphExecutor`
- standalone ToolLoopRunner 仅保留兼容或测试入口
- 业务 service 不再直接组织复杂 graph 执行流程

改造方向：

```text
AgentApplicationService.stream_reply
  ↓
GraphExecutor.execute
  ├── no topology -> ToolLoopRunner
  └── topology -> SubgraphRunner -> ToolLoopRunner
```

验收标准：

- `SessionController` 主路径保持 graph-only
- 子 Agent 可以通过 graph/runtime 被调用
- 子 Agent standalone classic 入口若仍保留，文档明确标记为 compatibility
- 执行结果统一为 `ExecutionResult` 或轻量 wrapper

### Phase 6：清理 legacy 与收束文档

目标：

- 删除已无 API / 测试依赖的 classic 入口
- 清理 `*_classic` experience target
- 更新 README 和开发文档
- 补充新增 Agent 的接入指南

验收标准：

- 没有未使用的 classic runner / service fallback
- 没有重复 session graph store 实现
- 没有绕过 registry 的新 Agent 绑定
- 文档中的主路径与代码一致

## 6. 推荐代码目录形态

目标目录形态：

```text
backend_business/services/agent/
├── runtime/
│   ├── agent_definition.py
│   ├── agent_registry.py
│   ├── agent_runtime.py
│   ├── agent_execution_service.py
│   ├── session_graph_store.py
│   ├── context.py
│   ├── scratchpad.py
│   └── scratchpad_service.py
├── execution/
│   ├── graph_executor.py
│   ├── subgraph_runner.py
│   ├── tool_loop_runner.py
│   ├── base_agent_tool_loop_runner.py
│   └── topology_instantiator.py
├── agents/
│   ├── requirement_agent/
│   │   ├── definition.py
│   │   ├── prompt_builder.py
│   │   ├── tools_adapter.py
│   │   └── service.py
│   ├── conflict_detection_agent/
│   ├── requirement_classification_agent/
│   └── session_controller/
├── tools/
├── topology/
└── execution_graph_service/
```

说明：

- `agents/*/definition.py` 只描述该 Agent 的静态能力
- `agents/*/service.py` 保持薄封装，主要供 API router 注入使用
- `tools/` 保留领域工具实现
- `execution/` 只放运行时执行引擎，不依赖具体 Agent service
- `runtime/` 放注册、策略、session graph、运行状态等跨 Agent 能力

## 7. 新增 Agent 接入规范

新增 Agent 默认流程：

1. 新建 `agents/<agent_name>/definition.py`
2. 实现 prompt builder
3. 实现 tool executor 或复用已有 tools
4. 在 `AgentRegistry` 注册 `AgentDefinition`
5. 如需被 SessionController 委托，在 definition 中声明 selectable metadata
6. 如需独立 API，再增加薄 service 和 router
7. 增加最小 contract 测试

禁止流程：

- 复制某个现有 Agent 的完整 `service.py`
- 在 service 中手写 runtime binding specs
- 在 tools 中通过副作用控制父流程状态
- 绕过 `GraphExecutor` 手动拼装复杂执行图

## 8. 测试策略

### 8.1 单元测试

覆盖：

- `AgentDefinition` 校验
- `AgentRegistry` 查询与 binding specs 生成
- `AgentSessionGraphStore` graph target 选择
- `BaseAgentToolLoopRunner` 模板方法
- `ToolLoopRunner` 工具并发合并语义

### 8.2 集成测试

覆盖：

- SessionController graph-only 主路径
- SessionController 委托 requirement / conflict / classification
- GraphExecutor no-topology 直接对话路径
- GraphExecutor topology expand 路径
- suspended graph resume 路径
- 子 Agent standalone compatibility 路径

### 8.3 回归测试

重点保护：

- existing API response schema
- SSE event 名称和基本 payload
- active graph 链式关系
- requirement 修改审批
- classification result 写回
- conflict detection result 输出
- scratchpad 继承和持久化

## 9. 风险与控制

### 风险一：一次性重构过大

控制：

- 按阶段提交
- 每阶段只抽一个边界
- 保留旧入口到测试通过后再删除

### 风险二：GraphExecutor 变成巨型类

控制：

- 不合并 `ToolLoopRunner` 内部逻辑
- `GraphExecutor` 只编排，不执行 tool-call 细节
- 新增 helper 时优先放到独立模块

### 风险三：业务 Agent 行为漂移

控制：

- 先补 contract 测试
- 重构前后比较关键 SSE events 和 final result
- 每个 Agent 单独迁移，不并行大改

### 风险四：experience skill 注入丢失

控制：

- 将 skill injection/writeback 做成 `BaseAgentToolLoopRunner` 的显式步骤
- 每个 Agent 的 target 解析独立覆盖
- 增加 regression test 或至少保留现有 target id

## 10. 优先级建议

推荐执行顺序：

1. 抽 `AgentSessionGraphStore`
2. 抽 `BaseAgentToolLoopRunner`
3. 引入 `AgentDefinition`
4. 引入 `AgentRegistry`
5. 改造 `SessionController` 委托配置
6. 将子 Agent 新式入口收口到 `GraphExecutor`
7. 清理 standalone classic legacy

不建议第一步就做：

- 删除所有 classic 入口
- 大规模改 `GraphExecutor`
- 一次性迁移所有 Agent 到 registry
- 改动数据库 schema

## 11. 阶段完成后的理想状态

最终应达到：

- 新增 Agent 不需要复制 service / runner 样板代码
- Agent 能力通过 `AgentDefinition` 注册
- runtime binding 从 registry 生成
- SessionController 的委托目标来自 registry
- GraphExecutor 是新式执行统一入口
- ToolLoopRunner 是稳定的底层 LLM tool-call loop
- SubgraphRunner 保持 agent-agnostic
- classic standalone 能力要么删除，要么明确标为 compatibility
- 开发文档、代码结构、测试口径一致

一句话总结：

```text
用 GraphExecutor 统一执行入口，用 ToolLoopRunner 保持循环核心，用 AgentDefinition/Registry 统一 Agent 描述，用 Store/BaseRunner 清掉重复适配层。
```

## 12. 当前落地状态

截至本轮重构，后端 Agent 架构已完成以下收束：

- 已新增 `AgentDefinition` / `AgentRegistry`，SessionController 的可委托 Agent、runtime binding specs、内置模板 selectable containers 均从 registry 获取。
- 已新增通用 `AgentSessionGraphStore`，requirement / conflict / classification / session controller 的 session CRUD、active graph 恢复、graph chain 查询和删除逻辑已收口复用。
- 已新增 `BaseAgentToolLoopRunner`，三个业务 Agent 的 standalone tool-loop adapter 已迁移为模板方法实现，只保留各自上下文构建、meta patch 和结果后处理差异。
- `SessionController` 主入口保持 graph-only，非 graph execution_mode 会被拒绝；SessionController 委托路径通过 GraphExecutor / SubgraphRunner / ToolLoopRunner 分层推进。
- 需求管理、冲突检测、需求分类独立 API 是 alpha 单 Agent 测试入口，已收口到 GraphExecutor graph 模式；独立 stream payload 只接受 `execution_mode="graph"`。
- `ToolLoopRunner` 仍只负责 LLM tool-call loop；`GraphExecutor` 只负责编排 intent gate、拓扑展开、恢复和结果归一。
- experience skill 注入已保留，并在 graph subgraph 场景中按当前阶段任务过滤适用场景，避免跨阶段经验污染当前阶段提示词。

仍保留的测试/内部入口：

- `RequirementAgentChatService.stream_requirement_agent_reply`
- `RequirementClassificationAgentService.stream_requirement_classification_agent_reply`
- 三个业务 Agent 的 `run_inline_tool_loop` / `stream_inline_tool_loop`

这些入口服务于 alpha 单 Agent 测试界面和 graph/runtime 内部委托，不再代表旧式兼容路径；需求管理和需求分类的 stream 方法会转入 `GraphExecutor.execute_agent_tool_loop`。新增能力默认不得复制这些 service 流程，应优先注册 `AgentDefinition` 并接入 graph/runtime 路径。

本轮验证：

```text
python -m pytest tests/agent_chat tests/test_agent_chat_prompt_payload.py tests/test_fastapi_agent_chat_prompt_payload_contract.py tests/test_no_legacy_patterns.py
```

结果：424 passed, 3 warnings。
