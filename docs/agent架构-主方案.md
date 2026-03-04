# Agent 架构设计——主方案

## 整体架构概述

整体架构分为四个层次：**会话层、领域层、执行层、数据底座**。

- **会话层**：理解用户自然语言意图，转化为系统可执行命令，管理对话流程。
- **领域层**：采用"虚拟 Actor"模式，封装每条需求的核心状态和完整生命周期。
- **执行层**：专门处理耗时较长的计算任务（LLM 调用、向量检索、OCR 等），避免阻塞核心业务流程。
- **数据底座**：基于事件溯源（Event Sourcing）和读写分离（CQRS）设计，确保所有操作可追溯、可回放、可审计。

---

## 一、会话层

会话层是用户与系统之间的语义转换边界，职责严格限定为：将用户自然语言意图转化为可执行动作序列，并将结果反馈用户。**不持有任何业务数据，不承担任何领域计算。**

### 1.1 内部 Agent 构成

**会话总控 Agent**

系统入口与出口。结合对话上下文识别用户意图和目标对象（某条需求、某个项目），决定委托给哪个下层 Agent 处理；对需求工程领域语义保持不透明，仅管控流程走向。

**计划 Agent**

**非默认路径，仅在拓扑模板无法匹配时启用。** 系统默认路径是：框架层根据当前指令类型匹配对应的计算拓扑模板，将其注入到目标 Agent 的第一个节点 `injected_context` 中，Agent 按模板各节点填充上下文后直接执行，无需计划 Agent 介入。

当指令类型无法匹配任何已有拓扑模板时，才由会话总控激活计划 Agent。计划 Agent 承接委托后，将用户意图拆解为具有显式依赖关系与成功标准的有序执行步骤序列，在执行过程中依据中间结果动态调整路径——判断应触发重试、执行降级还是向上澄清，完全自主规划执行结构。

### 1.2 通信机制：逻辑 Sidebar 模式

系统引入了 **Sidebar（边车）机制**。为了控制内存等架构资源开销，系统不采取独立进程，而是使用**逻辑 Sidebar（强封装的通信 SDK / 胖客户端）**代替物理 Sidecar，作为所有 Container 内部的标准通信枢纽。Sidebar 是一个**需要独立设计的 service 模块**，承载路由表维护、健康检查、重试熔断等非功能性能力，各 Agent/Worker 通过注入或导入的方式使用它，但其内部实现对调用方完全不透明。

- **基于职责的语义路由（Capability-Based Routing）**：
  Agent 之间不互相关心具体谁在执行。Agent 发出的不再是具体的网络请求地址，而是指明任务的意图声明（例如：“我需要一个能做 L4 细化的 Worker”）。Agent 调用时不需要管对方具体是多少号，只要知道其职责即可，代码层面仅需调用如 `sidebar.send({role: "LLM_Worker", payload: task})`。由 Sidebar 负责查找空闲且健康的对应节点并将消息投递过去。
  
- **非功能性逻辑的完美下沉**：
  将“业务逻辑（Agent 脑子里的事）”和“通信调度（跑腿的事）”彻底解耦。诸如“最多重试 3 次”、“长耗时心跳检测”、熔断和超时等机制，直接配置并在 Sidebar 层实施生效。各种由于网络或节点状态导致的重试实际上是 Sidebar 捕获到底层特定错误并自动发起的新一轮路由，不再侵入 Agent 自身的业务代码中。
  
- **无缝对接执行图（Execution Graph）**：
  由于所有的跨组件、跨容器的调用都必须经过各自的 Sidebar SDK，Sidebar 天然成为了拦截并记录执行链路的最佳切入点。Sidebar 在转发或接收消息时自动生成 `span_id` 并记录执行图的“边”（如跨容器边、重试边），实现业务代码对分布式追踪的“零感知”。

### 1.3 质检失败处理策略

1. **自动重试**：计划 Agent 将质检结论作为新约束重新触发 Worker，执行图中产生重试边，原 WorkerContainer 保留并标注为重试源。重试上限为 **3 次**。
2. **挂起澄清**：3 次重试后仍失败，执行图置为 `Suspended`，会话总控向用户说明卡滞的质检项、已重试次数，并附上当前最优结果。用户补充输入后，系统将新输入作为**新节点的增量 input**，追加到原 AgentContainer 的节点序列末尾，推理循环重建完整上下文后继续执行，执行图从 `Suspended` 恢复为运行态。

---

## 二、领域层

领域层职责严格限定为：**维护每一条需求条目的状态完整性与变更一致性**。不承担推理、规划或跨需求协调职责。

### 2.1 RequirementActor

系统为每条需求分配一个 RequirementActor，以 `requirement_id` 为唯一标识，是该需求数据的唯一权威持有者。

Actor 内部维护五类数据：
- L1–L4 各层级结构化需求文本、验收标准、优先级与约束条件
- 会议片段、转写文本、截图标注等证据链引用
- 可测试性、完整性、冲突与歧义等质量标记
- 当前流程阶段（草稿 / 待评审 / 评审中 / 通过 / 驳回 / 已基线）
- 完整的事件流与状态快照（变更历史）

### 2.2 工作逻辑

收到 Command 后，首先校验当前状态是否允许该操作：
- **校验通过**：执行变更，将变更以不可变 Event 追加至事件流，返回成功。
- **校验失败**：返回失败原因，不产生任何事件。由调用方 Agent 自行决定后续路径（挂起或转向）。

针对同一 `requirement_id` 的命令串行处理，天然消除并发写入冲突，调用方无需外部锁。

### 2.3 生命周期管理（虚拟 Actor 模式）

- Command 到达时，运行时自动从事件存储加载事件流并重放，重建当前状态（激活）。
- 系统周期性写入快照，将重建复杂度从 O(n) 压缩至 O(k)。
- 一定时间内无消息时自动休眠、释放内存；下次 Command 到达时透明激活。
- 调用方始终以 `requirement_id` 寻址，无需感知 Actor 物理存在状态。

### 2.4 层间协作原则

Actor 对调用方完全不透明，不感知是哪个 Agent 发出命令，也不感知其他 Actor 的存在。跨需求协调（如冲突检测）完全在 Agent 侧完成。Worker 完成计算后可直接向 Actor 发送 Command 写回结果，无需经由 Agent 中转。

### 2.5 读己之所写（Read-Your-Writes）的强一致保障

系统采用 CQRS 架构，读模型通过异步订阅事件流更新，不可避免存在毫秒级延迟窗口。当 Worker 绕过 Agent 直接向 Actor 写回结果后，若 Agent 紧接着被唤醒或前端立刻请求查询，极易从 Read Model 拉取到尚未更新的旧数据，导致 Agent 基于“幻觉”做出错误规划，或令前端用户陷入困惑。

为彻底解决这一最终一致性带来的时间差问题，系统引入了**版本号比对（Version Fencing）**与**内存特权直读（Actor Ask）**相结合的混合机制：

1. **版本号栅栏（Version Fencing / 适用于外部与读库查询）**：
   - Actor 每次成功处理 Command 并追加事件后，会返回该需求实体单调递增的 `Version`（事件序列号）。
   - Worker 在完成任务并通知调用方（唤醒 Agent 或经 WebSocket 通知前端）时，显式附带该 `Version`。
   - 当调用方必须从 Read Model 查询数据时（如前端刷新列表、检索聚合等），请求携带 `min_version=X` 参数。若 Read Model 尚未消费更新至该版本，读接口会自动阻塞等待或轮询，直到投影追平该版本号后才返回结果，严防拉旧。
   
2. **Agent 强一致直读（Actor Ask / 适用于内部核心编排）**：
   - 尽管具备版本号阻塞机制，为保障 Agent 极速高频连贯推理（如：“Worker刚改完需求，Agent马上要查冲突”），允许 Agent 跳过读库，发出特殊的 `QueryCommand` **直接向 RequirementActor 请求数据**。
   - Actor 收到后，直接将其当前**内存中的最新状态快照**强一致地同步返回给 Agent。Actor 内存即绝对的“真相源”，此特权机制彻底免除了查询等待，仅对内部核心逻辑开放。

3. **上下文增量注入（极致优化）**：
   - 作为协同优化，Worker 在向 Actor 发送 Command 写回结果获得最新状态后，在唤醒 Agent 的消息体中，直接将变更后的关键数据作为增量上下文（`injected_context`）塞给 Agent。使得绝大多数流转下，Agent 甚至无需发起任何外部查询（无论是查库还是 Ask Actor），就地取得强一致的闭环反馈。

---

## 三、执行层

执行层的职责：**把 Agent 不该自己干的重活接过来，跑完了告诉 Agent 结果。**

"重活"是指耗时长、计算密集、或需调用外部服务的任务——LLM 文本生成、向量检索、OCR、冲突矩阵计算等。执行层把这些任务异步承接，Agent 可挂起等结果，也可在等待期间处理其他兼容消息。

### Worker 的核心设计

Worker 是**无状态执行单元**，每次任务所需的全部上下文均封装于 Task 消息中，执行完毕后即刻释放资源，不保留任何跨任务状态。

通信模式：从任务队列拉取 Task → 执行 → 发布 ResultEvent 通知 Agent。ResultEvent 经由 Sidebar 按 `task_id` 路由，Sidebar 查找对应 Checkpoint 定位到等待中的 AgentContainer，将结果投递给它；Agent 收到后将其作为新节点的增量 input，继续推理循环。当结果需要直接写回领域对象时，Worker 可绕过 Agent 直接向 Actor 发送 Command（如 LLM Worker 完成 L4 生成后直接发送 `UpdateL4ContentCommand`）。

---

## 四、数据底座

数据底座由四类存储组件构成，职责严格分离。

### 4.1 事件存储（Event Store）

系统**唯一真相来源**。Actor 每次处理 Command 所产生的 Event 均以追加写入方式持久化，已写入事件永不修改、永不删除。每条事件携带 `requirement_id`、事件类型、时间、操作人、变更数据及 Command 来源。Actor 当前状态通过重放事件序列重建；系统定期写入快照以加速激活。

### 4.2 读模型（Read Model / CQRS）

专门面向界面展示与分析查询的投影视图，通过订阅事件流异步更新，与写入路径完全分离：
- 需求列表视图：ID、标题、状态、优先级
- 需求详情视图：完整内容、证据链、评审历史
- 冲突视图：跨需求关联关系
- 基线差异视图：两版本变更对比

各读模型独立维护，损坏后可通过重放事件流从头重建，不影响写入侧。

### 4.3 执行图存储（Execution Graph Store）

记录每条用户指令的完整执行过程。管理三类数据：图基本信息（`graph_id`、起止时间、最终状态）、节点记录（各 Container 及内部节点）、边记录（容器内部边与跨容器边）。计算拓扑图亦存储于此，与执行图通过关联关系相互引用。

### 4.4 Agent Checkpoint 存储

Agent 进入 Waiting 状态时写入的**轻量等待索引**。每条 Checkpoint 记录：Agent 标识、进入 Waiting 的时间点、等待的 `task_id` 列表，并通过 `graph_id` 与执行图关联。

Checkpoint **不需要额外存储中间状态**——Agent 的完整执行上下文（所有节点的增量 input 与 output）已全部持久化于执行图存储中。当等待的结果到达时，系统直接从节点序列重建完整上下文，定位到挂起点后继续执行，Checkpoint 仅作为"正在等待哪些 task"的查找入口。

### 4.5 四类存储的关联关系

```
用户指令 → 唯一执行图（graph_id）
执行图中 Actor 调用节点 → 关联 requirement_id
Actor 处理 Command 产生的 Event → 反向关联触发它的执行图节点（call_node_id）
Agent Checkpoint → 同时关联 graph_id 与 task_id
```

通过这组关联，任意业务操作均可从用户指令出发，沿执行图追溯至领域层具体事件，实现端到端完整可观测性。

---

## 五、核心概念定义

### 5.1 Agent（智能体）

承担**决策与编排**职责。核心能力不在于计算，而在于推理——将开放性目标分解、规划并收敛为可执行操作序列。输出是结构化计划序列、命令集合或任务描述，不是计算结果本身。

Agent 分为两层：

**高层 Agent（跨流程编排）**
- 会话总控 Agent：系统入口，识别目标与意图，管控流程走向，对领域语义不透明。
- 计划 Agent：拆解执行步骤，动态调整路径，是系统动态适应性的核心承载者。

**低层 Agent（专项业务决策）**
- 需求细化 Agent：处理 L1→L4 逐层分解，内置各层质量评判标准。
- 质检 Agent：在提交、评审、基线等关键节点执行质量门禁（可测试性、完整性、冲突、歧义），输出带问题定位的结构化结论。
- 冲突检测 Agent：跨需求语义分析，对 Worker 返回的候选冲突对做最终语义裁决。
- 追溯 Agent：需求上下游关联关系的语义理解与覆盖性推断。
- 评审 Agent：将自然语言评审反馈解析为结构化变更动作，做意见合并/拆分决策。

> **大模型的定位**：LLM 本身不承担 Agent/Worker/Actor 任何角色语义。对大模型的调用被封装为 ToolCall 函数，由 Worker 在执行任务时显式调用。大模型调用作为 WorkerContainer 内部的执行步骤节点记录，不在图拓扑层面产生新容器或边。Agent 负责"用大模型做什么"，Worker 负责"怎么调用大模型"，三者职责不相互渗透。

### 5.2 Worker（任务执行器）

承担**确定性计算**职责的无状态执行单元。给定规范化输入，必然产生确定性输出，不涉及任何业务语义判断。Worker 实例完全同质，故障替换与扩容无需状态迁移。

**幂等性约束**：任务队列保证"至少一次"投递，Worker 处理逻辑须满足幂等性——对同一 `task_id` 的重复执行不产生额外副作用。

**超时机制**：长耗时任务（如 LLM 调用）需定期发送心跳；心跳中断则任务重新投递，对应 WorkerContainer 标记为 `TimedOut`，重试上限为 3 次，超限后执行图置为 `Suspended`。

### 5.3 Actor（业务状态持有者）

业务对象状态的**唯一权威持有者**，为每个业务实体划定严格一致性边界。所有状态修改必须以命令形式提交给 Actor 串行处理，不得绕过 Actor 直接操作底层存储。

采用命令驱动的事件溯源机制：Command → 前置条件校验 → 生成不可变 Event 追加至事件流 → 返回结果。任意历史状态可通过重放事件序列精确重建。

---

## 六、图结构定义

### 6.1 计算拓扑图（Computation Topology Graph）

系统对某类指令历史处理经验的结构化沉淀。节点代表处理主体类型（Agent 类型 / Worker 类型 / Actor 类型），边代表历史执行中频繁出现的交互模式（调用 / 命令 / 通知）。

计算拓扑图是**软性建议**，不是硬性约束。Agent 不需要主动查询拓扑图——AgentContainer 创建时，框架层自动根据当前指令类型匹配对应的推荐拓扑，将其注入到第一个节点的 `injected_context` 中。Agent 在第一轮推理时即可看到建议，自行决定是否采用、部分采用或完全放弃，整个查询过程对 Agent 完全透明。

### 6.2 执行图（Execution Graph）

对单次用户指令从到达至结束的完整执行过程的运行时记录。每条指令触发一张执行图的创建，动态生长，直至指令处理终止。

最终状态三选一：`Succeeded` / `Failed` / `Suspended`（等待用户补充输入）。

执行图与计算拓扑图的关系是**双向反馈**：拓扑图以软建议形式向 Agent 提供结构参考；执行图沉淀后，可归纳出新的高频路径模式，候选为新的拓扑图或对现有拓扑图进行修订，形成"运行→归纳→模板→建议→运行"的持续优化闭环。

### 6.3 容器（Container）

执行图中对某一处理主体**单次完整执行过程**的封装单元，是执行图的基本组织结构。

- `AgentContainer`：某个 Agent 的一次完整推理与编排过程
- `WorkerContainer`：某个 Worker 的一次完整计算过程
- `ActorContainer`：某个 Actor 对一条 Command 的一次完整处理过程

**ActorContainer 与命令队列**：Actor 对同一 `requirement_id` 的 Command 串行处理，但多个调用方可能在短时间内并发提交命令。为清晰表达这一排队过程，系统为每个 Actor 维护一个**命令队列（Command Queue）**——到达的 Command 先进入队列，Actor 逐条出队处理，每次出队处理对应创建一个新的 ActorContainer。执行图中，队列中等待处理的 Command 以"待处理"状态挂在 Actor 节点上，ActorContainer 创建后与对应的调用边关联，形成完整的 Command 到达 → 入队 → 出队处理 → 返回结果的可视化链路。

ActorContainer 的内部节点语义与 WorkerContainer 类似：Command 接收、前置条件校验、Event 写入、快照（可选）、返回结果，各步骤以顺序节点记录，步骤边界由 Actor 处理逻辑显式标记。

在同一执行图中，**每个 Agent/Worker 实例唯一对应一个容器**。但在特定情形下（如重试、再次调度），同一处理主体可另行产生一个新容器，原容器保留并标注关联关系（如重试源）。

### 6.4 内部节点（Intra-Container Node）

内部节点是容器内部记录处理主体单步行为的最小执行单元。**AgentContainer 与 WorkerContainer 的节点语义不同，不使用同一套定义。**

#### AgentContainer 的节点：一节点 = 一轮对话

AgentContainer 内的每个节点对应 Agent 的**一轮完整对话**，天然分为两半：前半是发给 LLM 的完整输入上下文（messages + injected_context），后半是 LLM 的回复（action 输出）。两半合在一起，构成一个完整节点，LLM 回复到达后作为整体一次性持久化。

```
AgentNode {
  node_id
  container_id
  sequence_index        // 当前 Container 内第几次推理

  input {
    messages            // 本节点新增的增量输入（上一节点 output 触发的 toolcall 结果、跨容器返回值等）
    injected_context    // 本节点注入的拓扑建议、系统提示、从节点序列重建的历史上下文（恢复执行时）等
  }

  output {
    type: "toolcall"              // 普通工具调用，结果作为下一节点的输入
        | "cross_container_call"  // 跨容器调用，触发新 Container，同时承担调用节点语义
        | "confirm_required"      // 需要用户显式确认，Agent 进入 Dispatching 状态等待；用户确认后结果作为下一节点的增量输入
        | "reply_to_user"         // 回复用户，Container 随之关闭
        | "suspend"               // 挂起，等待用户补充输入，执行图置为 Suspended
    content  // toolcall 列表 / 调用参数 / 确认请求描述 / 回复内容 / 挂起原因
  }

  status: "success" | "failed" | "timeout"
  started_at / ended_at
}
```

**设计要点：**

- **第一个节点的 input** 不只是用户消息，还包括系统提示词、计算拓扑图的软建议，以及恢复执行时从节点序列重建的历史上下文，统一放入 `injected_context`。
- **增量存储，运行时重建**：数据库中每个节点只持久化**本节点自身新增的增量信息**——即上一节点 output 所触发的那批新 messages（toolcall 结果、跨容器返回值、用户输入等）以及本次的 `injected_context`，加上本节点的 output。**不做全量 messages 快照**，不重复存储之前节点已有的内容。实际调用 LLM 时，按 `sequence_index` 顺序将当前 Container 内所有前序节点的 delta 依次拼接，重建完整 messages 数组后发送，重建逻辑由推理循环统一负责。
- **一次 LLM 输出多个 toolcall（并行调用）时，仍算一个节点**，`output.content` 记录 toolcall 列表，"一节点 = 一次推理"的对应关系保持干净。
- **`toolcall` 与 `cross_container_call` 的边界需显式区分**：前者（如查数据库、本地计算）在当前 Container 内完成，结果直接进入下一节点的 `messages`，不产生新容器；后者（如调用另一个 Agent 或 Worker）触发新 Container 创建，产生跨容器调用边。当 `output.type == "cross_container_call"` 时，该节点同时承担**调用节点**语义，无需单独设立"调用节点"类型。
- **返回节点**：被调用 Container 执行完毕时，其最后一个节点承担返回节点语义，通过返回边将结果传回调用方。每个 Container 至多一个返回节点，位于序列末尾。
- **节点产生机制（链式自动触发）**：节点由 Agent 的推理循环自动生成，无需外部显式创建。每当上一个节点的 output 到达（toolcall 结果返回、跨容器结果汇合、或用户首次输入），循环自动将其纳入 messages，组装下一节点的完整 input，发送给 LLM 等待回复；回复到达后，input + output 作为完整节点整体写入图存储，随即进入下一轮循环。第一个节点由 AgentContainer 创建时触发，output 类型为 `reply_to_user` 或 `suspend` 时循环终止，Container 随之关闭。

#### WorkerContainer 的节点：执行步骤节点

Worker 是确定性计算，没有 LLM 推理循环。其内部节点是顺序执行步骤，例如：构造 prompt、调用 LLM API（此处 LLM 只是工具函数）、解析返回结果、写回 Actor 等。

```
WorkerStepNode {
  node_id
  container_id
  sequence_index      // 当前 Worker 内第几个步骤

  step_name           // 步骤名称（如 construct_prompt / call_llm_api / parse_result / write_actor）

  input               // 本步骤的输入数据快照
  output              // 本步骤的输出数据快照（步骤失败时记录错误信息）

  status: "success" | "failed" | "timeout"
  started_at / ended_at
}
```

WorkerStepNode 与 AgentNode 的核心区别：步骤边界由 Worker 自身的执行逻辑显式标记（每个关键执行点前后各写一次快照），不依赖推理循环自动触发；每个步骤节点独立存储完整的输入/输出快照，不做增量存储，因为 Worker 步骤间的数据量通常较小且彼此独立。

### 6.5 边（Edge）

**容器内部边**：连接同一容器内相邻内部节点，表示步骤间先后顺序或条件分支。

**跨容器边**（三类）：
- **调用边**：AgentContainer 调用节点 → 被调用容器首个节点，携带调用参数快照
- **返回边**：被调用容器返回节点 → 发起调用容器等待节点，携带执行结果快照
- **重试边**：AgentContainer 重试决策节点 → 新建容器首个节点，携带重试原因

调用边与返回边成对出现，共同表达一次完整的跨容器交互。

**并行调用与汇合节点**：当 Agent 同时发起多个 Worker 调用时，每个被调用容器各自产生一条返回边，这些返回边**全部收敛至调用方 AgentContainer 中的同一个 AgentNode**（汇合节点）。汇合节点的 `input.messages` 中包含所有并行 Worker 的返回结果，合并后作为该次 LLM 推理的完整输入。Agent 侧通过维护 pending task 计数器感知并行任务的完成进度，计数归零后触发汇合节点的推理。这一设计无需引入新的边类型，复数条返回边同指一个节点即为并行汇合的图结构表达。

---

## 七、状态机与生命周期

### 7.1 RequirementActor 状态机

状态机定义为五元组 `M_actor = (S, C, δ, s₀, F)`，转换函数 δ 为偏函数（给定状态下的非法命令直接拒绝）。

状态转换流程：

```
Draft
  ├── [质量门禁通过] → PendingReview
  │     └── [启动评审] → UnderReview
  │           ├── [通过] → Approved
  │           │     └── [纳入基线] → Baselined
  │           │                └── [发起变更] → ChangeRequested → (重新细化与评审)
  │           └── [驳回] → Rejected
  │                 └── [修改后重新提交] → PendingReview
  └── [质量门禁未通过] → 留在 Draft
```

采用**确定性有限状态机**（非概率模型），相同命令在相同状态下必然产生相同迁移结果，确保需求演化路径完全可验证。

### 7.2 Worker 生命周期

双状态机，极为简单：

```
Idle —(dequeue)→ Executing —(complete/fail)→ Idle
```

无其他持久化状态，体现无状态设计的直接特征。

### 7.3 Agent 生命周期

状态空间：`Idle → Planning → Dispatching → Waiting → (Planning | Dispatching | Suspended | Succeeded | Failed)`

- `Planning`：意图解析、目标识别、步骤分解，以及向 Worker/Actor 发起普通调用
- `Dispatching`：专指需要**用户显式确认**的操作（如修改需求条目等后果不可逆的写操作），Agent 在此状态下等待用户确认后才继续执行
- `Waiting`：挂起上下文，等待异步 Worker 结果
- 结果到达后：满足成功标准则回 Planning；质检失败且未超重试限则重新触发；无法自动恢复则转 Suspended

**Checkpoint 机制**：Agent 每次进入 Waiting 前写入 Checkpoint（Agent 标识、挂起时间点、等待的 task_id 列表），并通过 `graph_id` 与执行图关联。由于节点序列已完整持久化，结果到达时直接从节点序列重建上下文并继续，Checkpoint 只作为等待任务的查找入口，无需额外保存中间状态。

---

## 八、协作示例

### 例 1：将需求细化为 L4

典型路径：`会话总控 → 计划 Agent → LLM Worker → 质检 Agent → RequirementActor`

质检发现可测试性不足 → 触发重试边，新建第二个 LLM WorkerContainer → 质检通过 → 计划 Agent 向 Actor 发送 Command → Actor 追加事件 → 执行图标记 `Succeeded`。

核心要点：拓扑图软建议被采纳；质检失败在图中形成闭合重试回路；LLM 调用作为 WorkerContainer 内部步骤节点存在，不在图拓扑层面产生新容器。

### 例 2：检查需求间冲突（部分偏离模板）

典型路径：`会话总控 → 冲突检测 Agent → 冲突矩阵计算 Worker → 冲突检测 Agent`

因需求数量较多，冲突检测 Agent 判断需先做语义分组，在执行路径中插入 RAG Worker 调用（拓扑图未定义此步骤）。随后并行触发 3 个冲突矩阵计算 WorkerContainer，汇合节点等待三者全部返回后继续推进。

### 例 3：合并评审意见（完全自由编排）

会话总控发现"刚才"对应的评审上下文未明确，判断与拓扑图典型路径不符，决定完全放弃模板，走自由接口，执行图记录"未采用模板"及放弃原因。

追溯 Agent 定位 `review_id` → 评审 Agent 将意见映射为结构化变更动作 → 向 Actor 发送 Command → Actor 校验发现需求处于基线锁定状态，校验失败 → 返回失败原因 → 会话总控发起澄清 → 执行图置为 `Suspended`。

核心要点：Actor 前置校验失败在执行图中完整记录；执行图以 `Suspended` 而非 `Failed` 终止，等待用户输入后恢复。
