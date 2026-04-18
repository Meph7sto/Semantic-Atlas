from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.experience.skill_dedup import SkillDeduplicator


def test_skill_deduplicator_skips_identical_section_content():
    existing = """---
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

- demo scene

## 推荐步骤

1. step one
2. step two
3. step three

## 常见陷阱

- demo pitfall

## 结果呈现建议

- demo result

## 成功案例模式摘要

- demo summary
"""
    candidate = existing.replace("20260418T000000Z_001", "20260418T010000Z_002")

    result = SkillDeduplicator().should_write(
        existing_skill=existing,
        candidate_skill=candidate,
    )

    assert result.should_write is False
    assert result.reason == "content_unchanged"
