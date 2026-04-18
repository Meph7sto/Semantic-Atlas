---
skill_id: exp_session_controller_conflict_delegate_seed_20260418_001
experience_target: session_controller_conflict_delegate
container_key: conflict_detection
prompt_builder_kind: session_controller_conflict_delegate
node_type: llm
task_pattern_summary: Session Controller 已确认进入冲突检测委托阶段，需要专项 Agent 对目标需求进行冲突判断。
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- 当前阶段需要对两个或多个需求进行冲突检测，并返回简洁、可解释的结论。

## 推荐步骤

1. 先确认用户指定的目标需求是否足够明确；不明确时先补齐定位信息。
2. 使用详情工具读取待检测需求内容，再执行冲突检测工具。
3. 最终结论只基于工具返回，明确说明是否冲突以及主要冲突原因。

## 常见陷阱

- 不要在没有读取需求详情的情况下直接下冲突判断，也不要把工具未返回的原因写进结论。

## 结果呈现建议

- 先给出冲突结论，再补充关键证据点，保持中文表达简洁直达。

## 成功案例模式摘要

- 先定位目标，再获取详情，再完成检测，最后用紧凑结论收束输出。
