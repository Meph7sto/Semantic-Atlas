from __future__ import annotations

from datetime import datetime, timezone
import os
from pathlib import Path
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.experience.skill_store import SkillStore


def test_skill_store_initializes_target_layout(tmp_path: Path):
    store = SkillStore(tmp_path / ".agent_skills")

    target_dir = store.ensure_target("session_controller_decision")

    assert target_dir == tmp_path / ".agent_skills" / "session_controller_decision"
    assert target_dir.exists()
    assert (target_dir / "archive").exists()


def test_skill_store_writes_and_archives_current_skill(tmp_path: Path):
    store = SkillStore(tmp_path / ".agent_skills")
    target_id = "session_controller_decision"

    current_path = store.write_current(
        target_id,
        "---\nskill_id: skill-1\n---\nseed one\n",
    )
    replacement_path = store.write_current(
        target_id,
        "---\nskill_id: skill-2\n---\nseed two\n",
        archived_at=datetime(2026, 4, 18, 12, 30, tzinfo=timezone.utc),
    )

    archive_paths = store.list_archives(target_id)

    assert current_path == replacement_path
    assert store.read_current(target_id) == "---\nskill_id: skill-2\n---\nseed two\n"
    assert len(archive_paths) == 1
    assert archive_paths[0].name == "20260418T123000Z.md"
    assert archive_paths[0].read_text(encoding="utf-8") == (
        "---\nskill_id: skill-1\n---\nseed one\n"
    )


def test_skill_store_restores_latest_archive(tmp_path: Path):
    store = SkillStore(tmp_path / ".agent_skills")
    target_id = "session_controller_decision"

    store.write_current(
        target_id,
        "---\nskill_id: skill-1\n---\nseed one\n",
    )
    store.write_current(
        target_id,
        "---\nskill_id: skill-2\n---\nseed two\n",
        archived_at=datetime(2026, 4, 18, 12, 30, tzinfo=timezone.utc),
    )
    archive_name = store.list_archives(target_id)[0].name
    restored_path = store.restore_archive(target_id, archive_name=archive_name)

    assert restored_path == store.build_current_path(target_id)
    assert store.read_current(target_id) == "---\nskill_id: skill-1\n---\nseed one\n"
