from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.experience.skill_sanitizer import SkillSanitizer


def test_skill_sanitizer_redacts_requirement_identifiers():
    content = "需要先定位 R-12，再给出结论。"

    result = SkillSanitizer().sanitize(content=content)

    assert result.passed is True
    assert "<redacted_requirement>" in result.sanitized_content
    assert "R-12" not in result.sanitized_content


def test_skill_sanitizer_rejects_blocked_requirement_id_token():
    content = "结果中包含 requirement_id: abc"

    result = SkillSanitizer().sanitize(content=content)

    assert result.passed is False
    assert result.failure_reason is not None
