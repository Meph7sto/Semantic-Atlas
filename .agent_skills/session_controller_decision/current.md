---
skill_id: exp_session_controller_decision_20260418T062647Z_002
experience_target: session_controller_decision
container_key: conductor
prompt_builder_kind: session_controller_decision
node_type: llm
task_pattern_summary: 执行 Session Controller 的结构化决策与工具调度。
iteration: 2
invocation_count: 0
injection_miss_count: 0
created_at: '2026-04-18T00:00:00Z'
last_updated_at: '2026-04-18T06:26:47Z'
last_used_at: null
derived_from:
  graph_id: <redacted_uuid>
  subgraph_key: sg_controller_intake
  node_keys:
  - turn_1__sg_sg_controller_intake_r1
  - turn_1__sg_sg_controller_intake_r2
---

## 适用场景

- Session Controller 需要先做结构化决策，再决定是否进入委托或回复阶段。
- 适用于总控需要先判断任务路由、是否委托以及是否直接回复的决策阶段。

## 推荐步骤

1. 先判断用户诉求属于直接回复、需求管理、冲突检测还是需求分类。
2. 如果任务目标不明确，优先产出最小必要澄清，而不是盲目委托子阶段。
3. 如果需要委托，明确选择唯一目标 route_key，并保证 conclusion 保持结构化且可被后续阶段消费。
4. 先判断当前任务是否需要展开拓扑、委托专项 Agent，还是可以直接回复，不要同时保留多个互相竞争的执行路径。
5. 若决定委托，先明确 delegate_agent、目标 requirement 和阶段目标，再进入 invoke 或后续阶段。
6. 若信息不足以安全决策，优先输出最小澄清问题，而不是直接假设用户意图。

## 常见陷阱

- 不要同时给出多个互斥 route_key 或把“澄清”和“委托”混在同一次完成信号里。
- 不要在还未完成路由判断时同时输出直接回复和委托决策，避免把总控状态推入冲突分支。

## 结果呈现建议

- 结论需要便于后续阶段直接消费，优先保持字段稳定、语义清晰。
- 先给出结论，再补充支撑证据或限制条件，保持表达紧凑可执行。
- 决策结果应显式体现后续动作，例如直接回复、委托、澄清或挂起。

## 成功案例模式摘要

- 面对明确的业务任务时，总控先定类，再把执行权交给最合适的专项阶段。
- 常见成功路径是先完成任务路由，再将决策收束为单一路径并把必要上下文一并传递给后续节点。
