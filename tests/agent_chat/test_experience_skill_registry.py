from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.experience.registry import SkillRegistry


def test_skill_registry_initializes_and_upserts_targets(tmp_path: Path):
    registry = SkillRegistry(tmp_path / ".agent_skills")
    updated_at = datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc)

    registry.initialize()
    registry.upsert_target(
        "session_controller_decision",
        skill_id="skill-1",
        current_skill_path="session_controller_decision/current.md",
        iteration=1,
        updated_at=updated_at,
    )

    payload = registry.load()
    entry = payload["targets"]["session_controller_decision"]

    assert payload["version"] == 1
    assert entry["skill_id"] == "skill-1"
    assert entry["current_skill_path"] == "session_controller_decision/current.md"
    assert entry["iteration"] == 1
    assert entry["invocation_count"] == 0
    assert entry["injection_miss_count"] == 0
    assert entry["last_updated_at"] == "2026-04-18T12:00:00Z"


def test_skill_registry_records_injection_outcomes(tmp_path: Path):
    registry = SkillRegistry(tmp_path / ".agent_skills")

    registry.initialize()
    registry.upsert_target(
        "session_controller_conflict_delegate",
        skill_id="skill-2",
        current_skill_path="session_controller_conflict_delegate/current.md",
        iteration=2,
        updated_at=datetime(2026, 4, 18, 11, 0, tzinfo=timezone.utc),
    )

    registry.record_injection_result(
        "session_controller_conflict_delegate",
        missed=False,
        used_at=datetime(2026, 4, 18, 12, 0, tzinfo=timezone.utc),
    )
    registry.record_injection_result(
        "session_controller_conflict_delegate",
        missed=True,
        used_at=datetime(2026, 4, 18, 13, 0, tzinfo=timezone.utc),
    )

    entry = registry.get_target("session_controller_conflict_delegate")

    assert entry is not None
    assert entry["invocation_count"] == 2
    assert entry["injection_miss_count"] == 1
    assert entry["skill_hit_count"] == 1
    assert entry["miss_ratio"] == 0.5
    assert entry["last_used_at"] == "2026-04-18T13:00:00Z"
    assert entry["needs_refinement"] is False


def test_skill_registry_marks_target_for_refinement_after_repeated_misses(tmp_path: Path):
    registry = SkillRegistry(tmp_path / ".agent_skills")

    registry.initialize()
    registry.upsert_target(
        "session_controller_conflict_delegate",
        skill_id="skill-2",
        current_skill_path="session_controller_conflict_delegate/current.md",
        iteration=2,
        updated_at=datetime(2026, 4, 18, 11, 0, tzinfo=timezone.utc),
    )

    for hour in range(5):
        registry.record_injection_result(
            "session_controller_conflict_delegate",
            missed=True,
            used_at=datetime(2026, 4, 18, 12 + hour, 0, tzinfo=timezone.utc),
            miss_threshold=0.4,
            min_miss_sample=5,
        )

    entry = registry.get_target("session_controller_conflict_delegate")

    assert entry is not None
    assert entry["miss_ratio"] == 1.0
    assert entry["needs_refinement"] is True
    assert entry["degraded"] is True
