---
skill_id: exp_conflict_detection_tool_loop_seed_20260418_001
experience_target: conflict_detection_tool_loop
container_key: conflict_detection
prompt_builder_kind: ""
node_type: llm
task_pattern_summary: 经典 tool-loop 模式下的冲突检测 Agent，需要对指定需求执行冲突识别并给出解释。
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- 冲突检测 Agent 直接在经典模式下处理用户请求，不经过 Session Controller 的委托子阶段。

## 推荐步骤

1. 先确认冲突检测对象是否明确，必要时先列举或检索需求。
2. 获取目标需求详情后再调用冲突检测工具。
3. 只根据工具返回总结是否冲突及主要原因。

## 常见陷阱

- 不要在缺失目标需求详情时直接给出冲突判断，也不要把推测内容写成确定结论。

## 结果呈现建议

- 输出顺序保持“是否冲突”在前、“原因解释”在后，避免冗长铺垫。

## 成功案例模式摘要

- 通过“定位 -> 详情 -> 检测 -> 总结”的固定路径稳定完成冲突判断。
