# Phase 1: SessionController 非拓扑收敛方案（classic 为生产默认）

## 1. 文档定位

这是一份 **Phase 1** 方案文档，不是实现说明。

当前边界非常明确：

- 先**不引入拓扑图**
- 先**不把 SessionController 迁到 GraphExecutor / SubgraphRunner**
- 先**不做 runtime 原生 `invoke/handoff`**
- 先**不进入实现阶段**

本阶段只做一件事：

**把现有 SessionController 架构收敛成一套清晰、可维护、可测试的非拓扑图方案。**

拓扑图化迁移放到后续阶段单独设计。

补充边界：

- 仓库里如果存在 `execution_mode="graph"` 相关代码或开关，只视为 **Phase 2 实验链路**
- **当前正式架构** 仍以 `classic` 为生产默认与验收口径
- 实验链路不代表迁移已完成，更不代表可以替代本阶段收敛要求

## 2. 背景与当前问题

当前 `SessionController` 在业务定位上是用户唯一看到的高层总控 Agent，但在代码实现上，它同时承担了三种不同层次的职责：

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
   - 通过 context 注入强行改写父流程行为
   - 在工具返回后隐式决定是否停止、是否总结

问题不在于功能不能用，而在于职责边界混杂，导致：

- `SessionControllerService` 既是入口 service，又像 orchestration engine
- `SessionControllerTools` 既是工具适配层，又偷偷承担部分流程控制
- 高层决策没有清晰的结构化输出协议，只能从若干 context 字段和副作用中推断
- 后续无论是否迁移到拓扑图，当前代码都不够干净

## 3. 本阶段目标

### 3.1 保持不变的东西

- `SessionController` 仍然是用户唯一入口
- `SessionController` 仍然保留高层决策权
- 子 Agent 仍然通过它调度
- 现有 session graph、SSE、挂起恢复能力继续保留
- 现有 `ToolLoopRunner` 继续作为基础能力使用

### 3.2 本阶段要改变的东西

- 不再让工具层承担父流程控制
- 让高层决策输出变成**显式结构化协议**
- 让 `SessionControllerService` 只负责 service 该做的事
- 让 `SessionControllerToolLoopRunner` 只负责“意图识别 + 调度 + 结构化结果产出”
- 把“最终回复”和“是否挂起”的判断口径从隐式副作用改成显式字段

## 4. 核心原则

### 4.1 原则一：当前阶段不碰拓扑图

当前阶段不讨论：

- `session_controller_agent.json`
- `controller_intake_llm / handoff / invoke` 子图建模
- GraphExecutor 接管 SessionController 主流程

这些内容全部下放到后续阶段。

### 4.2 原则二：决策归总控 tool loop，不归 tools 副作用

在当前非拓扑图方案下，高层决策仍由 `SessionController` 的 LLM tool loop 完成，但必须满足：

- 决策由 `SessionControllerToolLoopRunner` 的结构化结果显式表达
- 决策**不能**继续通过 `SessionControllerTools` 的副作用偷偷完成

也就是说：

- 决策属于总控 Agent
- 执行属于 tools / 子 Agent
- 状态流转属于 service

### 4.3 原则三：tools 只做能力，不做父流程控制

`SessionControllerTools` 可以保留这些能力：

- `list_requirements`
- `search_requirements`
- `invoke_requirement_agent`
- `invoke_conflict_detection`
- `invoke_requirement_classification_agent`

但必须去掉以下职责：

- `_mark_tool_loop_should_stop(...)`
- `_stop_after_tool_round`
- `_forced_tool_loop_reply`
- 通过 context 副作用提前终止父流程
- 隐式决定“父流程接下来该如何收尾”

### 4.4 原则四：service 只负责状态机，不负责业务猜测

`SessionControllerService` 在本阶段仍保留流程骨架，但它的判断依据必须来自显式结构化结果，而不是零散 context 字段和工具副作用。

## 5. 目标结构

本阶段收敛后的结构如下：

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

这套结构里最重要的变化不是“换框架”，而是：

**要把总控 agent 的输出，从一堆隐式 context 副作用，收敛成一份显式的结构化结果。**

## 6. 结构化结果协议

这是当前阶段最关键的设计点。

建议新增统一结果结构，例如：

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

### 6.1 `mode` 的建议枚举

- `direct_reply`
  - 本轮不需要委托，SessionController 可直接回复

- `clarify`
  - 信息不足，必须先向用户提最小必要问题

- `browse`
  - 本轮主要是浏览型查询，可在总控层直接总结

- `delegate_requirement`
  - 需要委托需求管理 Agent

- `delegate_conflict`
  - 需要委托冲突检测 Agent

- `delegate_classification`
  - 需要委托需求分类 Agent

- `approval_pending`
  - 子 Agent 已发起审批，当前轮需要告知用户并挂起

- `error`
  - 当前轮无法完成，需要统一错误处理

### 6.2 `should_suspend` 与 `suspend_reason`

当前阶段不引入 `handoff` 拓扑节点，因此挂起仍在 service 层执行，但必须通过显式字段驱动：

- `should_suspend = true`
- `suspend_reason = clarification | approval_pending | external_wait`

这样 service 不再自己猜测是否挂起，而是消费统一结果协议。

## 7. 各层职责调整

### 7.1 `SessionControllerService`

保留职责：

- session 访问校验
- user/assistant message 持久化
- `active_graph_id` 维护
- runtime graph 生命周期控制
- SSE 事件转发
- 根据结构化结果决定 `succeed_graph` / `suspend_graph` / `fail_graph`

应收缩的职责：

- 不再自己从若干零散 context 字段推导完整业务含义
- 不再依赖工具层副作用决定流程何时结束
- 不再把“工具返回了什么”和“父流程该怎么收尾”混在一起

### 7.2 `SessionControllerToolLoopRunner`

保留职责：

- 驱动总控 Agent 的 LLM + tool loop
- 组织 prompt
- 维护总控上下文
- 返回结构化结果协议

新增要求：

- 返回值必须显式包含 `mode`
- 显式包含 `should_suspend`
- 显式包含 `delegated_agent`
- 显式包含最终给 service 使用的收尾信息

### 7.3 `SessionControllerTools`

保留职责：

- 实际调用浏览类接口
- 实际调用各子 Agent
- 标准化工具结果
- 回填最小必要上下文，例如 `resolved_requirement_id`

必须移除的职责：

- 终止父循环
- 强行指定父层回复文本
- 强行指定父层总结策略
- 通过隐藏字段替代正式协议

## 8. 最终回复策略

当前阶段先不把最终回复迁入拓扑图，但要把回复策略收敛清楚。

建议分两层：

1. `tool_loop_reply`
   - 结构化、偏中间态
   - 面向系统与日志

2. `assistant_reply`
   - 面向用户的自然语言输出
   - 由 service 在一个明确的“最终回复阶段”统一生成

关键不是是否还留在 service，而是：

**最终回复必须只由一个显式阶段生成，不能由工具副作用和 service if-else 混合拼装。**

## 9. 挂起策略

当前阶段仍由 service 执行挂起，但口径必须统一。

### 9.1 澄清挂起

当 `mode == clarify` 时：

- `clarification_question` 必须非空
- `should_suspend == true`
- `suspend_reason == clarification`

service 负责：

- 先把澄清问题作为 assistant message 发给用户
- 再把 graph 状态置为 `suspended`

### 9.2 审批挂起

当 `mode == approval_pending` 时：

- `approval_pending == true`
- `should_suspend == true`
- `suspend_reason == approval_pending`

service 负责：

- 告知用户审批已发送
- 将 graph 置为 `suspended`

## 10. 文件改造清单

### 10.1 本阶段必须修改的文件

- `backend_business/services/agent/agents/session_controller/service.py`
  - 收敛流程控制
  - 改为消费显式结构化结果协议
  - 删除依赖隐式 context 副作用的收尾逻辑

- `backend_business/services/agent/agents/session_controller/tool_loop_runner.py`
  - 定义并返回结构化结果协议
  - 明确 `mode / should_suspend / delegated_agent`

- `backend_business/services/agent/agents/session_controller/tools.py`
  - 删除 `_mark_tool_loop_should_stop`
  - 删除 `_stop_after_tool_round`
  - 删除 `_forced_tool_loop_reply`
  - 保留能力适配

- `backend_business/services/agent/agents/session_controller/prompt_builder.py`
  - 强化对总控 LLM 的输出约束
  - 明确要求模型产出可映射到结构化结果协议的行为

### 10.2 建议新增的文件

- `backend_business/services/agent/agents/session_controller/contracts.py`
  - 定义 `SessionControllerDecisionMode`
  - 定义 `SessionControllerLoopResult`
  - 定义 `SuspendReason`

如果不想新增文件，也至少应在现有 runner 中引入清晰的数据结构，而不是裸 dict。

### 10.3 本阶段需要同步修改的测试

- `tests/agent_chat/test_session_controller_service.py`
  - 改为校验 service 是否正确消费结构化结果

- `tests/agent_chat/test_session_controller_tools.py`
  - 删除依赖 `_stop_after_tool_round` 的断言
  - 强化“tools 不控制父流程”的约束测试

- 建议新增：
  - `tests/agent_chat/test_session_controller_result_contract.py`
  - 专门测试 `mode / should_suspend / delegated_agent / suspend_reason`

## 11. 删除候选

### 11.1 本阶段完成后可删除或废弃

- `SessionControllerTools` 中：
  - `_mark_tool_loop_should_stop`
  - `_stop_after_tool_round`
  - `_forced_tool_loop_reply`

### 11.2 后续阶段可删除

- `SessionControllerService` 中依赖零散 context 字段做业务分支的老代码
- 各子 Agent service 的 inline 兼容调用路径

## 12. 验收标准

本阶段方案落地后，应满足：

1. `SessionController` 仍然是用户唯一入口
2. tools 不再控制父流程的停止与收尾
3. `SessionControllerToolLoopRunner` 返回显式结构化结果
4. service 只根据结构化结果进行挂起、成功、失败处理
5. 澄清与审批挂起有统一字段表达
6. 现有 SSE 与会话链能力继续可用

## 13. 风险与注意事项

### 13.1 风险一：只改字段名，不改职责边界

如果只是把旧的隐式 context 副作用重新包装成几个新字段，但 tools 仍然在控制父流程，那这次收敛就是假的。

### 13.2 风险二：service 继续保留过多业务分支

如果 service 仍然在自己判断“这是不是澄清”“这是不是审批”“这是不是直接回复”，而不是消费显式 `mode`，则边界仍未清楚。

### 13.3 风险三：提前混入拓扑图方案

当前阶段如果又把文档和代码拉回拓扑图，会把问题重新搞复杂。此阶段应当聚焦在：

- 收敛职责
- 明确协议
- 去掉工具副作用

## 14. 后续阶段预留

等当前阶段完成并稳定后，再进入后续阶段：

1. 将 `SessionController` 迁移到拓扑图 / GraphExecutor
2. 将 `clarify / suspend / final_reply` 转成图中的显式阶段
3. 将子 Agent 委托从工具兼容层升级为 runtime 原生 `invoke`

但这些都**不属于当前阶段**。

## 15. 结论

当前阶段的正确做法不是“马上拓扑图化”，而是先把现有 `SessionController` 清理干净：

- 总控决策留在总控 Agent
- tools 只负责能力
- service 只负责状态机
- 所有关键收尾行为通过显式结果协议驱动

这一步做完，后面无论是否迁移到拓扑图，都会更稳、更容易实施。
