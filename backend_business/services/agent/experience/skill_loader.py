"""Render retrieved skills into prompt-ready system context."""

from __future__ import annotations

from dataclasses import dataclass

from .skill_compiler import parse_skill_document
from .skill_retriever import RetrievedSkill

_SECTION_ORDER = (
    "适用场景",
    "推荐步骤",
    "常见陷阱",
    "结果呈现建议",
)


@dataclass(frozen=True, slots=True)
class LoadedSkillPrompt:
    """Prompt-ready representation of a retrieved skill."""

    skill_id: str
    target_id: str
    score: float
    skill_ids: tuple[str, ...]
    shared_skill_ids: tuple[str, ...]
    prompt_text: str


class SkillLoader:
    """Format a retrieved skill into compact system-prompt context."""

    def render_prompt(
        self,
        *,
        retrieved_skill: RetrievedSkill,
        max_items_per_section: int = 4,
    ) -> LoadedSkillPrompt:
        return self.render_prompt_bundle(
            retrieved_skills=[retrieved_skill],
            max_items_per_section=max_items_per_section,
        )

    def render_prompt_bundle(
        self,
        *,
        retrieved_skills: list[RetrievedSkill],
        max_items_per_section: int = 4,
    ) -> LoadedSkillPrompt:
        normalized_skills = [
            item for item in retrieved_skills
            if isinstance(item, RetrievedSkill)
        ]
        if not normalized_skills:
            raise ValueError("retrieved_skills must not be empty")
        prompt_parts = [
            self._render_single_prompt(
                retrieved_skill=item,
                max_items_per_section=max_items_per_section,
            )
            for item in normalized_skills
        ]
        primary_skill = normalized_skills[0]
        shared_skill_ids = tuple(
            item.skill_id
            for item in normalized_skills
            if item.target_id == "shared_patterns"
        )
        return LoadedSkillPrompt(
            skill_id=primary_skill.skill_id,
            target_id=primary_skill.target_id,
            score=primary_skill.score,
            skill_ids=tuple(item.skill_id for item in normalized_skills),
            shared_skill_ids=shared_skill_ids,
            prompt_text="\n\n".join(part.strip() for part in prompt_parts if part.strip()),
        )

    def _render_single_prompt(
        self,
        *,
        retrieved_skill: RetrievedSkill,
        max_items_per_section: int = 4,
    ) -> str:
        metadata, sections = parse_skill_document(retrieved_skill.content)
        heading = (
            "## 已命中的共享模式"
            if retrieved_skill.target_id == "shared_patterns"
            else "## 已命中的经验技能"
        )
        lines: list[str] = [
            heading,
            "",
            f"- skill_id: {retrieved_skill.skill_id}",
            f"- experience_target: {retrieved_skill.target_id}",
            f"- relevance_score: {retrieved_skill.score:.2f}",
            "",
            "请把下面经验当作当前阶段的优先执行参考。",
            "仅在与本轮任务匹配时采用；如果与实时工具结果冲突，以实时工具证据为准。",
        ]

        summary = str(metadata.get("task_pattern_summary") or "").strip()
        if summary:
            lines.extend(
                [
                    "",
                    "### 任务模式摘要",
                    f"- {summary}",
                ]
            )

        for section_name in _SECTION_ORDER:
            items = [
                str(item or "").strip()
                for item in (sections.get(section_name) or [])[:max_items_per_section]
                if str(item or "").strip()
            ]
            if not items:
                continue
            lines.extend(["", f"### {section_name}"])
            if section_name == "推荐步骤":
                for index, item in enumerate(items, start=1):
                    lines.append(f"{index}. {item}")
            else:
                for item in items:
                    lines.append(f"- {item}")

        return "\n".join(lines).strip()
