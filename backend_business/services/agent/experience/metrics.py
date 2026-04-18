"""Registry-backed metrics aggregation for the experience skill system."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from backend_business.config import settings

from .registry import SkillRegistry


@dataclass(frozen=True, slots=True)
class ExperienceTargetMetrics:
    target_id: str
    invocation_count: int
    injection_miss_count: int
    skill_hit_count: int
    miss_ratio: float
    rewrite_count: int
    review_fail_count: int
    sanitizer_fail_count: int
    requires_manual_review: bool
    needs_refinement: bool


@dataclass(frozen=True, slots=True)
class ExperienceMetricsSnapshot:
    target_metrics: tuple[ExperienceTargetMetrics, ...]
    skill_hit_count: int
    skill_miss_count: int
    skill_rewrite_count: int
    skill_review_fail_count: int
    skill_sanitizer_fail_count: int
    skill_target_distribution: dict[str, int]
    targets_requiring_review: tuple[str, ...]
    targets_pending_refinement: tuple[str, ...]


class ExperienceMetrics:
    """Build observability snapshots from the skill registry."""

    def __init__(
        self,
        root_path: str | Path | None = None,
        *,
        registry: SkillRegistry | None = None,
    ) -> None:
        self._root_path = Path(root_path or settings.AGENT_EXPERIENCE_ROOT)
        self._registry = registry or SkillRegistry(self._root_path)

    def snapshot(self) -> ExperienceMetricsSnapshot:
        payload = self._registry.load()
        targets = payload.get("targets") or {}
        target_metrics: list[ExperienceTargetMetrics] = []
        distribution: dict[str, int] = {}
        review_targets: list[str] = []
        refinement_targets: list[str] = []
        total_hits = 0
        total_misses = 0
        total_rewrites = 0
        total_review_failures = 0
        total_sanitizer_failures = 0

        for target_id, raw_entry in sorted(targets.items()):
            entry = raw_entry if isinstance(raw_entry, dict) else {}
            invocation_count = int(entry.get("invocation_count") or 0)
            miss_count = int(entry.get("injection_miss_count") or 0)
            hit_count = int(entry.get("skill_hit_count") or max(0, invocation_count - miss_count))
            miss_ratio = float(entry.get("miss_ratio") or 0.0)
            rewrite_count = int(entry.get("rewrite_count") or 0)
            review_fail_count = int(entry.get("review_fail_count") or 0)
            sanitizer_fail_count = int(entry.get("sanitizer_fail_count") or 0)
            requires_manual_review = bool(entry.get("requires_manual_review"))
            needs_refinement = bool(entry.get("needs_refinement"))

            target_metrics.append(
                ExperienceTargetMetrics(
                    target_id=str(target_id),
                    invocation_count=invocation_count,
                    injection_miss_count=miss_count,
                    skill_hit_count=hit_count,
                    miss_ratio=miss_ratio,
                    rewrite_count=rewrite_count,
                    review_fail_count=review_fail_count,
                    sanitizer_fail_count=sanitizer_fail_count,
                    requires_manual_review=requires_manual_review,
                    needs_refinement=needs_refinement,
                )
            )
            distribution[str(target_id)] = invocation_count
            total_hits += hit_count
            total_misses += miss_count
            total_rewrites += rewrite_count
            total_review_failures += review_fail_count
            total_sanitizer_failures += sanitizer_fail_count
            if requires_manual_review:
                review_targets.append(str(target_id))
            if needs_refinement:
                refinement_targets.append(str(target_id))

        return ExperienceMetricsSnapshot(
            target_metrics=tuple(target_metrics),
            skill_hit_count=total_hits,
            skill_miss_count=total_misses,
            skill_rewrite_count=total_rewrites,
            skill_review_fail_count=total_review_failures,
            skill_sanitizer_fail_count=total_sanitizer_failures,
            skill_target_distribution=distribution,
            targets_requiring_review=tuple(review_targets),
            targets_pending_refinement=tuple(refinement_targets),
        )
