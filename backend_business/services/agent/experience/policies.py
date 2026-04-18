"""Target-specific policy resolution for experience skill runtime behavior."""

from __future__ import annotations

from dataclasses import dataclass, replace

from backend_business.config import settings

from .targets import ExperienceTarget


@dataclass(frozen=True, slots=True)
class ExperiencePolicy:
    """Resolved behavior flags and thresholds for a single experience target."""

    experience_target: str
    enabled: bool = True
    enable_injection: bool = True
    enable_writeback: bool = True
    retrieval_threshold: float = 0.7
    min_tool_calls: int = 2
    miss_threshold: float = 0.4
    min_miss_sample: int = 5
    allow_shared_patterns: bool = False
    compiler_mode: str = "default"


class ExperiencePolicyResolver:
    """Resolve policy defaults for individual targets."""

    def __init__(
        self,
        *,
        target_overrides: dict[str, ExperiencePolicy] | None = None,
    ) -> None:
        self._target_overrides = dict(target_overrides or {})

    def resolve(
        self,
        target: ExperienceTarget | str | None,
    ) -> ExperiencePolicy:
        target_id = _resolve_target_id(target)
        if not target_id:
            return self._base_policy("unknown", enabled=False)
        override = self._target_overrides.get(target_id)
        if override is not None:
            return override
        return self._build_default_policy(target_id)

    def _build_default_policy(self, target_id: str) -> ExperiencePolicy:
        policy = self._base_policy(target_id)
        if target_id == "shared_patterns":
            return replace(
                policy,
                enable_injection=settings.AGENT_EXPERIENCE_ENABLE_SHARED_PATTERNS,
                enable_writeback=settings.AGENT_EXPERIENCE_ENABLE_SHARED_PATTERNS,
                retrieval_threshold=min(policy.retrieval_threshold, 0.58),
                allow_shared_patterns=False,
                compiler_mode="shared_patterns",
            )
        if target_id == "session_controller_decision":
            return replace(
                policy,
                retrieval_threshold=max(policy.retrieval_threshold, 0.82),
                min_tool_calls=max(policy.min_tool_calls, 2),
                allow_shared_patterns=False,
                compiler_mode="decision",
            )
        if target_id.startswith("session_controller_") and target_id.endswith("_delegate"):
            return replace(
                policy,
                retrieval_threshold=max(0.68, policy.retrieval_threshold),
                min_tool_calls=max(1, policy.min_tool_calls),
                allow_shared_patterns=True,
                compiler_mode="delegate",
            )
        if target_id.endswith("_classic"):
            return replace(
                policy,
                retrieval_threshold=min(policy.retrieval_threshold, 0.66),
                min_tool_calls=max(1, policy.min_tool_calls),
                allow_shared_patterns=True,
                compiler_mode="classic",
            )
        return policy

    @staticmethod
    def _base_policy(target_id: str, *, enabled: bool = True) -> ExperiencePolicy:
        return ExperiencePolicy(
            experience_target=target_id,
            enabled=enabled,
            enable_injection=True,
            enable_writeback=True,
            retrieval_threshold=float(settings.AGENT_EXPERIENCE_RETRIEVAL_THRESHOLD),
            min_tool_calls=max(0, int(settings.AGENT_EXPERIENCE_MIN_TOOL_CALLS)),
            miss_threshold=float(settings.AGENT_EXPERIENCE_MISS_THRESHOLD),
            min_miss_sample=max(1, int(settings.AGENT_EXPERIENCE_MIN_MISS_SAMPLE)),
            allow_shared_patterns=bool(settings.AGENT_EXPERIENCE_ENABLE_SHARED_PATTERNS),
            compiler_mode="default",
        )


def _resolve_target_id(target: ExperienceTarget | str | None) -> str:
    if isinstance(target, ExperienceTarget):
        return str(target.target_id or "").strip()
    return str(target or "").strip()
