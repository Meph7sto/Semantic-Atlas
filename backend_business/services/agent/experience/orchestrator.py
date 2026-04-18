"""End-to-end orchestration for experience skill writeback."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import logging
from typing import Any

from backend_business.config import settings

from .collector import ExperienceCollector, ExperienceMaterial
from .policies import ExperiencePolicyResolver
from .registry import SkillRegistry
from .review_agent import SkillReviewAgent
from .skill_compiler import (
    CompiledSkillDraft,
    SkillCompiler,
)
from .skill_dedup import SkillDeduplicator
from .skill_sanitizer import SkillSanitizer
from .skill_store import SkillStore
from .targets import ExperienceTarget

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ExperienceWritebackResult:
    status: str
    target_id: str | None = None
    reason: str | None = None
    skill_path: str | None = None
    skill_id: str | None = None


class ExperienceOrchestrator:
    """Coordinate collection, compilation, review, and persistence."""

    def __init__(
        self,
        *,
        root_path: str | Path | None = None,
        collector: ExperienceCollector | None = None,
        compiler: SkillCompiler | None = None,
        sanitizer: SkillSanitizer | None = None,
        review_agent: SkillReviewAgent | None = None,
        deduplicator: SkillDeduplicator | None = None,
        store: SkillStore | None = None,
        registry: SkillRegistry | None = None,
        policies: ExperiencePolicyResolver | None = None,
    ) -> None:
        self._root_path = Path(root_path or settings.AGENT_EXPERIENCE_ROOT)
        self._collector = collector or ExperienceCollector()
        self._compiler = compiler or SkillCompiler()
        self._sanitizer = sanitizer or SkillSanitizer()
        self._review_agent = review_agent or SkillReviewAgent()
        self._deduplicator = deduplicator or SkillDeduplicator()
        self._store = store or SkillStore(self._root_path)
        self._registry = registry or SkillRegistry(self._root_path)
        self._policies = policies or ExperiencePolicyResolver()

    @property
    def root_path(self) -> Path:
        return self._root_path

    def process_outcome(
        self,
        *,
        target: ExperienceTarget | None,
        graph_id: str,
        graph_service: Any | None,
        recorder: Any | None,
        scratchpad_snapshot: list[dict[str, Any]] | None,
        container_key: str | None = None,
        subgraph_key: str | None = None,
        user_message: str = "",
        task_description: str = "",
        final_conclusion: Any = None,
        runtime_status: str = "succeeded",
        final_error: str | None = None,
        node_key: str | None = None,
    ) -> ExperienceWritebackResult:
        if target is None:
            return ExperienceWritebackResult(
                status="skipped",
                reason="no_experience_target",
            )
        policy = self._policies.resolve(target)
        if not settings.ENABLE_AGENT_EXPERIENCE_SKILL:
            return ExperienceWritebackResult(
                status="skipped",
                target_id=target.target_id,
                reason="feature_disabled",
            )
        if not settings.AGENT_EXPERIENCE_ENABLE_WRITEBACK or not policy.enable_writeback:
            return ExperienceWritebackResult(
                status="skipped",
                target_id=target.target_id,
                reason="writeback_disabled",
            )
        if not policy.enabled:
            return ExperienceWritebackResult(
                status="skipped",
                target_id=target.target_id,
                reason="target_disabled",
            )

        now = datetime.now(timezone.utc)
        self._store.ensure_target(target.target_id)
        self._registry.initialize()

        material = self._collector.collect(
            target=target,
            graph_id=graph_id,
            graph_service=graph_service,
            recorder=recorder,
            scratchpad_snapshot=scratchpad_snapshot,
            container_key=container_key,
            subgraph_key=subgraph_key,
            user_message=user_message,
            task_description=task_description,
            final_conclusion=final_conclusion,
            runtime_status=runtime_status,
            final_error=final_error,
            node_key=node_key,
        )

        if (
            material.runtime_status == "succeeded"
            and len(material.tool_call_trace) < int(policy.min_tool_calls)
        ):
            self._registry.record_writeback_result(
                target.target_id,
                status="skipped",
                reason="insufficient_tool_calls",
                at=now,
            )
            return ExperienceWritebackResult(
                status="skipped",
                target_id=target.target_id,
                reason="insufficient_tool_calls",
            )

        existing_skill = self._store.read_current(target.target_id)
        draft = self._compile_draft(
            target=target,
            material=material,
            existing_skill=existing_skill,
            now=now,
        )
        dedup_result = self._deduplicator.should_write(
            existing_skill=existing_skill,
            candidate_skill=draft.content,
        )
        if not dedup_result.should_write:
            self._registry.record_writeback_result(
                target.target_id,
                status="skipped",
                reason=dedup_result.reason,
                at=now,
            )
            return ExperienceWritebackResult(
                status="skipped",
                target_id=target.target_id,
                reason=dedup_result.reason,
                skill_id=str(draft.metadata.get("skill_id") or ""),
            )

        sanitize_result = self._sanitizer.sanitize(
            content=draft.content,
            material=material,
        )
        if not sanitize_result.passed:
            self._registry.record_writeback_result(
                target.target_id,
                status="skipped_sanitizer",
                reason=sanitize_result.failure_reason or "sanitizer_failed",
                at=now,
            )
            return ExperienceWritebackResult(
                status="skipped",
                target_id=target.target_id,
                reason=sanitize_result.failure_reason or "sanitizer_failed",
            )

        review_result = self._review_agent.review(
            content=sanitize_result.sanitized_content,
        )
        if not review_result.passed:
            self._registry.record_writeback_result(
                target.target_id,
                status="skipped_review",
                reason="; ".join(review_result.missing_required),
                at=now,
            )
            return ExperienceWritebackResult(
                status="skipped",
                target_id=target.target_id,
                reason="; ".join(review_result.missing_required),
            )

        if settings.AGENT_EXPERIENCE_DRY_RUN:
            self._registry.record_writeback_result(
                target.target_id,
                status="dry_run",
                reason="writeback_skipped_in_dry_run",
                at=now,
            )
            return ExperienceWritebackResult(
                status="dry_run",
                target_id=target.target_id,
                reason="writeback_skipped_in_dry_run",
                skill_id=str(draft.metadata.get("skill_id") or ""),
            )

        skill_path = self._store.write_current(
            target.target_id,
            sanitize_result.sanitized_content,
            archived_at=now,
        )
        relative_path = skill_path.relative_to(self._root_path).as_posix()
        self._registry.upsert_target(
            target.target_id,
            skill_id=str(draft.metadata.get("skill_id") or ""),
            current_skill_path=relative_path,
            iteration=int(draft.metadata.get("iteration") or 1),
            updated_at=now,
        )
        self._registry.record_writeback_result(
            target.target_id,
            status="written",
            reason="writeback_completed",
            at=now,
        )
        self._maybe_refresh_shared_patterns(now=now)
        return ExperienceWritebackResult(
            status="written",
            target_id=target.target_id,
            skill_path=str(skill_path),
            skill_id=str(draft.metadata.get("skill_id") or ""),
        )

    def record_injection_feedback(
        self,
        *,
        target: ExperienceTarget | str | None,
        missed: bool,
        used_at: datetime | None = None,
    ) -> dict[str, Any] | None:
        target_id = (
            target.target_id
            if isinstance(target, ExperienceTarget)
            else str(target or "").strip()
        )
        if not target_id:
            return None
        policy = self._policies.resolve(target_id)
        return self._registry.record_injection_result(
            target_id,
            missed=missed,
            used_at=used_at or datetime.now(timezone.utc),
            miss_threshold=policy.miss_threshold,
            min_miss_sample=policy.min_miss_sample,
        )

    def rollback_target(
        self,
        target_id: str,
        *,
        archive_name: str | None = None,
        archive_path: str | Path | None = None,
    ) -> Path:
        now = datetime.now(timezone.utc)
        restored_path = self._store.restore_archive(
            target_id,
            archive_name=archive_name,
            archive_path=archive_path,
            archived_at=now,
        )
        relative_path = restored_path.relative_to(self._root_path).as_posix()
        current_skill = self._store.read_current(target_id)
        metadata = self._extract_skill_metadata(current_skill)
        self._registry.upsert_target(
            target_id,
            skill_id=str(metadata.get("skill_id") or ""),
            current_skill_path=relative_path,
            iteration=int(metadata.get("iteration") or 1),
            updated_at=now,
        )
        self._registry.record_writeback_result(
            target_id,
            status="rolled_back",
            reason="manual_archive_restore",
            at=now,
        )
        return restored_path

    def _compile_draft(
        self,
        *,
        target: ExperienceTarget,
        material: ExperienceMaterial,
        existing_skill: str | None,
        now: datetime,
    ) -> CompiledSkillDraft:
        if material.runtime_status == "failed":
            return self._compiler.apply_pitfall_update(
                target=target,
                material=material,
                existing_skill=existing_skill,
                now=now,
            )
        return self._compiler.compile_full(
            target=target,
            material=material,
            existing_skill=existing_skill,
            now=now,
        )

    def safe_process_outcome(self, **kwargs: Any) -> ExperienceWritebackResult:
        """Best-effort wrapper that never breaks the main execution path."""
        try:
            return self.process_outcome(**kwargs)
        except Exception as exc:  # pragma: no cover - defensive path
            logger.warning("experience writeback failed: %s", exc, exc_info=True)
            target = kwargs.get("target")
            target_id = target.target_id if isinstance(target, ExperienceTarget) else None
            return ExperienceWritebackResult(
                status="skipped",
                target_id=target_id,
                reason=f"orchestrator_error: {exc}",
            )

    def _maybe_refresh_shared_patterns(self, *, now: datetime) -> ExperienceWritebackResult | None:
        shared_policy = self._policies.resolve("shared_patterns")
        if (
            not settings.AGENT_EXPERIENCE_ENABLE_SHARED_PATTERNS
            or not shared_policy.enabled
            or not shared_policy.enable_writeback
        ):
            return None
        current_skills = self._load_current_target_skills()
        existing_shared_skill = self._store.read_current("shared_patterns")
        draft = self._compiler.compile_shared_patterns(
            current_skills=current_skills,
            existing_skill=existing_shared_skill,
            now=now,
        )
        if draft is None:
            return None
        dedup_result = self._deduplicator.should_write(
            existing_skill=existing_shared_skill,
            candidate_skill=draft.content,
        )
        if not dedup_result.should_write:
            self._registry.record_writeback_result(
                "shared_patterns",
                status="skipped",
                reason=dedup_result.reason,
                at=now,
            )
            return ExperienceWritebackResult(
                status="skipped",
                target_id="shared_patterns",
                reason=dedup_result.reason,
                skill_id=str(draft.metadata.get("skill_id") or ""),
            )
        skill_path = self._store.write_current(
            "shared_patterns",
            draft.content,
            archived_at=now,
        )
        relative_path = skill_path.relative_to(self._root_path).as_posix()
        self._registry.upsert_target(
            "shared_patterns",
            skill_id=str(draft.metadata.get("skill_id") or ""),
            current_skill_path=relative_path,
            iteration=int(draft.metadata.get("iteration") or 1),
            updated_at=now,
        )
        self._registry.record_writeback_result(
            "shared_patterns",
            status="written",
            reason="shared_patterns_refreshed",
            at=now,
        )
        return ExperienceWritebackResult(
            status="written",
            target_id="shared_patterns",
            skill_path=str(skill_path),
            skill_id=str(draft.metadata.get("skill_id") or ""),
        )

    def _load_current_target_skills(self) -> dict[str, str]:
        skills: dict[str, str] = {}
        for target_dir in self._root_path.iterdir() if self._root_path.exists() else []:
            if not target_dir.is_dir():
                continue
            target_id = str(target_dir.name or "").strip()
            if not target_id:
                continue
            current_skill = self._store.read_current(target_id)
            if current_skill:
                skills[target_id] = current_skill
        return skills

    @staticmethod
    def _extract_skill_metadata(content: str | None) -> dict[str, Any]:
        if not content:
            return {}
        from .skill_compiler import parse_skill_document

        metadata, _sections = parse_skill_document(content)
        return metadata
