---
skill_id: exp_session_controller_requirement_delegate_seed_20260418_001
experience_target: session_controller_requirement_delegate
container_key: requirement_agent
prompt_builder_kind: session_controller_requirement_delegate
node_type: llm
task_pattern_summary: Session Controller 已确定进入需求管理委托阶段，需要由 requirement agent 完成查询、澄清或修改。
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- 总控已完成决策，当前阶段只负责执行需求查询、定位、修改或审批前准备。

## 推荐步骤

1. 先确认是否已有明确 requirement_id；若没有，先用列表或搜索工具完成唯一定位。
2. 如果是写操作，先收集足够的上下文，再决定是否允许写入或转为澄清。
3. 输出时保持结果和工具依据一致，避免脱离工具结果做自由发挥。

## 常见陷阱

- 不要在 requirement_id 未明确时直接执行写操作，也不要跳过定位步骤直接猜测目标需求。

## 结果呈现建议

- 明确区分查询结论、澄清问题、写入结果和审批等待状态。

## 成功案例模式摘要

- 先定位需求，再读取细节，最后根据目标动作进入查询、修改或审批分支。
