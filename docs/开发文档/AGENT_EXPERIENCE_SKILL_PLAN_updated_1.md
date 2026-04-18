# Semantic-Atlas Agent 经验技能化开发计划

> 本文档基于当前项目真实代码结构编写，目标是把 Agent 在执行图中的成功经验沉淀为可复用 Skill，并在后续同类任务中自动注入到对应执行阶段。

---

## 一、目标

构建一套完整的 Agent 经验技能化系统，使 Semantic-Atlas 的多 Agent 运行时具备以下能力：

1. 在任务执行完成后自动提炼经验
2. 将经验以 Skill 文件形式保存、归档、迭代
3. 在后续相似任务执行时自动检索并注入对应 Skill
4. 记录 Skill 的命中、失效、重炼和版本演进过程
5. 逐步覆盖 Session Controller、专项委托 Agent、经典 tool-loop 路径和跨容器共享模式

最终期望效果：

```text
任务执行
  -> 轨迹落盘
  -> 自动提炼经验
  -> Skill 入库（文件）
  -> 下次命中注入
  -> 命中效果评估
  -> 失败时重炼
```

---

## 二、项目现状与设计约束

当前项目已经具备经验技能化的核心基础，不需要新建一套执行框架。

### 2.1 当前主执行链路

当前多 Agent 主链路是：

`GraphExecutor -> TopologyInstantiator -> SubgraphRunner -> ToolLoopRunner`

相关代码位置：

- `backend_business/services/agent/execution/graph_executor.py`
- `backend_business/services/agent/execution/subgraph_runner.py`
- `backend_business/services/agent/execution/tool_loop_runner.py`
- `backend_business/services/agent/runtime/graph_recorder.py`
- `backend_business/services/agent/runtime/scratchpad.py`

### 2.2 当前可直接复用的能力

| 现有能力 | 说明 |
|------|------|
| execution graph 落盘 | 已记录 node / edge / container / output_summary / tool_call_results |
| Scratchpad | 已支持跨阶段工作记忆 |
| complete_phase | 已形成明确阶段完成信号 |
| invoke 子容器执行 | 已支持 call / return / 并发 fan-out / cancellation |
| graph meta patch | 已支持在运行中写状态和上下文摘要 |
| agent_runs | 已记录子运行时状态 |
| 测试基座 | `tests/agent_chat/` 已覆盖 GraphExecutor / SubgraphRunner / Session Controller |

### 2.3 设计约束

经验技能化开发必须遵循下面几个约束：

1. 不重建新的消息总线或新的状态存储体系
2. 经验优先挂接到现有 GraphExecutor 主路径
3. Skill 作为 prompt 资产，优先以文件形式管理
4. 原始执行轨迹仍由 execution graph 与 agent_runs 承担
5. 技能注入必须遵循“就近注入”，不能把所有经验塞给总控

---

## 三、总体方案

### 3.1 经验单位

在本项目中，经验单位不直接按笼统的 `container_type` 定义，而是按“执行阶段目标”定义：

`experience_target = container_key + prompt_builder_kind + node_type（必要时）`

这样做的原因：

- 一个容器里可能有多个职责完全不同的阶段
- Session Controller 内部既有决策阶段，也有委托阶段，也有回复阶段
- 按容器粗粒度注入，容易把错误经验注入到不相干的 prompt 中

### 3.2 Skill 分层

每个 Skill 建议分为三层内容：

1. `Meta`
   - 标识、作用范围、版本、命中统计、来源轨迹
2. `Gene`
   - 可复用的策略、步骤、适用场景、陷阱
3. `Capsule`
   - 典型成功案例的脱敏模式摘要

后续当系统成熟后，可再增加：

4. `Shared Pattern`
   - 跨 experience_target 共享的子模式经验

### 3.3 Skill 存储结构

```text
Semantic-Atlas/
├── .agent_skills/
│   ├── _registry.yaml
│   ├── session_controller_decision/
│   │   ├── current.md
│   │   └── archive/
│   ├── session_controller_requirement_delegate/
│   │   ├── current.md
│   │   └── archive/
│   ├── session_controller_conflict_delegate/
│   │   ├── current.md
│   │   └── archive/
│   ├── session_controller_classification_delegate/
│   │   ├── current.md
│   │   └── archive/
│   ├── requirement_agent_classic/
│   │   ├── current.md
│   │   └── archive/
│   ├── conflict_detection_classic/
│   │   ├── current.md
│   │   └── archive/
│   └── shared_patterns/
│       ├── current.md
│       └── archive/
└── backend_business/services/agent/experience/
    ├── __init__.py
    ├── targets.py
    ├── collector.py
    ├── orchestrator.py
    ├── skill_store.py
    ├── skill_loader.py
    ├── skill_retriever.py
    ├── skill_compiler.py
    ├── skill_sanitizer.py
    ├── skill_dedup.py
    ├── review_agent.py
    ├── registry.py
    ├── metrics.py
    └── policies.py
```

### 3.4 Skill 头部格式

```markdown
---
skill_id: exp_session_controller_conflict_delegate_20260418_001
experience_target: session_controller_conflict_delegate
container_key: conflict_detection
prompt_builder_kind: session_controller_conflict_delegate
node_type: llm
task_pattern_summary: 用户要求检测两个或多个需求之间的冲突，且总控已决定委托冲突检测阶段执行
iteration: 3
invocation_count: 21
injection_miss_count: 3
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: "2026-04-18T00:00:00Z"
derived_from:
  graph_id: "graph_xxx"
  subgraph_key: "conflict_delegate"
  node_keys:
    - "turn_3__conflict_delegate_r1"
---
```

### 3.5 Skill 正文格式

```markdown
## 适用场景

## 推荐步骤

## 常见陷阱

## 结果呈现建议

## 成功案例模式摘要
```

---

## 四、运行时完整流程

### 4.1 提炼流程

```text
阶段执行完成
    ↓
识别 experience_target
    ↓
收集素材
    ↓
规则去重
    ↓
语义去重
    ↓
提炼 Skill 草稿
    ↓
隐私过滤
    ↓
结构化评审
    ↓
写入 current.md
    ↓
归档旧版本
    ↓
更新 registry
```

### 4.2 注入流程

```text
子图开始构建 prompt
    ↓
识别 experience_target
    ↓
检索当前主 Skill
    ↓
相关度判断
    ↓
命中则注入到 system prompt
    ↓
记录本次注入 skill_id
```

### 4.3 效果反馈流程

```text
执行结束
    ↓
本次是否注入 Skill？
    ├── 否：仅记录普通执行统计
    └── 是：
          ├── 成功：invocation_count + 1
          └── 失败：invocation_count + 1, injection_miss_count + 1
                        ↓
                  miss_ratio 超阈值
                        ↓
                    触发重炼
```

---

## 五、核心模块设计

### 5.1 `targets.py`

职责：

- 解析当前运行上下文
- 将 `container_key / prompt_builder_kind / node_type / config_json` 映射为统一的 `experience_target`

输出建议：

```python
ExperienceTarget(
    target_id="session_controller_conflict_delegate",
    container_key="conflict_detection",
    prompt_builder_kind="session_controller_conflict_delegate",
    node_type="llm",
)
```

### 5.2 `collector.py`

职责：

- 从 recorder、scratchpad、graph_service、agent_runs 中收集提炼素材
- 为 compiler 输出统一结构

输入：

- graph_id
- subgraph_id / subgraph_key
- stage node keys
- execution result
- scratchpad snapshot

输出：

```json
{
  "experience_target": "...",
  "user_message": "...",
  "task_description": "...",
  "tool_call_trace": [...],
  "phase_conclusions": [...],
  "scratchpad_summary": [...],
  "final_conclusion": "...",
  "runtime_status": "succeeded"
}
```

### 5.3 `skill_compiler.py`

职责：

- 根据执行素材生成新的 Skill 草稿
- 已存在主 Skill 时，做迭代更新而不是无脑重写
- 失败态支持仅提炼 Pitfall

需要支持两种模式：

1. `full_compile`
2. `pitfall_only`

#### `full_compile` Prompt 模板建议

```text
你是 Semantic-Atlas 的 Agent 经验提炼器。

你的任务是根据一次成功执行的轨迹素材，为指定的 experience_target 生成或迭代更新一份 Skill。

要求：
1. 输出的是“下次遇到同类任务如何执行”的经验，不是复盘报告。
2. 只写操作模式、步骤、适用场景、陷阱和结果呈现建议，不要写具体 requirement 原文。
3. 如果已有主 Skill，请在其基础上增量更新，而不是整份重写风格漂移。
4. 步骤必须具体可执行，禁止使用“仔细分析”“综合判断”这类空泛表述。
5. 允许总结成功案例模式，但必须脱敏，不得保留 requirement_id、项目名、用户名、长段原文。
6. 输出格式必须是完整 Markdown Skill 文本，包含头部元数据和正文章节。

输入：
- experience_target: {experience_target}
- existing_skill: {existing_skill_or_empty}
- execution_material:
  - user_message: {user_message}
  - task_description: {task_description}
  - tool_call_trace: {tool_call_trace}
  - phase_conclusions: {phase_conclusions}
  - scratchpad_summary: {scratchpad_summary}
  - final_conclusion: {final_conclusion}

请输出更新后的完整 Skill 草稿。
```

#### `pitfall_only` Prompt 模板建议

```text
你是 Semantic-Atlas 的 Agent 失败经验提炼器。

这次任务执行失败了。请根据以下执行轨迹，总结出一条应写入 Skill“常见陷阱”章节的可操作规避规则。

要求：
1. 只输出一条失败经验，不要重写整份 Skill。
2. 必须写成“下次如何避免”的规则，而不是复述失败经过。
3. 禁止使用“仔细分析”“提高准确率”这类空泛表述。
4. 不得包含 requirement_id、项目名、用户名、长段 requirement 原文。
5. 输出内容应能直接 append 到“常见陷阱”章节。

输入：
- experience_target: {experience_target}
- user_message: {user_message}
- task_description: {task_description}
- tool_call_trace: {tool_call_trace}
- phase_conclusions: {phase_conclusions}
- final_error: {final_error}

请输出一条 Markdown 列表项文本。
```

### 5.4 `skill_sanitizer.py`

职责：

- 在写入前做显式脱敏
- 清除 requirement id、原文大段引用、项目内部命名、具体数值模式

建议两层实现：

1. 正则与规则清洗
2. 轻量 LLM 二次检查

### 5.5 `review_agent.py`

职责：

- 对 Skill 草稿做结构化评审
- 输出 pass / missing_required / optional_suggestions

通过条件：

- 有适用场景
- 有至少 3 条可执行步骤
- 有常见陷阱
- 不泄漏 requirement 原文与具体标识

### 5.6 `skill_dedup.py`

职责：

- 判断本次经验是否值得更新主 Skill

推荐两段式：

1. 规则级快速去重
2. LLM 语义去重

### 5.7 `skill_store.py`

职责：

- 读写 `current.md`
- 归档旧版本
- 管理目录结构初始化

### 5.8 `registry.py`

职责：

- 管理 `_registry.yaml`
- 更新 iteration / invocation_count / injection_miss_count / last_used_at
- 维护每个 target 的当前主 Skill 路径

### 5.9 `skill_retriever.py`

职责：

- 根据 `experience_target` 精确定位
- 对 `task_description / user_message` 做相关度判断
- 只返回命中的主 Skill

### 5.10 `skill_loader.py`

职责：

- 将 Skill 文本格式化为 prompt 片段
- 控制注入前缀、长度、成熟度提示语

### 5.11 `orchestrator.py`

职责：

- 串联完整流程：
  - target resolve
  - collect
  - dedup
  - compile
  - sanitize
  - review
  - store
  - registry update

它应当成为经验技能化的统一编排入口。

### 5.12 `metrics.py`

职责：

- 汇总经验技能化相关运行指标
- 为日志、监控面板、灰度观察提供统一统计口径

建议统计内容：

- skill 命中次数
- 注入失败次数
- 重炼次数
- 评审失败次数
- 脱敏失败次数
- target 分布

### 5.13 `policies.py`

职责：

- 统一承载经验技能化的策略规则，而不是把阈值和开关散落在 `loader / retriever / orchestrator / registry` 各处
- 为不同 `experience_target` 提供差异化策略配置
- 负责定义“是否允许提炼、是否允许注入、命中阈值多少、是否允许自动写回、是否允许共享模式参与”等规则

建议封装的策略项：

```python
ExperiencePolicy(
    experience_target="session_controller_conflict_delegate",
    enabled=True,
    enable_injection=True,
    enable_writeback=True,
    retrieval_threshold=0.72,
    min_tool_calls=2,
    miss_threshold=0.4,
    min_miss_sample=5,
    allow_shared_patterns=False,
    compiler_mode="default",
)
```

建议用途：

1. `retriever` 读取 target 级检索阈值
2. `orchestrator` 读取是否允许写回、是否允许 full_compile
3. `registry` 读取 miss 率触发阈值
4. `loader` 读取是否允许共享模式注入
5. 后续灰度阶段按 target 单独开关

建议默认策略：

- `session_controller_decision`
  - 检索阈值更高，写回更保守
- `session_controller_*_delegate`
  - 检索阈值中等，优先支持自动写回
- `*_classic`
  - 初期可只开启注入，不急于开启自动写回

---

## 六、接入点设计

### 6.1 GraphExecutor 接入

接入文件：

- `backend_business/services/agent/execution/graph_executor.py`

接入位置：

- `_drive_runner()` 成功返回 `ContainerResult` 后
- `resume()` 成功返回 `ContainerResult` 后
- `failed / suspended` 分支也要有失败态或挂起态统计入口

作用：

- 提炼入口容器经验
- 统计根容器命中情况

### 6.2 SubgraphRunner 接入

接入文件：

- `backend_business/services/agent/execution/subgraph_runner.py`

接入位置：

- `_build_subgraph_context()` 中识别 target 并为注入做上下文准备
- `_resolve_prompt_builder()` 调用前后注入 `_extra_system_context`
- `_advance_invoke()` 子容器返回后触发对应 target 的经验提炼

作用：

- 提炼 delegate 阶段经验
- 注入 graph mode 的 Skills

说明：

- `_extra_system_context` 在当前代码里已经有消费链，不是一个全新概念
- `backend_business/services/agent/execution/subgraph_runner.py` 中，`_resolve_prompt_builder()` 已经通过 `context.get("_extra_system_context")` 传给 `SubgraphPromptBuilder`
- `SubgraphPromptBuilder.build_system_prompt()` 也已经支持把 `extra_system_context` 拼进最终 system prompt
- 因此当前接入应写成“复用现有 dict context 字段”，不需要为运行时上下文额外增加类型定义
- 只有当后续把 context 从 `dict[str, Any]` 收口为强类型对象时，才需要同步更新类型定义

### 6.3 经典 prompt builder 接入

接入文件：

- `backend_business/services/agent/agents/conflict_detection_agent/prompt_builder.py`
- `backend_business/services/agent/agents/requirement_classification_agent/prompt_builder.py`
- `backend_business/services/agent/agents/requirement_agent/prompt_builder.py`

作用：

- 在经典 tool-loop 路径中也支持 Skill 注入

### 6.4 RuntimeGraphRecorder 接入

不改 recorder 的主体职责，但要复用其现有数据：

- `tool_call_results`
- `output_summary`
- `_task_context`
- `current_node_key`

必要时可增加辅助读取接口，但不建议改成“经验系统专用 recorder”。

---

## 七、阶段划分与开发内容

## Phase 1：基础设施与 Skill 存储层

目标：

- 建立 Skill 文件体系、注册表和基础读写能力

开发内容：

1. 创建 `.agent_skills/` 目录结构
2. 实现 `skill_store.py`
3. 实现 `registry.py`
4. 实现 `targets.py`
5. 增加配置项与 feature flag
6. 初始化首批种子 Skill

交付物：

- `.agent_skills/_registry.yaml`
- `.agent_skills/<experience_target>/current.md`
- `backend_business/services/agent/experience/{targets,skill_store,registry}.py`

验收标准：

- 可以初始化 Skill 目录
- 可以读写 current.md
- 可以归档旧版本
- 可以根据上下文解析 experience_target

---

## Phase 2：提炼链路与自动写回

目标：

- 在执行结束后自动提炼经验并写回主 Skill

开发内容：

1. 实现 `collector.py`
2. 实现 `skill_compiler.py`
3. 实现 `skill_sanitizer.py`
4. 实现 `review_agent.py`
5. 实现 `skill_dedup.py`
6. 实现 `orchestrator.py`
7. 在 `GraphExecutor` 和 `SubgraphRunner` 中挂接提炼入口
8. 支持失败态 pitfall-only 提炼

交付物：

- 自动提炼主链路
- 去重、过滤、评审、写入全流程

验收标准：

- 一次完整执行结束后可自动生成或更新 Skill
- 重复任务不会无限重写 Skill
- 脱敏失败时不会落盘
- 评审不通过时不会污染 current.md

---

## Phase 3：Skill 检索与 Prompt 注入

目标：

- 在执行阶段开始时自动检索并注入 Skill

开发内容：

1. 实现 `skill_retriever.py`
2. 实现 `skill_loader.py`
3. 在 `SubgraphRunner._build_subgraph_context()` 中准备检索上下文
4. 在 graph prompt builders 中接入 `_extra_system_context`
5. 在 classic prompt builders 中接入 Skill 注入
6. 记录 `_injected_skill_id`

交付物：

- graph mode 自动注入
- classic tool-loop 自动注入

验收标准：

- 同类任务第二次执行能带上对应 Skill
- 不同 target 之间不会串注入
- 低相关度场景不注入

---

## Phase 4：覆盖范围扩展

目标：

- 将经验技能化从首批阶段扩展到项目主要 Agent 能力面

建议覆盖顺序：

1. `session_controller_decision`
2. `session_controller_requirement_delegate`
3. `session_controller_conflict_delegate`
4. `session_controller_classification_delegate`
5. `requirement_agent_classic`
6. `conflict_detection_classic`
7. `requirement_classification_classic`

开发内容：

1. 给各 target 补种子 Skill
2. 增加 target-specific compiler 模板
3. 增加 target-specific sanitizer 规则
4. 增加 target-specific 检索阈值与写回策略

交付物：

- 多 target 统一运行
- target 级策略可配置

验收标准：

- 每个 target 都能独立生成、命中、更新
- 不同 target 的 current.md 互不污染

---

## Phase 5：效果反馈、重炼与观测

目标：

- 让系统知道“注入是否有效”，并具备自动重炼能力

开发内容：

1. 记录 `invocation_count`
2. 记录 `injection_miss_count`
3. 计算 miss ratio
4. 达阈值自动触发重炼
5. 增加 `metrics.py`
6. 增加日志与观测字段
7. 在 graph meta 或运行日志中记录命中与失效信息

建议观测指标：

- skill_hit_count
- skill_miss_count
- skill_rewrite_count
- skill_review_fail_count
- skill_sanitizer_fail_count
- skill_target_distribution

交付物：

- 反馈闭环
- 运行指标
- 基础观测面板数据源

验收标准：

- 能看见每个 target 的命中与失效率
- 失效率超阈值时能自动重炼

---

## Phase 6：共享模式与跨容器经验抽取

目标：

- 从单 target 经验，扩展到跨 target 共享的通用操作模式

适用场景示例：

- “先 list 再 detail 再 execute”的工具使用模式
- “先澄清再执行”的交互模式
- “批量任务先拆分再聚合”的执行模式

开发内容：

1. 设计 `shared_patterns/` 目录
2. 从多条 Skill 中提炼共享模式
3. 定义 shared pattern 注入规则
4. 控制 shared pattern 与 target-specific skill 的优先级

交付物：

- 共享模式 Skill
- target-specific + shared pattern 双层注入体系

验收标准：

- 共享模式不会覆盖专项技能
- 注入顺序稳定、可配置

---

## Phase 7：上线治理、回滚与长期维护

目标：

- 使经验技能化具备可上线、可灰度、可回滚、可维护能力

开发内容：

1. 增加开关：
   - 全局总开关
   - target 级开关
   - 注入开关
   - 自动写回开关
   - dry-run 开关
2. 增加回滚能力：
   - 从 `archive/` 回切 `current.md`
3. 增加治理规则：
   - 长期不命中的 Skill 降级
   - 长期 miss 高的 Skill 标记待人工复核
4. 增加发布策略：
   - 开发环境
   - 灰度环境
   - 正式环境

交付物：

- 灰度上线方案
- 回滚方案
- 长期治理策略

验收标准：

- 任意 target 可单独关闭
- current.md 可快速回滚
- 不影响现有 Agent 主业务链路

---

## 八、测试计划

### 8.1 单元测试

新增建议：

- `tests/agent_chat/test_experience_skill_targets.py`
- `tests/agent_chat/test_experience_skill_store.py`
- `tests/agent_chat/test_experience_skill_registry.py`
- `tests/agent_chat/test_experience_skill_dedup.py`
- `tests/agent_chat/test_experience_skill_sanitizer.py`
- `tests/agent_chat/test_experience_skill_review.py`
- `tests/agent_chat/test_experience_skill_loader.py`

### 8.2 集成测试

新增建议：

- `tests/agent_chat/test_experience_skill_pipeline.py`
- `tests/agent_chat/test_experience_skill_graph_integration.py`
- `tests/agent_chat/test_experience_skill_classic_integration.py`

### 8.3 对现有测试的补充

建议补充：

- `tests/agent_chat/test_subgraph_runner.py`
  - 断言注入 prompt 是否生效
- `tests/agent_chat/test_graph_executor.py`
  - 断言根容器执行后是否触发提炼
- `tests/agent_chat/test_session_controller_graph_mode.py`
  - 断言 decision / delegate 技能是否命中
- `tests/agent_chat/test_conflict_detection_agent_graph_mode.py`
  - 断言 conflict delegate 的经验闭环

### 8.4 验收重点

必须验证下面几点：

1. Skill 会写入正确 target
2. 低相关任务不会误注入
3. requirement 原文不会写进 Skill
4. 重复任务不会无限覆盖 current.md
5. 失败态只更新 pitfall
6. 命中统计与 miss 统计准确
7. 关闭 feature flag 后系统完全回退到旧行为

---

## 九、上线与迁移计划

### 9.1 上线顺序

建议顺序：

1. 开发环境开启 dry-run
2. 开发环境开启真实写回
3. 灰度环境开启写回但关闭注入
4. 灰度环境开启部分 target 注入
5. 正式环境逐步放量

### 9.2 回滚策略

回滚层次：

1. 关闭注入开关
2. 关闭自动写回开关
3. 回滚 current.md 到 archive 版本
4. 关闭整个经验技能化总开关

### 9.3 数据迁移

本方案不依赖数据库 schema 迁移即可启动。

仅需：

1. 初始化 `.agent_skills/`
2. 写种子 Skill
3. 配置 feature flag

后续如果需要把指标持久化到数据库，再单独增加轻量统计表。

---

## 十、配置项建议

```yaml
ENABLE_AGENT_EXPERIENCE_SKILL: "true"
AGENT_EXPERIENCE_ROOT: ".agent_skills"

AGENT_EXPERIENCE_ENABLE_WRITEBACK: "true"
AGENT_EXPERIENCE_ENABLE_INJECTION: "true"
AGENT_EXPERIENCE_DRY_RUN: "false"

AGENT_EXPERIENCE_MIN_TOOL_CALLS: 2
AGENT_EXPERIENCE_RETRIEVAL_THRESHOLD: 0.7
AGENT_EXPERIENCE_MISS_THRESHOLD: 0.4
AGENT_EXPERIENCE_MIN_MISS_SAMPLE: 5

AGENT_EXPERIENCE_COMPILER_MODEL: "gpt-4o-mini"
AGENT_EXPERIENCE_REVIEW_MODEL: "gpt-4o-mini"
AGENT_EXPERIENCE_DEDUP_MODEL: "gpt-4o-mini"
AGENT_EXPERIENCE_RETRIEVAL_MODEL: "gpt-4o-mini"

AGENT_EXPERIENCE_ENABLE_SHARED_PATTERNS: "false"
```

---

## 十一、关键文件清单

| 文件 | 职责 |
|------|------|
| `.agent_skills/_registry.yaml` | Skill 注册表 |
| `.agent_skills/<target>/current.md` | 当前主 Skill |
| `.agent_skills/<target>/archive/` | 历史版本归档 |
| `backend_business/services/agent/experience/targets.py` | target 识别 |
| `backend_business/services/agent/experience/collector.py` | 提炼素材收集 |
| `backend_business/services/agent/experience/orchestrator.py` | 总编排 |
| `backend_business/services/agent/experience/skill_store.py` | 文件读写与归档 |
| `backend_business/services/agent/experience/skill_loader.py` | 注入格式化 |
| `backend_business/services/agent/experience/skill_retriever.py` | 检索与相关度判断 |
| `backend_business/services/agent/experience/skill_compiler.py` | 草稿生成 |
| `backend_business/services/agent/experience/skill_sanitizer.py` | 脱敏 |
| `backend_business/services/agent/experience/skill_dedup.py` | 去重 |
| `backend_business/services/agent/experience/review_agent.py` | 结构化评审 |
| `backend_business/services/agent/experience/registry.py` | 注册表维护 |
| `backend_business/services/agent/experience/metrics.py` | 指标统计 |
| `backend_business/services/agent/experience/policies.py` | target 级策略与阈值管理 |
| `backend_business/services/agent/execution/graph_executor.py` | 根容器提炼接入点 |
| `backend_business/services/agent/execution/subgraph_runner.py` | 子容器提炼与注入接入点 |
| 各类 `prompt_builder.py` | prompt 注入位置 |

---

## 十二、潜在风险与应对

| 风险 | 影响 | 应对方式 |
|------|------|------|
| 技能注入导致总控 prompt 跑偏 | 高 | 按 experience_target 细粒度注入 |
| 提炼质量不稳定 | 中 | review + dedup + archive 回滚 |
| requirement 原文泄漏 | 高 | sanitizer 默认强制开启 |
| 写回过于频繁 | 中 | 去重、阈值控制、dry-run |
| graph mode 与 classic mode 行为不一致 | 中 | 分阶段接入并分别测试 |
| 共享模式覆盖专项技能 | 中 | 共享模式放低优先级并可单独关闭 |

---

## 十三、结论

这套开发计划的核心不是补一个独立功能点，而是在现有 GraphExecutor 主链路上，为 Semantic-Atlas 增加“经验积累、技能复用、效果反馈、持续重炼”的完整闭环。

按上述七个阶段推进后，项目会逐步具备：

1. 轨迹到经验的自动沉淀能力
2. 经验到 prompt 的自动注入能力
3. 注入效果的量化评估能力
4. 技能版本的长期治理能力
5. 多 target、多路径、跨容器模式的统一经验体系
