"""Bounded, relevance-aware prompt compilation for Scratchpad history."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

_CJK_SEGMENT_RE = re.compile(r"[\u3400-\u9fff]+")
_LATIN_TERM_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", re.IGNORECASE)
_TASK_STOP_TERMS = {
    "agent",
    "current",
    "result",
    "stage",
    "task",
    "the",
    "user",
    "任务",
    "处理",
    "当前",
    "用户",
    "结果",
    "进行",
    "阶段",
    "需求",
}
_DEFAULT_IMPORTANCE = {
    "note": 0.65,
    "tool_excerpt": 0.55,
    "stage_output": 0.8,
}


def estimate_prompt_tokens(text: str) -> int:
    """Return a deterministic token estimate suitable for enforcing a budget.

    Exact token counts are model-specific. CJK characters are conservatively
    counted one-for-one while other text is estimated at four characters per
    token. The same estimator is used for selection and observability.
    """

    if not text:
        return 0
    cjk_count = sum(1 for character in text if "\u3400" <= character <= "\u9fff")
    non_cjk_count = len(text) - cjk_count
    return cjk_count + math.ceil(non_cjk_count / 4)


def compact_memory_content(content: Any, *, max_tokens: int) -> str:
    """Render a bounded content excerpt for cross-round memory transfer."""

    return _truncate_to_tokens(_stringify_content(content), max_tokens)


@dataclass(frozen=True)
class PromptMemoryPolicy:
    """Limits and ranking weights for Scratchpad prompt memory."""

    max_tokens: int = 1200
    max_entries: int = 12
    max_entry_tokens: int = 240
    summary_tokens: int = 180
    minimum_task_relevance: float = 0.05
    always_include_importance: float = 0.95
    recent_important_entries: int = 2
    recent_stage_outputs: int = 2
    task_weight: float = 0.45
    importance_weight: float = 0.35
    recency_weight: float = 0.2

    def __post_init__(self) -> None:
        if self.max_tokens < 64:
            raise ValueError("max_tokens must be at least 64")
        if self.max_entries < 1:
            raise ValueError("max_entries must be positive")
        if self.max_entry_tokens < 8:
            raise ValueError("max_entry_tokens must be at least 8")
        if self.summary_tokens < 0:
            raise ValueError("summary_tokens cannot be negative")
        if not 0 <= self.minimum_task_relevance <= 1:
            raise ValueError("minimum_task_relevance must be between 0 and 1")
        if not 0 <= self.always_include_importance <= 1:
            raise ValueError("always_include_importance must be between 0 and 1")
        if self.recent_important_entries < 0:
            raise ValueError("recent_important_entries cannot be negative")
        if self.recent_stage_outputs < 0:
            raise ValueError("recent_stage_outputs cannot be negative")
        if any(
            weight < 0 or weight > 1
            for weight in (
                self.task_weight,
                self.importance_weight,
                self.recency_weight,
            )
        ):
            raise ValueError("memory ranking weights must be between 0 and 1")
        total_weight = self.task_weight + self.importance_weight + self.recency_weight
        if not math.isclose(total_weight, 1.0, abs_tol=1e-6):
            raise ValueError("memory ranking weights must sum to 1")


@dataclass(frozen=True)
class MemoryCompilation:
    """Compiled prompt text plus auditable selection telemetry."""

    text: str
    container_key: str | None
    task_fingerprint: str | None
    observation_key: str | None
    raw_entry_count: int
    eligible_entry_count: int
    selected_entry_ids: tuple[str, ...]
    omitted_entry_count: int
    task_filtered_entry_count: int
    estimated_tokens: int
    max_tokens: int
    max_entries: int
    raw_history_digest: str
    compiled_at: str

    @property
    def selected_entry_count(self) -> int:
        return len(self.selected_entry_ids)

    @property
    def was_distilled(self) -> bool:
        return self.omitted_entry_count > 0

    def to_metrics(self) -> dict[str, Any]:
        return {
            "container_key": self.container_key,
            "task_fingerprint": self.task_fingerprint,
            "observation_key": self.observation_key,
            "raw_entry_count": self.raw_entry_count,
            "eligible_entry_count": self.eligible_entry_count,
            "selected_entry_count": self.selected_entry_count,
            "selected_entry_ids": list(self.selected_entry_ids),
            "omitted_entry_count": self.omitted_entry_count,
            "task_filtered_entry_count": self.task_filtered_entry_count,
            "estimated_tokens": self.estimated_tokens,
            "max_tokens": self.max_tokens,
            "max_entries": self.max_entries,
            "was_distilled": self.was_distilled,
            "raw_history_digest": self.raw_history_digest,
            "compiled_at": self.compiled_at,
        }


@dataclass(frozen=True)
class _RankedEntry:
    index: int
    entry: Any
    score: float
    task_relevance: float


class ScratchpadMemoryCompiler:
    """Select and distill raw Scratchpad entries without mutating history."""

    def __init__(self, policy: PromptMemoryPolicy | None = None) -> None:
        self.policy = policy or PromptMemoryPolicy()

    def compile(
        self,
        entries: Sequence[Any],
        *,
        container_key: str | None,
        task: str | None = None,
        observation_key: str | None = None,
        include_flow_context: bool = True,
    ) -> MemoryCompilation:
        raw_entries = list(entries)
        raw_digest = _history_digest(raw_entries)
        task_text = str(task or "").strip()
        task_terms = _extract_terms(task_text)
        task_fingerprint = (
            hashlib.sha256(task_text.encode("utf-8")).hexdigest()[:16] if task_text else None
        )
        compiled_at = datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")
        if not raw_entries:
            return MemoryCompilation(
                text="",
                container_key=container_key,
                task_fingerprint=task_fingerprint,
                observation_key=observation_key,
                raw_entry_count=0,
                eligible_entry_count=0,
                selected_entry_ids=(),
                omitted_entry_count=0,
                task_filtered_entry_count=0,
                estimated_tokens=0,
                max_tokens=self.policy.max_tokens,
                max_entries=self.policy.max_entries,
                raw_history_digest=raw_digest,
                compiled_at=compiled_at,
            )

        ranked_entries = self._rank(raw_entries, task_terms=task_terms)
        recent_flow_stage_output_ids = {
            _entry_id(entry)
            for entry in _latest_entries_of_type(
                [
                    entry
                    for entry in raw_entries
                    if _is_globally_scoped(entry)
                    or (include_flow_context and _is_flow_scoped(entry))
                ],
                entry_type="stage_output",
                limit=self.policy.recent_stage_outputs,
            )
        }
        recent_global_important_entry_ids = {
            _entry_id(entry)
            for entry in _latest_entries_matching(
                raw_entries,
                predicate=lambda entry: (
                    _is_globally_scoped(entry)
                    and _entry_importance(entry) >= self.policy.always_include_importance
                ),
                limit=self.policy.recent_important_entries,
            )
        }
        eligible_entries = [
            ranked
            for ranked in ranked_entries
            if not task_terms
            or ranked.task_relevance >= self.policy.minimum_task_relevance
            or _entry_id(ranked.entry) in recent_global_important_entry_ids
            or _entry_id(ranked.entry) in recent_flow_stage_output_ids
        ]
        task_filtered_count = len(raw_entries) - len(eligible_entries)
        selected = self._select(eligible_entries)
        text, selected = self._render(
            raw_entries=raw_entries,
            eligible_entries=eligible_entries,
            selected=selected,
            task_filtered_count=task_filtered_count,
            raw_digest=raw_digest,
        )
        selected_ids = tuple(_entry_id(item.entry) for item in selected)
        estimated_tokens = estimate_prompt_tokens(text)
        return MemoryCompilation(
            text=text,
            container_key=container_key,
            task_fingerprint=task_fingerprint,
            observation_key=observation_key,
            raw_entry_count=len(raw_entries),
            eligible_entry_count=len(eligible_entries),
            selected_entry_ids=selected_ids,
            omitted_entry_count=len(raw_entries) - len(selected),
            task_filtered_entry_count=task_filtered_count,
            estimated_tokens=estimated_tokens,
            max_tokens=self.policy.max_tokens,
            max_entries=self.policy.max_entries,
            raw_history_digest=raw_digest,
            compiled_at=compiled_at,
        )

    def _rank(
        self,
        entries: Sequence[Any],
        *,
        task_terms: set[str],
    ) -> list[_RankedEntry]:
        entry_count = max(1, len(entries))
        ranked: list[_RankedEntry] = []
        for index, entry in enumerate(entries):
            entry_terms = _entry_terms(entry)
            task_relevance = _task_relevance(task_terms, entry_terms)
            recency = (index + 1) / entry_count
            importance = _entry_importance(entry)
            score = (
                task_relevance * self.policy.task_weight
                + importance * self.policy.importance_weight
                + recency * self.policy.recency_weight
            )
            ranked.append(
                _RankedEntry(
                    index=index,
                    entry=entry,
                    score=score,
                    task_relevance=task_relevance,
                )
            )
        ranked.sort(key=lambda item: (-item.score, -item.index, _entry_id(item.entry)))
        return ranked

    def _select(self, eligible_entries: Sequence[_RankedEntry]) -> list[_RankedEntry]:
        summary_reserve = min(
            self.policy.summary_tokens,
            self.policy.max_tokens // 4,
        )
        header_reserve = min(120, self.policy.max_tokens // 4)
        detail_budget = max(8, self.policy.max_tokens - summary_reserve - header_reserve)
        selected: list[_RankedEntry] = []
        used_tokens = 0
        for ranked in eligible_entries:
            if len(selected) >= self.policy.max_entries:
                break
            line = _format_entry_line(
                ranked.entry,
                max_tokens=self.policy.max_entry_tokens,
            )
            line_tokens = estimate_prompt_tokens(line) + 1
            if used_tokens + line_tokens > detail_budget:
                continue
            selected.append(ranked)
            used_tokens += line_tokens
        return selected

    def _render(
        self,
        *,
        raw_entries: Sequence[Any],
        eligible_entries: Sequence[_RankedEntry],
        selected: list[_RankedEntry],
        task_filtered_count: int,
        raw_digest: str,
    ) -> tuple[str, list[_RankedEntry]]:
        selected = list(selected)
        while True:
            selected_ids = {_entry_id(item.entry) for item in selected}
            omitted_relevant = [
                item for item in eligible_entries if _entry_id(item.entry) not in selected_ids
            ]
            ordered_selected = sorted(selected, key=lambda item: item.index)
            detail_lines = [
                _format_entry_line(
                    item.entry,
                    max_tokens=self.policy.max_entry_tokens,
                )
                for item in ordered_selected
            ]
            omitted_count = len(raw_entries) - len(selected)
            header = _format_header(
                selected_count=len(selected),
                raw_count=len(raw_entries),
                omitted_count=omitted_count,
                estimated_tokens=0,
                max_tokens=self.policy.max_tokens,
            )
            base_parts = [header, *detail_lines]
            base_text = "\n".join(base_parts)
            remaining_tokens = self.policy.max_tokens - estimate_prompt_tokens(base_text) - 1
            summary = ""
            if omitted_count and remaining_tokens > 0:
                summary = _build_distilled_summary(
                    omitted_relevant=omitted_relevant,
                    task_filtered_count=task_filtered_count,
                    raw_digest=raw_digest,
                    max_tokens=min(self.policy.summary_tokens, remaining_tokens),
                )
            body_parts = [*detail_lines, *([summary] if summary else [])]
            estimated_tokens = 0
            text = ""
            for _ in range(4):
                header = _format_header(
                    selected_count=len(selected),
                    raw_count=len(raw_entries),
                    omitted_count=omitted_count,
                    estimated_tokens=estimated_tokens,
                    max_tokens=self.policy.max_tokens,
                )
                text = "\n".join([header, *body_parts])
                updated_estimate = estimate_prompt_tokens(text)
                if updated_estimate == estimated_tokens:
                    break
                estimated_tokens = updated_estimate
            if estimate_prompt_tokens(text) <= self.policy.max_tokens:
                return text, ordered_selected
            if selected:
                selected.pop()
                continue
            return _truncate_to_tokens(text, self.policy.max_tokens), []


def _format_header(
    *,
    selected_count: int,
    raw_count: int,
    omitted_count: int,
    estimated_tokens: int,
    max_tokens: int,
) -> str:
    return (
        "[Scratchpad - 跨阶段工作记忆 | "
        f"selected={selected_count}/{raw_count} | "
        f"estimated_tokens={estimated_tokens}/{max_tokens} | "
        f"distilled={omitted_count}]"
    )


def _build_distilled_summary(
    *,
    omitted_relevant: Sequence[_RankedEntry],
    task_filtered_count: int,
    raw_digest: str,
    max_tokens: int,
) -> str:
    if max_tokens <= 0:
        return ""
    type_counts = Counter(
        str(getattr(item.entry, "entry_type", "note")) for item in omitted_relevant
    )
    counts = ",".join(f"{key}:{value}" for key, value in sorted(type_counts.items()))
    hints: list[str] = []
    for item in omitted_relevant[:3]:
        content = _stringify_content(getattr(item.entry, "content", ""))
        compact_content = _truncate_to_tokens(content, 32)
        hints.append(f"{_entry_id(item.entry)[:8]}={compact_content}")
    parts = [
        "[Distilled history]",
        f"relevant_omitted={len(omitted_relevant)}",
        f"task_filtered={task_filtered_count}",
    ]
    if counts:
        parts.append(f"types={counts}")
    if hints:
        parts.append("hints=" + " | ".join(hints))
    parts.append(f"raw_trace=sha256:{raw_digest}")
    return _truncate_to_tokens("; ".join(parts), max_tokens)


def _format_entry_line(entry: Any, *, max_tokens: int) -> str:
    entry_type = str(getattr(entry, "entry_type", "note")).upper()
    source_subgraph = str(getattr(entry, "source_subgraph", "") or "").strip()
    source = f" (from: {source_subgraph})" if source_subgraph else ""
    importance = _entry_importance(entry)
    prefix = (
        f"  [id={_entry_id(entry)[:12]}] [{entry_type}]{source} [importance={importance:.2f}]: "
    )
    content_budget = max(1, max_tokens - estimate_prompt_tokens(prefix))
    content = _truncate_to_tokens(
        _stringify_content(getattr(entry, "content", "")),
        content_budget,
    )
    return prefix + content


def _entry_id(entry: Any) -> str:
    value = str(getattr(entry, "entry_id", "") or "").strip()
    if value:
        return value
    payload = json.dumps(
        {
            "entry_type": getattr(entry, "entry_type", None),
            "content": getattr(entry, "content", None),
            "source_subgraph": getattr(entry, "source_subgraph", None),
            "created_at": getattr(entry, "created_at", None),
        },
        ensure_ascii=False,
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:32]


def _entry_importance(entry: Any) -> float:
    raw_importance = getattr(entry, "importance", None)
    if raw_importance is None:
        raw_importance = _DEFAULT_IMPORTANCE.get(
            str(getattr(entry, "entry_type", "note")),
            0.5,
        )
    try:
        return min(1.0, max(0.0, float(raw_importance)))
    except (TypeError, ValueError):
        return 0.5


def _entry_terms(entry: Any) -> set[str]:
    content = _stringify_content(getattr(entry, "content", ""))
    source = str(getattr(entry, "source_subgraph", "") or "")
    task_refs = getattr(entry, "task_refs", ()) or ()
    task_ref_text = " ".join(str(item) for item in task_refs)
    return _extract_terms(f"{source}\n{task_ref_text}\n{content}")


def _is_globally_scoped(entry: Any) -> bool:
    task_refs = {
        str(item).strip().lower()
        for item in (getattr(entry, "task_refs", ()) or ())
        if str(item).strip()
    }
    return bool(task_refs & {"*", "global", "global-invariant"})


def _is_flow_scoped(entry: Any) -> bool:
    task_refs = {
        str(item).strip().lower()
        for item in (getattr(entry, "task_refs", ()) or ())
        if str(item).strip()
    }
    return "flow-context" in task_refs


def _task_relevance(task_terms: set[str], entry_terms: set[str]) -> float:
    if not task_terms:
        return 0.5
    if not entry_terms:
        return 0.0
    overlap = task_terms & entry_terms
    if not overlap:
        return 0.0
    return min(1.0, len(overlap) / max(1, len(task_terms)))


def _extract_terms(value: str) -> set[str]:
    normalized = str(value or "").lower()
    terms = set(_LATIN_TERM_RE.findall(normalized))
    for segment in _CJK_SEGMENT_RE.findall(normalized):
        if len(segment) == 1:
            terms.add(segment)
            continue
        terms.update(segment[index : index + 2] for index in range(len(segment) - 1))
    return {term for term in terms if len(term) > 1 and term not in _TASK_STOP_TERMS}


def _stringify_content(content: Any) -> str:
    if isinstance(content, (dict, list, tuple)):
        return json.dumps(
            content,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
            default=str,
        )
    return str(content)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    if max_tokens <= 0:
        return ""
    if estimate_prompt_tokens(text) <= max_tokens:
        return text
    suffix = "..."
    suffix_tokens = estimate_prompt_tokens(suffix)
    if max_tokens <= suffix_tokens:
        return suffix[:max_tokens]
    low = 0
    high = len(text)
    while low < high:
        midpoint = (low + high + 1) // 2
        candidate = text[:midpoint].rstrip() + suffix
        if estimate_prompt_tokens(candidate) <= max_tokens:
            low = midpoint
        else:
            high = midpoint - 1
    return text[:low].rstrip() + suffix


def _history_digest(entries: Iterable[Any]) -> str:
    digest = hashlib.sha256()
    for entry in entries:
        payload = json.dumps(
            {
                "entry_id": _entry_id(entry),
                "entry_type": getattr(entry, "entry_type", None),
                "content": getattr(entry, "content", None),
                "source_subgraph": getattr(entry, "source_subgraph", None),
                "container_key": getattr(entry, "container_key", None),
                "readonly": getattr(entry, "readonly", None),
                "created_at": getattr(entry, "created_at", None),
                "importance": _entry_importance(entry),
                "task_refs": list(getattr(entry, "task_refs", ()) or ()),
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        digest.update(payload.encode("utf-8"))
        digest.update(b"\n")
    return digest.hexdigest()


def _latest_entries_of_type(
    entries: Sequence[Any],
    *,
    entry_type: str,
    limit: int,
) -> list[Any]:
    return _latest_entries_matching(
        entries,
        predicate=lambda entry: str(getattr(entry, "entry_type", "")) == entry_type,
        limit=limit,
    )


def _latest_entries_matching(
    entries: Sequence[Any],
    *,
    predicate: Callable[[Any], bool],
    limit: int,
) -> list[Any]:
    if limit <= 0:
        return []
    matches: list[Any] = []
    for entry in reversed(entries):
        if not predicate(entry):
            continue
        matches.append(entry)
        if len(matches) >= limit:
            break
    return matches
