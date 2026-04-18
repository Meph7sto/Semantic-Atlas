---
skill_id: exp_session_controller_decision_seed_20260418_001
experience_target: session_controller_decision
container_key: conductor
prompt_builder_kind: session_controller_decision
node_type: llm
task_pattern_summary: 用户发起会话控制任务，总控需要判断直接回复、澄清、挂起还是委托后续子阶段。
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- Session Controller 需要先做结构化决策，再决定是否进入委托或回复阶段。

## 推荐步骤

1. 先判断用户诉求属于直接回复、需求管理、冲突检测还是需求分类。
2. 如果任务目标不明确，优先产出最小必要澄清，而不是盲目委托子阶段。
3. 如果需要委托，明确选择唯一目标 route_key，并保证 conclusion 保持结构化且可被后续阶段消费。

## 常见陷阱

- 不要同时给出多个互斥 route_key 或把“澄清”和“委托”混在同一次完成信号里。

## 结果呈现建议

- 结论需要便于后续阶段直接消费，优先保持字段稳定、语义清晰。

## 成功案例模式摘要

- 面对明确的业务任务时，总控先定类，再把执行权交给最合适的专项阶段。
