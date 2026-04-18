"""Lightweight structural review for compiled skills."""

from __future__ import annotations

from dataclasses import dataclass
import re

from .skill_compiler import parse_skill_document


@dataclass(frozen=True, slots=True)
class SkillReviewResult:
    passed: bool
    missing_required: list[str]
    optional_suggestions: list[str]


class SkillReviewAgent:
    """Review compiled skills for minimum structure and safety."""

    def review(self, *, content: str) -> SkillReviewResult:
        metadata, sections = parse_skill_document(content)
        missing_required: list[str] = []
        optional_suggestions: list[str] = []

        if not metadata.get("skill_id"):
            missing_required.append("missing skill_id metadata")
        if not sections.get("适用场景"):
            missing_required.append("missing scenario section")
        if len(sections.get("推荐步骤", [])) < 3:
            missing_required.append("recommended steps must contain at least 3 items")
        if not sections.get("常见陷阱"):
            missing_required.append("missing pitfalls section")
        if re.search(r"\b(?:requirement_id|req_id)\b", content, re.I):
            missing_required.append("raw requirement identifiers leaked")
        if not sections.get("结果呈现建议"):
            optional_suggestions.append("add result presentation guidance")
        if not sections.get("成功案例模式摘要"):
            optional_suggestions.append("add success pattern summary")

        return SkillReviewResult(
            passed=not missing_required,
            missing_required=missing_required,
            optional_suggestions=optional_suggestions,
        )
