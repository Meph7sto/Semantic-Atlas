# SessionController 迁移到 GraphExecutor 统一方案

## 1. 文档定位

这份文档记录 `SessionController` 从 classic 演进到 `GraphExecutor` 的迁移口径。当前代码已经进入迁移后的 graph-only 状态，本文保留历史阶段说明，但以本节“当前状态与边界”为准。

本文档统一回答四件事：

- 当前正式架构是什么
- classic 历史链路如何收敛和退出
- GraphExecutor 迁移的职责边界
- 后续如何继续拆分 service 与清理 legacy 代码

这是一份方案文档，不是实现说明。

## 2. 当前状态与边界

当前口径必须统一为：

- `SessionController` 公开入口只支持 `execution_mode="graph"`
- `graph` 是当前生产主路径，不再由 `SESSION_CONTROLLER_GRAPH_ENABLED` 控制
- 公开 API 不接受 `execution_mode="classic"` 或其他值
- SessionController 工具委托通过 graph/native invoke 表达，不再回落到 classic inline tool-loop

补充边界：

- 子 Agent 的 alpha 单独测试页面仍可存在，但只作为测试/诊断入口
- 单 Agent 测试入口也必须进入 graph/runtime，不保留 standalone classic 执行链路
- experience target 使用 `*_tool_loop`，不再保留 `*_classic` 目标

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

当前迁移已经完成默认链路切换，后续工作重点从“切换默认”转为“删除遗留 fallback、拆薄 service、同步文档测试”。

## 4. 总体迁移原则

### 4.1 原则一：先收敛职责，再切执行框架

如果不先把职责边界理清，直接迁到 `GraphExecutor` 只会把现有隐式耦合搬进图里，复杂度不会下降。

### 4.2 原则二：总控决策必须显式化

无论在 `classic` 还是 `graph`，`SessionController` 的高层决策都必须通过统一结构化结果表达，不能依赖工具副作用和零散上下文字段。

### 4.3 原则三：tools 只做能力，不做父流程控制

tools 可以调用浏览能力和子 Agent，但不能决定父循环何时结束、如何收尾、向用户回复什么。

### 4.4 原则四：service 只负责状态机

service 负责 session 校验、graph 生命周期、SSE、挂起恢复、消息持久化；不负责猜测业务语义。

### 4.5 原则五：graph-only 期间必须明确 legacy 边界

在 `graph` 成为默认后，必须始终明确：

- SessionController 主路径只允许 graph
- 子 Agent standalone classic 是否仍有独立入口或测试依赖
- 删除 legacy 能力前是否已清理对应 experience target、测试和文档

## 5. 总体阶段划分

历史迁移可拆成三个阶段；当前代码状态已经越过 Phase 3，进入 Phase 4 清理阶段：

### 5.1 Phase 1：classic 架构收敛

目标不是引入拓扑图，而是把当前 `SessionController` 收敛成一套清晰、可维护、可测试的非拓扑方案。

本阶段明确不做：

- 不把 `SessionController` 主流程迁到 `GraphExecutor / SubgraphRunner`
- 不引入 `controller_intake_llm / handoff / invoke` 的图节点建模
- 不把 runtime 原生 `invoke/handoff` 作为正式依赖

本阶段完成后，历史口径中 `classic` 仍是生产默认；当前代码已不处于该阶段。

### 5.2 Phase 2：GraphExecutor 迁移落地

在 Phase 1 收敛完成后，再让 `GraphExecutor` 接管 `SessionController` 主流程，并把 `clarify / suspend / final_reply` 变成图中的显式阶段。

本阶段的历史口径中 `graph` 仍默认视为实验链路；当前代码已不处于该阶段。

### 5.3 Phase 3：graph 切默认

当 `graph` 方案经过联调、回归、灰度和回滚验证后，才允许把默认执行路径从 `classic` 切到 `graph`。

### 5.4 Phase 4：graph-only 收敛

当前代码处于本阶段：

- `SessionController` API 和 service 只接受 `graph`
- `SubgraphRunner` 通过 `PromptBuilderFactory` 接入业务 prompt builder，不直接 import SessionController
- `SessionControllerTools` 不再执行 classic inline tool-loop
- 后续继续拆分 `SessionControllerService`，并评估子 Agent standalone classic 能力是否还有保留价值

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
- 不再通过 SessionController 保留 classic 回滚链路；回滚策略应基于 graph 修复或版本回滚

### 7.3 Graph 方案边界

Phase 2 中允许引入：

- `session_controller_agent.json`
- `controller_intake_llm / handoff / invoke / final_reply` 等图节点
- runtime 原生 `invoke/handoff`
- 由图显式表达的挂起与恢复阶段

但必须满足：

- graph 配置必须显式表达 runtime 行为，不能靠 prompt_builder 名称推断
- 通用执行层不能 import 业务 Agent 的 prompt builder
- graph 实现不能重新引入 SessionController classic fallback

### 7.4 迁移方式

推荐按“先图内对齐语义，再替换入口”的方式推进：

1. 先用与 Phase 1 相同的结构化协议定义图节点边界。
2. 再把 `clarify / approval_pending / final_reply` 从 service 收尾迁到图中的显式阶段。
3. 再把子 Agent 委托从工具兼容层迁到 runtime 原生 `invoke`。
4. 最后才评估是否把公开入口默认切到 graph。

这样做的目的，是避免在“执行框架切换”和“业务语义重写”两个维度同时失控。

## 8. Phase 3：切默认与回滚

### 8.1 切默认前提

历史上只有在以下条件全部满足后，才允许把 `graph` 设为默认主链路：

- 前后端明确切换到 `graph` 入口
- 推理服务、工具调用提供方、Postgres、挂起恢复链路全部完成联调
- SSE、会话持久化、审批挂起、澄清挂起全链路验证通过
- 回滚方案明确可用
- 验收口径从“实验可运行”升级为“默认主路径稳定”

### 8.2 双轨并存要求

切默认完成后，必须始终明确区分：

- graph 主路径
- legacy 子 Agent classic 能力
- 删除 legacy 前的兼容范围

任何时候都不能出现“graph 已经部分接管，但默认和回滚口径不清楚”的状态。

## 9. 风险与注意事项

### 9.1 风险一：只改字段名，不改职责边界

如果只是把旧的隐式 context 副作用包装成几个新字段，但 tools 仍然控制父流程，那 Phase 1 就没有真正完成。

### 9.2 风险二：service 继续承载业务猜测

如果 service 仍然自己判断“这是澄清还是审批还是直接回复”，而不是消费显式 `mode`，则 classic 收敛仍然失败。

### 9.3 风险三：跳过 Phase 1 直接图化

如果直接把当前隐式逻辑搬进 GraphExecutor，图只会成为新的耦合承载体，不会自动带来清晰边界。

### 9.4 风险四：文档和代码默认链路不一致

如果文档继续描述 classic 默认，而代码已经 graph-only，会误导维护者保留或删除错误路径。

## 10. 统一结论

`SessionController -> GraphExecutor` 的历史迁移路径不是“一步到位切 graph 默认”，而是：

1. 先完成 classic 收敛，清理职责边界。
2. 再把稳定的语义迁入 GraphExecutor。
3. 最后在双轨可回滚的前提下切换默认链路。

当前架构判断标准应固定为：

- 当前正式架构：`GraphExecutor / graph-only`
- 当前清理方向：删除 SessionController classic fallback，拆薄 service
- 当前 legacy 边界：子 Agent standalone classic tool-loop 和 `*_classic` experience target 单独评估
