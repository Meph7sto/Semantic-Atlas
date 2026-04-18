"""Heuristics for deciding whether a compiled skill update is meaningful."""

from __future__ import annotations

from dataclasses import dataclass

from .skill_compiler import parse_skill_document


@dataclass(frozen=True, slots=True)
class SkillDedupResult:
    should_write: bool
    reason: str


class SkillDeduplicator:
    """Avoid rewriting identical skill content over and over."""

    def should_write(
        self,
        *,
        existing_skill: str | None,
        candidate_skill: str,
    ) -> SkillDedupResult:
        if not existing_skill or not str(existing_skill).strip():
            return SkillDedupResult(should_write=True, reason="missing_current_skill")

        existing_metadata, existing_sections = parse_skill_document(existing_skill)
        candidate_metadata, candidate_sections = parse_skill_document(candidate_skill)
        _ = existing_metadata, candidate_metadata
        if self._normalize_sections(existing_sections) == self._normalize_sections(
            candidate_sections
        ):
            return SkillDedupResult(should_write=False, reason="content_unchanged")
        return SkillDedupResult(should_write=True, reason="content_changed")

    @staticmethod
    def _normalize_sections(sections: dict[str, list[str]]) -> dict[str, tuple[str, ...]]:
        normalized: dict[str, tuple[str, ...]] = {}
        for key, values in sections.items():
            normalized[key] = tuple(
                " ".join(str(value or "").split()).strip().lower()
                for value in values or []
                if " ".join(str(value or "").split()).strip()
            )
        return normalized
