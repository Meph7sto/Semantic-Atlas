# Semantic-Atlas

## What This Repository Is

Semantic-Atlas 是一个面向需求工程的语义分析平台，覆盖会议转写解析、上下文构建、需求抽取、需求管理、追溯分析、冲突检测、分类、多 Agent 协作与通用对话。仓库采用前后端分离的三层结构：`frontend/` 提供交互工作台，`backend_business/` 负责编排、权限、会话与执行图，`backend_inference/` 负责模型推理与分析能力。它既是一个业务平台，也是一个“可视化、可追踪的 Agent 执行框架”实验场。

## Long-Term Direction

- 将需求工程相关能力统一到可追溯的 Agent 执行框架下，让需求修改、分析、裁决、派发和汇总都能在执行图中被记录与回放。
- 让会话总控 Agent 成为用户侧统一入口，专项 Agent 只处理单一职责，逐步补齐质检、影响分析、知识检索、评审纪要等未落地 Agent。
- 保持需求状态写入口唯一：所有需求写入都经由 RequirementActor/需求管理 Agent 路径，其他 Agent 默认保持只读分析职责。
- 在不破坏现有可用链路的前提下，逐步收敛设计文档、拓扑模板能力与实际运行时实现之间的差异。

## Current Focus Area

- 当前仓库最值得继承的能力是 3 个已落地 Agent 的统一实现骨架：`session_controller`、`requirement_agent`、`conflict_detection_agent`。
- 近期仓库级重点应是以现有 Agent 为模板继续新增专项 Agent，而不是重新发明新的 Agent 基础设施。
- 在继续扩展 Agent 之前，后续协作者应优先按“当前代码的真实运行方式”理解系统，而不是按设计文档的理想态假设实现。

## Constraints

- 保持三层结构：前端负责工作台与可视化，`backend_business/` 负责会话/编排/执行图/权限，`backend_inference/` 负责模型推理与算法能力。 -- 这是当前代码组织和 API 分层的基本边界。
- 需求写入只能走需求管理 Agent 与 RequirementActor 路径。 -- 这是仓库里最重要的读写分离约束，避免多个 Agent 直接改需求状态。
- 新 Agent 应优先复用现有执行底座，而不是新造一套运行时。 -- 当前可复用底座已经包括 `ToolLoopRunner`、运行图记录、会话图链、SSE 输出与前端图可视化。
- 现阶段真实的多 Agent 协作主要是直接函数调用与内联执行，不是运行中的 MessageBus/Sidebar 闭环。 -- README 和设计文档比代码更超前，新增实现必须以现有落地代码为准。
- 仓库使用 `superspec commit`，正常仓库工作不要直接运行 `git commit`。 -- 这是仓库显式工作流规则。

## Stable Decisions

- 已落地的自定义 Agent 有 3 个：`session_controller`、`requirement_agent`、`conflict_detection_agent`。
- 新 Agent 的首选实现模板是目录式薄适配结构：`service.py`、`prompt_builder.py`、`tool_loop_runner.py`、`runtime_graph_recorder.py`，按需补 `tools.py` 或复用 `services/agent/tools/` 下工具集。
- 通用执行内核以 `backend_business/services/agent/execution/tool_loop_runner.py` 为核心；各 Agent 通过上下文、提示词、工具集和图记录器做薄适配。
- 运行时观测以执行图为主：Agent 会话、图链、节点状态、工具结果、最终回复都应能被记录并在前端查看。
- `session_controller` 不直接处理领域写入或专业裁决；它负责意图识别、调度专项 Agent、汇总结果并回复用户。
- `requirement_agent` 是当前唯一已落地的需求读写 Agent；它通过 Actor Runtime 桥接 RequirementActor，工具集以 `list/search/get/update` 为主。
- `conflict_detection_agent` 是只读分析 Agent；它当前支持 `classic` 与 `graph` 两种执行模式，其中 `graph` 模式接入 `GraphExecutor`。
- 新 Agent 若需要被总控编排，优先在 `SessionControllerTools` 中新增 `invoke_<agent>` 工具，并沿用现有“内联写入父执行图”的方式实现。

## Open Questions

- 下一批优先落地的专项 Agent 顺序是什么：质检、影响分析、知识检索、评审纪要，还是别的 Agent。
- 后续新增 Agent 应继续沿用当前直接内联委托方式，还是开始把 Sidebar / MessageBus / invoke-Waiting-return 闭环真正接入运行时。
- 拓扑模板与 GraphExecutor 应成为所有新 Agent 的默认执行模式，还是继续允许“经典 ToolLoopRunner 模式”和“图模式”并存。

## Important Context

这套 Agent 架构的“设计文档版本”和“代码真实落地版本”之间存在差距。文档里大量描述了理想化的多 Agent 拓扑、Sidebar 路由、invoke/Waiting/return 闭环和更多专项 Agent；但当前真正可运行、可复用、且已有测试覆盖的实现核心是以下三套：

- `backend_business/services/agent/agents/requirement_agent/`
- `backend_business/services/agent/agents/conflict_detection_agent/`
- `backend_business/services/agent/agents/session_controller/`

后续工程师要仿制新 Agent，最重要的不是先读所有方案文档，而是先读这三套实现，并同步看对应路由、前端页面和测试。当前代码里的真实模式如下：

- 后端每个 Agent 都有独立 FastAPI router、独立 session/message/graph-chain API。
- 前端每个 Agent 都有独立页面、独立 API 封装，并复用执行图画布与节点详情面板。
- `session_controller` 通过工具把任务委托给 `requirement_agent` 或 `conflict_detection_agent`，并把子 Agent 的节点直接写入父图。
- `requirement_agent` 的独特点是 RequirementActor 读写桥接、prompt payload format、context mode 和 scratchpad。
- `conflict_detection_agent` 的独特点是冲突检测专用工具与 `GraphExecutor` 图模式。

仓库中关于“还有哪些 Agent 终局上应该存在”的参考清单主要在 `docs/agent设计类型.md` 与 `docs/Agent方案_updated.md`，但这些文档更适合回答“未来想要什么”，不适合直接回答“现在该怎么做”。当两者冲突时，应优先相信当前代码与测试。

## How To Work In This Repository

先读顺序建议如下：

1. `README.md`
2. `backend_business/services/agent/execution/tool_loop_runner.py`
3. `backend_business/services/agent/agents/session_controller/`
4. `backend_business/services/agent/agents/requirement_agent/`
5. `backend_business/services/agent/agents/conflict_detection_agent/`
6. `backend_business/api/routers/{agent_chat,conflict_agent_chat,session_controller_chat}.py`
7. `frontend/src/views/alpha/{RequirementAgentChat,ConflictAgentChat,SessionControllerAgentChat}.vue`
8. `tests/agent_chat/` 下对应测试

实现新 Agent 时，默认按下面的最小闭环补齐：

1. 新建 Agent 服务目录，复用现有 `service/prompt_builder/tool_loop_runner/runtime_graph_recorder` 模式。
2. 定义该 Agent 的工具边界，工具应体现清晰职责，不要把多个专业判断混进一个 Agent。
3. 为 Agent 挂独立 router，提供 sessions、messages、graph-chain、stream 等接口。
4. 为前端补独立 API 模块与 Alpha 调试页，继续复用现有执行图可视化组件。
5. 如果该 Agent 需要被总控调度，在 `SessionControllerTools` 增加 `invoke_<agent>` 入口，并仿照现有内联执行方式记录 call/start/end/return。
6. 优先补与现有 Agent 同风格的单测与 FastAPI 合约测试。

实现时优先仿照当前可工作的现实模板，不要先尝试把整个理想态架构一次性补齐。只有在明确要推进基础设施重构时，才去动 Sidebar、MessageBus、拓扑模板全局执行链路等尚未完全接入的部分。

---
*Last updated: 2026-03-29*
