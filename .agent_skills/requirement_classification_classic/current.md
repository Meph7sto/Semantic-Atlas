---
skill_id: exp_requirement_classification_classic_seed_20260418_001
experience_target: requirement_classification_classic
container_key: requirement_classification_agent
prompt_builder_kind: ""
node_type: llm
task_pattern_summary: 经典 tool-loop 模式下的需求分类 Agent，需要定位需求、执行分类并返回解释。
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- 需求分类 Agent 在经典模式中直接完成需求定位、分类和结果说明。

## 推荐步骤

1. 优先复用上下文中已经明确的 requirement_id，减少重复澄清。
2. 当目标不明确时，先用查询工具完成定位，再进入分类步骤。
3. 输出聚焦分类结果和必要解释，不扩展到修改建议或无关分析。

## 常见陷阱

- 不要在已有 requirement_id 的情况下重复向用户索要同一信息，也不要把分类结果和编辑动作混在一起。

## 结果呈现建议

- 先给分类结论，再给简短依据，整体保持自然中文和低噪音。

## 成功案例模式摘要

- 对明确目标需求直接分类，对模糊目标先定位后分类。
