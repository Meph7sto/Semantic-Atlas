from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.experience.review_agent import SkillReviewAgent


def test_skill_review_agent_accepts_complete_skill():
    content = """---
skill_id: exp_demo_20260418T000000Z_001
experience_target: demo
container_key: demo
prompt_builder_kind: demo
node_type: llm
task_pattern_summary: demo
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- demo

## 推荐步骤

1. step one
2. step two
3. step three

## 常见陷阱

- pitfall

## 结果呈现建议

- result

## 成功案例模式摘要

- summary
"""
    result = SkillReviewAgent().review(content=content)

    assert result.passed is True
    assert result.missing_required == []


def test_skill_review_agent_rejects_missing_steps():
    content = """---
skill_id: exp_demo_20260418T000000Z_001
experience_target: demo
container_key: demo
prompt_builder_kind: demo
node_type: llm
---

## 适用场景

- demo

## 推荐步骤

1. only one

## 常见陷阱

- pitfall
"""
    result = SkillReviewAgent().review(content=content)

    assert result.passed is False
    assert any("recommended steps" in item for item in result.missing_required)
