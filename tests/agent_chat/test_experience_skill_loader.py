from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.experience import RetrievedSkill, SkillLoader


def test_skill_loader_renders_compact_prompt_context():
    loader = SkillLoader()

    loaded = loader.render_prompt(
        retrieved_skill=RetrievedSkill(
            skill_id="skill-1",
            target_id="conflict_detection_classic",
            score=0.88,
            content="""---
skill_id: skill-1
experience_target: conflict_detection_classic
task_pattern_summary: 检测需求冲突
---

## 适用场景

- 适用于检测冲突

## 推荐步骤

1. 先定位需求
2. 再读取详情
3. 最后输出结论

## 常见陷阱

- 不要跳过工具读取

## 结果呈现建议

- 先结论后原因
""",
        )
    )

    assert loaded.skill_id == "skill-1"
    assert loaded.target_id == "conflict_detection_classic"
    assert "## 已命中的经验技能" in loaded.prompt_text
    assert "### 推荐步骤" in loaded.prompt_text
    assert "relevance_score: 0.88" in loaded.prompt_text


def test_skill_loader_renders_bundle_with_shared_patterns():
    loader = SkillLoader()

    loaded = loader.render_prompt_bundle(
        retrieved_skills=[
            RetrievedSkill(
                skill_id="skill-1",
                target_id="conflict_detection_classic",
                score=0.88,
                content="""---
skill_id: skill-1
experience_target: conflict_detection_classic
task_pattern_summary: 检测需求冲突
---

## 适用场景

- 适用于检测冲突

## 推荐步骤

1. 先定位需求
2. 再读取详情
3. 最后输出结论

## 常见陷阱

- 不要跳过工具读取
""",
            ),
            RetrievedSkill(
                skill_id="shared-1",
                target_id="shared_patterns",
                score=0.71,
                content="""---
skill_id: shared-1
experience_target: shared_patterns
task_pattern_summary: 共享模式
---

## 适用场景

- 适用于多个 target

## 推荐步骤

1. 先确认目标
2. 再执行最小路径
3. 最后收束结论
""",
            ),
        ]
    )

    assert loaded.skill_ids == ("skill-1", "shared-1")
    assert loaded.shared_skill_ids == ("shared-1",)
    assert "## 已命中的经验技能" in loaded.prompt_text
    assert "## 已命中的共享模式" in loaded.prompt_text
