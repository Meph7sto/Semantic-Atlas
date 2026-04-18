---
skill_id: exp_requirement_agent_classic_seed_20260418_001
experience_target: requirement_agent_classic
container_key: requirement_agent
prompt_builder_kind: ""
node_type: llm
task_pattern_summary: 经典 tool-loop 模式下的需求管理 Agent，需要在单项目上下文中完成查询、定位、修改或澄清。
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- 需求管理 Agent 以经典对话方式直接执行工具调用，不经过执行图委托子阶段。

## 推荐步骤

1. 先判断当前任务是查询、修改还是澄清，并按目标选择最小工具路径。
2. 若目标需求不明确，先用列表或搜索缩小范围，再读取详情确认。
3. 写操作前必须确认 requirement_id 与变更意图足够明确。

## 常见陷阱

- 不要在需求未唯一定位时直接写入，也不要让空白搜索词进入 search 工具。

## 结果呈现建议

- 用自然中文总结工具结果，必要时补充版本号、状态或澄清问题。

## 成功案例模式摘要

- 先定位，后读取，再执行查询或修改，并基于工具结果收束回复。
