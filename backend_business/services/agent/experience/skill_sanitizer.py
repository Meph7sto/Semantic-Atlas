"""Sanitize compiled skill text before persistence."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .collector import ExperienceMaterial


@dataclass(frozen=True, slots=True)
class SkillSanitizeResult:
    passed: bool
    sanitized_content: str
    failure_reason: str | None = None


class SkillSanitizer:
    """Redact obvious sensitive identifiers and reject unsafe drafts."""

    _REDACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
        (
            re.compile(r"\b(?:requirement|req|r)[-_ ]?\d+\b", re.I),
            "<redacted_requirement>",
        ),
        (
            re.compile(
                r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
                re.I,
            ),
            "<redacted_uuid>",
        ),
    )
    _BLOCKED_PATTERNS: tuple[re.Pattern[str], ...] = (
        re.compile(r"\b(?:requirement_id|req_id)\b", re.I),
    )

    def sanitize(
        self,
        *,
        content: str,
        material: ExperienceMaterial | None = None,
    ) -> SkillSanitizeResult:
        sanitized = str(content or "")
        for pattern, replacement in self._REDACTIONS:
            sanitized = pattern.sub(replacement, sanitized)

        if material is not None:
            for raw_value in (material.user_message, material.task_description):
                stripped = str(raw_value or "").strip()
                if stripped and len(stripped) >= 180 and stripped in sanitized:
                    return SkillSanitizeResult(
                        passed=False,
                        sanitized_content=sanitized,
                        failure_reason="skill draft still contains long raw source text",
                    )

        for pattern in self._BLOCKED_PATTERNS:
            if pattern.search(sanitized):
                return SkillSanitizeResult(
                    passed=False,
                    sanitized_content=sanitized,
                    failure_reason=f"blocked token leaked: {pattern.pattern}",
                )

        return SkillSanitizeResult(
            passed=True,
            sanitized_content=sanitized,
        )
