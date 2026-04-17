# SessionController 迁移到 GraphExecutor 统一方案

## 1. 文档定位

这份文档是 `SessionController` 从当前实现演进到 `GraphExecutor` 的统一主方案，用来替代原先拆开的 Phase 1 / Phase 2 两份文档。

本文档统一回答四件事：

- 当前正式架构是什么
- 为什么要先做 classic 收敛
- GraphExecutor 迁移在什么前提下开始、怎么推进
- 什么时候可以把 `graph` 从实验链路切成默认链路

这是一份方案文档，不是实现说明。

## 2. 当前状态与边界

当前口径必须统一为：

- `classic` 仍是生产默认链路
- `graph` 只能作为实验链路存在
- 实验链路必须由显式开关控制：`SESSION_CONTROLLER_GRAPH_ENABLED`
- 未开启时，公开 API 不接受 `execution_mode="graph"`

补充边界：

- 仓库里如果已经存在 `execution_mode="graph"`、`GraphExecutor`、拓扑图建模代码，只能视为后续阶段预研或实验实现
- 实验链路可存在，但不代表迁移完成
- 迁移完成的判断标准不是“graph 能跑”，而是“graph 可以替代 classic 成为默认主路径”

## 3. 背景与问题

当前 `SessionController` 在业务上是用户唯一看到的总控 Agent，但在实现上同时承担了三层职责：

1. 高层对话决策
   - 理解用户意图
   - 判断是直接回答、澄清、浏览，还是委托子 Agent
   - 汇总最终答复

2. 会话运行时控制
   - 建图
   - 维护 `active_graph_id`
   - 发 SSE 事件
   - 挂起 / 恢复

3. 工具层流程控制
   - 通过工具副作用控制主循环结束
   - 通过 context 注入改写父流程行为
   - 在工具返回后隐式决定是否停止、是否总结

问题核心不是功能不能用，而是职责边界混杂：

- `SessionControllerService` 既像 service，又像 orchestration engine
- `SessionControllerTools` 既做能力适配，又偷偷控制父流程
- 高层决策没有统一的结构化协议，只能靠零散 context 字段和副作用推断
- 这会同时阻碍 classic 稳定性和后续 GraphExecutor 迁移

因此，迁移不能直接从“老结构”跳到“graph 默认”，而要分阶段推进。

## 4. 总体迁移原则

### 4.1 原则一：先收敛职责，再切执行框架

如果不先把职责边界理清，直接迁到 `GraphExecutor` 只会把现有隐式耦合搬进图里，复杂度不会下降。

### 4.2 原则二：总控决策必须显式化

无论在 `classic` 还是 `graph`，`SessionController` 的高层决策都必须通过统一结构化结果表达，不能依赖工具副作用和零散上下文字段。

### 4.3 原则三：tools 只做能力，不做父流程控制

tools 可以调用浏览能力和子 Agent，但不能决定父循环何时结束、如何收尾、向用户回复什么。

### 4.4 原则四：service 只负责状态机

service 负责 session 校验、graph 生命周期、SSE、挂起恢复、消息持久化；不负责猜测业务语义。

### 4.5 原则五：双轨期间必须有明确默认与回滚口径

在 `classic` 和 `graph` 并存阶段，必须始终明确：

- 哪条是生产默认链路
- 哪条是实验入口
- 关闭实验链路后系统是否能完全回退到 classic

## 5. 总体阶段划分

整个迁移统一拆成三个阶段：

### 5.1 Phase 1：classic 架构收敛

目标不是引入拓扑图，而是把当前 `SessionController` 收敛成一套清晰、可维护、可测试的非拓扑方案。

本阶段明确不做：

- 不把 `SessionController` 主流程迁到 `GraphExecutor / SubgraphRunner`
- 不引入 `controller_intake_llm / handoff / invoke` 的图节点建模
- 不把 runtime 原生 `invoke/handoff` 作为正式依赖

本阶段完成后，`classic` 仍是生产默认。

### 5.2 Phase 2：GraphExecutor 迁移落地

在 Phase 1 收敛完成后，再让 `GraphExecutor` 接管 `SessionController` 主流程，并把 `clarify / suspend / final_reply` 变成图中的显式阶段。

本阶段的 `graph` 仍默认视为实验链路，直到满足切默认条件。

### 5.3 Phase 3：graph 切默认

当 `graph` 方案经过联调、回归、灰度和回滚验证后，才允许把默认执行路径从 `classic` 切到 `graph`。

## 6. Phase 1：classic 收敛方案

### 6.1 目标

保持不变的东西：

- `SessionController` 仍然是用户唯一入口
- `SessionController` 仍然保留高层决策权
- 子 Agent 仍然通过它调度
- 现有 session graph、SSE、挂起恢复能力继续保留
- 现有 `ToolLoopRunner` 继续作为基础能力使用

本阶段要改变的东西：

- 不再让工具层承担父流程控制
- 让高层决策输出变成显式结构化协议
- 让 `SessionControllerService` 只负责 service 该做的事
- 让 `SessionControllerToolLoopRunner` 只负责意图识别、调度和结构化结果产出
- 把“最终回复”和“是否挂起”的判断从隐式副作用改成显式字段

### 6.2 目标结构

```text
用户输入
  ↓
SessionControllerService
  ├── session 校验
  ├── runtime graph 绑定
  ├── stage 事件编排
  ├── suspend / succeed / fail
  └── assistant message 持久化
        ↓
SessionControllerToolLoopRunner
  ├── 意图识别
  ├── 调度工具 / 子 Agent
  └── 返回结构化决策结果
        ↓
SessionControllerTools
  ├── 浏览类能力
  ├── requirement agent 调用
  ├── conflict agent 调用
  └── classification agent 调用
```

这一步最关键的变化不是换框架，而是把总控 Agent 的输出从隐式副作用收敛成显式协议。

### 6.3 统一结果协议

建议引入统一结果结构，例如：

```json
{
  "mode": "direct_reply | clarify | browse | delegate_requirement | delegate_conflict | delegate_classification | approval_pending | error",
  "tool_loop_reply": "工具层或子 Agent 的原始结论摘要",
  "assistant_reply_seed": "可选，供最终回复阶段使用的草稿",
  "clarification_question": "可选，需要向用户追问的最小必要问题",
  "delegated_agent": "requirement_agent | conflict_detection | requirement_classification_agent | null",
  "resolved_requirement_id": "REQ-123",
  "dispatched_agents": ["requirement_agent"],
  "approval_pending": false,
  "should_suspend": false,
  "suspend_reason": null,
  "context": {}
}
```

`mode` 建议统一为：

- `direct_reply`
- `clarify`
- `browse`
- `delegate_requirement`
- `delegate_conflict`
- `delegate_classification`
- `approval_pending`
- `error`

挂起字段统一为：

- `should_suspend = true | false`
- `suspend_reason = clarification | approval_pending | external_wait | null`

这样 service 不再自行猜测业务语义，而是消费统一协议。

### 6.4 各层职责

`SessionControllerService`：

- 保留 session 校验、消息持久化、`active_graph_id` 维护、runtime graph 生命周期、SSE 转发
- 根据结构化结果决定 `succeed_graph / suspend_graph / fail_graph`
- 不再依赖工具副作用或零散 context 字段收尾

`SessionControllerToolLoopRunner`：

- 驱动总控 Agent 的 LLM + tool loop
- 维护 prompt 与总控上下文
- 返回显式结构化结果
- 必须显式包含 `mode / should_suspend / delegated_agent / suspend_reason`

`SessionControllerTools`：

- 只负责浏览能力与子 Agent 调用
- 标准化工具结果
- 回填最小必要上下文，例如 `resolved_requirement_id`
- 不再负责终止父循环、指定父层回复、指定父层总结策略

### 6.5 最终回复与挂起策略

最终回复分两层：

- `tool_loop_reply`：结构化、中间态、面向系统与日志
- `assistant_reply`：面向用户的自然语言输出，由 service 在显式“最终回复阶段”统一生成

挂起策略统一为：

- `mode == clarify` 时，`clarification_question` 非空，`should_suspend == true`，`suspend_reason == clarification`
- `mode == approval_pending` 时，`approval_pending == true`，`should_suspend == true`，`suspend_reason == approval_pending`

service 的职责是按统一口径先发送 assistant message，再切 graph 状态，而不是自行拼接业务判断。

### 6.6 Phase 1 文件改造清单

必须修改：

- `backend_business/services/agent/agents/session_controller/service.py`
- `backend_business/services/agent/agents/session_controller/tool_loop_runner.py`
- `backend_business/services/agent/agents/session_controller/tools.py`
- `backend_business/services/agent/agents/session_controller/prompt_builder.py`

建议新增：

- `backend_business/services/agent/agents/session_controller/contracts.py`

建议同步测试：

- `tests/agent_chat/test_session_controller_service.py`
- `tests/agent_chat/test_session_controller_tools.py`
- `tests/agent_chat/test_session_controller_result_contract.py`

### 6.7 Phase 1 验收标准

本阶段完成后应满足：

1. `SessionController` 仍然是用户唯一入口。
2. tools 不再控制父流程的停止与收尾。
3. `SessionControllerToolLoopRunner` 返回显式结构化结果。
4. service 只根据结构化结果处理成功、挂起、失败。
5. 澄清与审批挂起有统一字段表达。
6. 现有 SSE 与会话链能力继续可用。

## 7. Phase 2：迁移到 GraphExecutor

### 7.1 启动前提

Phase 2 只能在 Phase 1 完成后开始。判断标准不是“代码里已经有 graph 入口”，而是：

- classic 职责边界已经收敛
- 结构化结果协议已经稳定
- 现有挂起 / 恢复 / SSE / 消息持久化口径已统一

### 7.2 迁移目标

Phase 2 的目标是：

- 让 `GraphExecutor` 接管 `SessionController` 主流程
- 将 `clarify / suspend / final_reply` 变成图中的显式阶段
- 将子 Agent 委托从兼容工具调用升级为 runtime 原生调度
- 继续保留 classic 作为可回滚链路，直到 graph 满足切默认条件

### 7.3 Graph 方案边界

Phase 2 中允许引入：

- `session_controller_agent.json`
- `controller_intake_llm / handoff / invoke / final_reply` 等图节点
- runtime 原生 `invoke/handoff`
- 由图显式表达的挂起与恢复阶段

但必须满足：

- `graph` 仍由显式开关控制
- 未开启开关时，外部请求不能进入 graph 默认路径
- graph 实现不能破坏 classic 现有回滚能力

### 7.4 迁移方式

推荐按“先图内对齐语义，再替换入口”的方式推进：

1. 先用与 Phase 1 相同的结构化协议定义图节点边界。
2. 再把 `clarify / approval_pending / final_reply` 从 service 收尾迁到图中的显式阶段。
3. 再把子 Agent 委托从工具兼容层迁到 runtime 原生 `invoke`。
4. 最后才评估是否把公开入口默认切到 graph。

这样做的目的，是避免在“执行框架切换”和“业务语义重写”两个维度同时失控。

## 8. Phase 3：切默认与回滚

### 8.1 切默认前提

只有在以下条件全部满足后，才允许把 `graph` 设为默认主链路：

- 前后端明确切换到 `graph` 入口
- 推理服务、工具调用提供方、Postgres、挂起恢复链路全部完成联调
- SSE、会话持久化、审批挂起、澄清挂起全链路验证通过
- 回滚开关明确可用，关闭后可完整退回 classic
- 验收口径从“实验可运行”升级为“默认主路径稳定”

### 8.2 双轨并存要求

在切默认前，必须始终明确区分：

- 生产默认链路
- 实验入口
- 回滚方式

任何时候都不能出现“graph 已经部分接管，但默认和回滚口径不清楚”的状态。

## 9. 风险与注意事项

### 9.1 风险一：只改字段名，不改职责边界

如果只是把旧的隐式 context 副作用包装成几个新字段，但 tools 仍然控制父流程，那 Phase 1 就没有真正完成。

### 9.2 风险二：service 继续承载业务猜测

如果 service 仍然自己判断“这是澄清还是审批还是直接回复”，而不是消费显式 `mode`，则 classic 收敛仍然失败。

### 9.3 风险三：跳过 Phase 1 直接图化

如果直接把当前隐式逻辑搬进 GraphExecutor，图只会成为新的耦合承载体，不会自动带来清晰边界。

### 9.4 风险四：graph 入口先于回滚口径落地

如果 graph 能进但没有明确开关、默认口径和回滚方案，就会把实验链路误当成正式架构。

## 10. 统一结论

`SessionController -> GraphExecutor` 的正确路径不是“一步到位切 graph 默认”，而是：

1. 先完成 classic 收敛，清理职责边界。
2. 再把稳定的语义迁入 GraphExecutor。
3. 最后在双轨可回滚的前提下切换默认链路。

统一后的架构判断标准也应固定为：

- 当前正式架构：`classic`
- 当前迁移方向：`GraphExecutor`
- 当前实施顺序：先收敛、再迁移、后切默认
