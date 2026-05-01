from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.experience import ExperienceMetrics, SkillRegistry


def test_experience_metrics_aggregates_registry_counts(tmp_path: Path):
    root = tmp_path / ".agent_skills"
    registry = SkillRegistry(root)
    registry.initialize()
    registry.upsert_target(
        "session_controller_conflict_delegate",
        skill_id="skill-1",
        current_skill_path="session_controller_conflict_delegate/current.md",
        iteration=1,
        updated_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )
    registry.record_injection_result(
        "session_controller_conflict_delegate",
        missed=False,
        used_at=datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc),
    )
    registry.record_writeback_result(
        "session_controller_conflict_delegate",
        status="written",
        at=datetime(2026, 4, 18, 14, 0, tzinfo=timezone.utc),
    )
    registry.upsert_target(
        "requirement_agent_tool_loop",
        skill_id="skill-2",
        current_skill_path="requirement_agent_tool_loop/current.md",
        iteration=1,
        updated_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )
    registry.record_injection_result(
        "requirement_agent_tool_loop",
        missed=True,
        used_at=datetime(2026, 4, 18, 15, 0, tzinfo=timezone.utc),
    )
    registry.record_writeback_result(
        "requirement_agent_tool_loop",
        status="skipped_review",
        at=datetime(2026, 4, 18, 16, 0, tzinfo=timezone.utc),
    )

    snapshot = ExperienceMetrics(root).snapshot()

    assert snapshot.skill_hit_count == 1
    assert snapshot.skill_miss_count == 1
    assert snapshot.skill_rewrite_count == 1
    assert snapshot.skill_review_fail_count == 1
    assert snapshot.skill_target_distribution["session_controller_conflict_delegate"] == 1
    assert snapshot.skill_target_distribution["requirement_agent_tool_loop"] == 1
