---
skill_id: exp_session_controller_classification_delegate_seed_20260418_001
experience_target: session_controller_classification_delegate
container_key: requirement_classification_agent
prompt_builder_kind: session_controller_classification_delegate
node_type: llm
task_pattern_summary: Session Controller 已确认进入需求分类委托阶段，需要专项 Agent 对目标需求完成分类并解释结果。
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- 当前阶段只负责完成需求分类，不承担需求修改或其他写操作。

## 推荐步骤

1. 如果上下文已给出选中 requirement_id，直接把它视为权威目标继续执行。
2. 如果目标不够明确，先通过列表、搜索或详情工具完成定位。
3. 调用分类工具后，输出分类结果及必要解释，不扩展到无关业务建议。

## 常见陷阱

- 不要要求用户重复提供已经在上下文中存在的 requirement_id，也不要把分类阶段变成需求编辑阶段。

## 结果呈现建议

- 先说明分类结论，再给出简短依据，避免输出冗长 JSON 或额外噪音。

## 成功案例模式摘要

- 在已知目标需求的情况下，直接分类并用简洁中文解释结果。
