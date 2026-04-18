"""Target-aware retrieval for experience skill injection."""

from __future__ import annotations

from dataclasses import dataclass
import difflib
from pathlib import Path
import re
from typing import Any

from backend_business.config import settings

from .policies import ExperiencePolicyResolver
from .registry import SkillRegistry
from .skill_compiler import parse_skill_document
from .skill_store import SkillStore
from .targets import ExperienceTarget

_TOKEN_PATTERN = re.compile(r"[a-z0-9_]+|[\u4e00-\u9fff]+", re.I)


@dataclass(frozen=True, slots=True)
class RetrievedSkill:
    """A skill selected for prompt injection."""

    skill_id: str
    target_id: str
    content: str
    score: float
    path: str | None = None
    metadata: dict[str, Any] | None = None


class SkillRetriever:
    """Retrieve the current target-specific skill when the task is relevant."""

    def __init__(
        self,
        root_path: str | Path | None = None,
        *,
        store: SkillStore | None = None,
        registry: SkillRegistry | None = None,
        policies: ExperiencePolicyResolver | None = None,
        default_threshold: float | None = None,
    ) -> None:
        self._root_path = Path(root_path or settings.AGENT_EXPERIENCE_ROOT)
        self._store = store or SkillStore(self._root_path)
        self._registry = registry or SkillRegistry(self._root_path)
        self._policies = policies or ExperiencePolicyResolver()
        self._default_threshold = (
            float(default_threshold)
            if default_threshold is not None
            else float(settings.AGENT_EXPERIENCE_RETRIEVAL_THRESHOLD)
        )

    @property
    def root_path(self) -> Path:
        return self._root_path

    def retrieve(
        self,
        *,
        target: ExperienceTarget | str | None,
        user_message: str = "",
        task_description: str = "",
        threshold: float | None = None,
    ) -> RetrievedSkill | None:
        if not settings.ENABLE_AGENT_EXPERIENCE_SKILL:
            return None
        if not settings.AGENT_EXPERIENCE_ENABLE_INJECTION:
            return None

        target_id = self._resolve_target_id(target)
        if not target_id:
            return None
        policy = self._policies.resolve(target_id)
        if not policy.enabled or not policy.enable_injection:
            return None

        content, path = self._load_skill(target_id)
        if not content:
            return None

        metadata, sections = parse_skill_document(content)
        experience_target = str(metadata.get("experience_target") or "").strip()
        if experience_target and experience_target != target_id:
            return None

        score = self._compute_relevance(
            user_message=user_message,
            task_description=task_description,
            metadata=metadata,
            sections=sections,
        )
        effective_threshold = (
            float(threshold)
            if threshold is not None
            else float(policy.retrieval_threshold or self._default_threshold)
        )
        if score < effective_threshold:
            return None

        skill_id = str(metadata.get("skill_id") or "").strip() or f"{target_id}:current"
        return RetrievedSkill(
            skill_id=skill_id,
            target_id=target_id,
            content=content,
            score=score,
            path=path,
            metadata=metadata,
        )

    def retrieve_for_injection(
        self,
        *,
        target: ExperienceTarget | str | None,
        user_message: str = "",
        task_description: str = "",
    ) -> list[RetrievedSkill]:
        target_id = self._resolve_target_id(target)
        if not target_id:
            return []
        policy = self._policies.resolve(target_id)
        primary = self.retrieve(
            target=target_id,
            user_message=user_message,
            task_description=task_description,
            threshold=policy.retrieval_threshold,
        )
        if primary is None:
            return []
        retrieved_skills = [primary]
        if settings.AGENT_EXPERIENCE_ENABLE_SHARED_PATTERNS and policy.allow_shared_patterns:
            shared_policy = self._policies.resolve("shared_patterns")
            shared_skill = self.retrieve(
                target="shared_patterns",
                user_message=user_message,
                task_description=task_description,
                threshold=shared_policy.retrieval_threshold,
            )
            if shared_skill is not None:
                retrieved_skills.append(shared_skill)
        return retrieved_skills

    def _load_skill(self, target_id: str) -> tuple[str | None, str | None]:
        entry = self._registry.get_target(target_id) or {}
        relative_path = str(entry.get("current_skill_path") or "").strip()
        if relative_path:
            candidate_path = self._root_path / relative_path
            if candidate_path.exists():
                return candidate_path.read_text(encoding="utf-8"), str(candidate_path)

        current_path = self._store.build_current_path(target_id)
        if not current_path.exists():
            return None, None
        return current_path.read_text(encoding="utf-8"), str(current_path)

    @staticmethod
    def _resolve_target_id(target: ExperienceTarget | str | None) -> str:
        if isinstance(target, ExperienceTarget):
            return str(target.target_id or "").strip()
        return str(target or "").strip()

    def _compute_relevance(
        self,
        *,
        user_message: str,
        task_description: str,
        metadata: dict[str, Any],
        sections: dict[str, list[str]],
    ) -> float:
        query_candidates = [
            str(task_description or "").strip(),
            str(user_message or "").strip(),
            " ".join(
                part
                for part in (
                    str(task_description or "").strip(),
                    str(user_message or "").strip(),
                )
                if part
            ).strip(),
        ]
        document_candidates = [
            str(metadata.get("task_pattern_summary") or "").strip(),
            "\n".join(
                item
                for values in sections.values()
                for item in values
                if str(item or "").strip()
            ).strip(),
        ]
        scores = [
            self._score_pair(query, document)
            for query in query_candidates
            if query
            for document in document_candidates
            if document
        ]
        if not scores:
            return 0.0
        return max(scores)

    def _score_pair(self, query: str, document: str) -> float:
        normalized_query = _normalize_text(query)
        normalized_document = _normalize_text(document)
        if not normalized_query or not normalized_document:
            return 0.0

        query_tokens = _extract_features(normalized_query)
        document_tokens = _extract_features(normalized_document)
        shared_features = query_tokens & document_tokens
        coverage = 0.0
        if query_tokens:
            coverage = len(shared_features) / len(query_tokens)
        keyword_overlap_bonus = 0.25 if len(shared_features) >= 2 else 0.0

        sequence_ratio = difflib.SequenceMatcher(
            None,
            normalized_query,
            normalized_document,
        ).ratio()
        blended = max(
            sequence_ratio,
            min(1.0, coverage + 0.35 + keyword_overlap_bonus),
            (sequence_ratio + coverage) / 2,
        )
        return round(blended, 4)


def _extract_features(text: str) -> set[str]:
    features: set[str] = set()
    for token in _TOKEN_PATTERN.findall(text):
        normalized_token = token.strip().lower()
        if not normalized_token:
            continue
        features.add(normalized_token)
        if _contains_cjk(normalized_token):
            for size in (2, 3):
                if len(normalized_token) < size:
                    continue
                for index in range(len(normalized_token) - size + 1):
                    features.add(normalized_token[index : index + size])
    return features


def _contains_cjk(text: str) -> bool:
    return any("\u4e00" <= char <= "\u9fff" for char in text)


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()
