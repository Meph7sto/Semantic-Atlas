from __future__ import annotations

import os
from pathlib import Path
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.config import settings
from backend_business.services.agent.experience import SkillRegistry, SkillRetriever, SkillStore
from backend_business.services.agent.experience.targets import ExperienceTarget

_SEED_SKILL = """---
skill_id: exp_session_controller_conflict_delegate_seed_20260418_001
experience_target: session_controller_conflict_delegate
container_key: conflict_detection
prompt_builder_kind: session_controller_conflict_delegate
node_type: llm
task_pattern_summary: 用户要求检测两个或多个需求之间的冲突
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- 当用户要求检查需求冲突时使用

## 推荐步骤

1. 先定位目标需求
2. 再读取需求详情
3. 最后基于工具结果输出冲突结论

## 常见陷阱

- 不要跳过详情读取

## 结果呈现建议

- 先给出是否冲突，再说明原因

## 成功案例模式摘要

- 常见成功路径是先读取详情再检测冲突
"""


def _seed_root(root: Path) -> None:
    store = SkillStore(root)
    registry = SkillRegistry(root)
    registry.initialize()
    store.write_current(
        "session_controller_conflict_delegate",
        _SEED_SKILL,
        archive_existing=False,
    )
    registry.upsert_target(
        "session_controller_conflict_delegate",
        skill_id="exp_session_controller_conflict_delegate_seed_20260418_001",
        current_skill_path="session_controller_conflict_delegate/current.md",
        iteration=1,
    )


def test_skill_retriever_returns_matching_skill_for_related_task(tmp_path: Path):
    root = tmp_path / ".agent_skills"
    _seed_root(root)
    retriever = SkillRetriever(root)

    result = retriever.retrieve(
        target=ExperienceTarget(
            target_id="session_controller_conflict_delegate",
            container_key="conflict_detection",
            prompt_builder_kind="session_controller_conflict_delegate",
            node_type="llm",
        ),
        user_message="请检查支付需求和退款需求是否冲突",
        task_description="检测两个需求之间是否冲突",
    )

    assert result is not None
    assert result.skill_id == "exp_session_controller_conflict_delegate_seed_20260418_001"
    assert result.target_id == "session_controller_conflict_delegate"
    assert result.score >= 0.7


def test_skill_retriever_skips_low_relevance_requests(tmp_path: Path):
    root = tmp_path / ".agent_skills"
    _seed_root(root)
    retriever = SkillRetriever(root)

    result = retriever.retrieve(
        target="session_controller_conflict_delegate",
        user_message="帮我更新这条需求的标题和描述",
        task_description="修改需求内容",
    )

    assert result is None


def test_skill_retriever_returns_shared_patterns_when_enabled(tmp_path: Path):
    root = tmp_path / ".agent_skills"
    _seed_root(root)
    store = SkillStore(root)
    store.write_current(
        "shared_patterns",
        """---
skill_id: exp_shared_patterns_seed_20260418_001
experience_target: shared_patterns
container_key: shared_patterns
prompt_builder_kind: shared_patterns
node_type: shared
task_pattern_summary: 检测两个需求之间是否冲突时先读取详情再输出结论
iteration: 1
invocation_count: 0
injection_miss_count: 0
created_at: "2026-04-18T00:00:00Z"
last_updated_at: "2026-04-18T00:00:00Z"
last_used_at: null
---

## 适用场景

- 适用于多个 target
- 适用于检测两个需求之间是否冲突的阶段

## 推荐步骤

1. 先读取详情
2. 再核对关键证据
3. 最后输出结论
""",
        archive_existing=False,
    )
    retriever = SkillRetriever(root)

    previous_flag = settings.AGENT_EXPERIENCE_ENABLE_SHARED_PATTERNS
    settings.AGENT_EXPERIENCE_ENABLE_SHARED_PATTERNS = True
    try:
        results = retriever.retrieve_for_injection(
            target="session_controller_conflict_delegate",
            user_message="请检查支付需求和退款需求是否冲突",
            task_description="检测两个需求之间是否冲突",
        )
    finally:
        settings.AGENT_EXPERIENCE_ENABLE_SHARED_PATTERNS = previous_flag

    assert [item.target_id for item in results] == [
        "session_controller_conflict_delegate",
        "shared_patterns",
    ]
