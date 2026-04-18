"""Registry helpers for tracking current experience skills."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from backend_business.config import settings

try:
    import yaml
except ImportError:  # pragma: no cover - fallback kept for minimal envs
    yaml = None


class SkillRegistry:
    """Read/write helper for `.agent_skills/_registry.yaml`."""

    REGISTRY_FILENAME = "_registry.yaml"

    def __init__(self, root_path: str | Path | None = None) -> None:
        self.root_path = Path(root_path or settings.AGENT_EXPERIENCE_ROOT)

    @property
    def registry_path(self) -> Path:
        return self.root_path / self.REGISTRY_FILENAME

    def initialize(self) -> dict[str, Any]:
        self.root_path.mkdir(parents=True, exist_ok=True)
        if not self.registry_path.exists():
            payload = self._default_payload()
            self.save(payload)
            return payload
        return self.load()

    def load(self) -> dict[str, Any]:
        if not self.registry_path.exists():
            return self._default_payload()

        raw_text = self.registry_path.read_text(encoding="utf-8").strip()
        if not raw_text:
            return self._default_payload()

        parsed = self._deserialize(raw_text)
        if not isinstance(parsed, dict):
            return self._default_payload()
        targets = parsed.get("targets")
        if not isinstance(targets, dict):
            parsed["targets"] = {}
        parsed.setdefault("version", 1)
        return parsed

    def save(self, payload: dict[str, Any]) -> Path:
        self.root_path.mkdir(parents=True, exist_ok=True)
        serialized = self._serialize(payload)
        self.registry_path.write_text(serialized, encoding="utf-8")
        return self.registry_path

    def get_target(self, target_id: str) -> dict[str, Any] | None:
        entry = self.load().get("targets", {}).get(target_id)
        if isinstance(entry, dict):
            return dict(entry)
        return None

    def upsert_target(
        self,
        target_id: str,
        *,
        skill_id: str | None = None,
        current_skill_path: str | None = None,
        iteration: int | None = None,
        updated_at: datetime | None = None,
    ) -> dict[str, Any]:
        payload = self.load()
        targets = payload.setdefault("targets", {})
        entry = self._normalize_entry(targets.get(target_id) or {})

        if skill_id is not None:
            entry["skill_id"] = skill_id
        if current_skill_path is not None:
            entry["current_skill_path"] = current_skill_path
        if iteration is not None:
            entry["iteration"] = int(iteration)
        if updated_at is not None:
            normalized_updated_at = _isoformat_utc(updated_at)
            entry.setdefault("created_at", normalized_updated_at)
            entry["last_updated_at"] = normalized_updated_at

        targets[target_id] = entry
        self.save(payload)
        return dict(entry)

    def record_injection_result(
        self,
        target_id: str,
        *,
        missed: bool,
        used_at: datetime | None = None,
        miss_threshold: float | None = None,
        min_miss_sample: int | None = None,
    ) -> dict[str, Any]:
        payload = self.load()
        targets = payload.setdefault("targets", {})
        entry = self._normalize_entry(targets.get(target_id) or {})
        entry["invocation_count"] = int(entry.get("invocation_count", 0)) + 1
        entry["injection_miss_count"] = int(
            entry.get("injection_miss_count", 0)
        ) + int(bool(missed))
        entry["skill_hit_count"] = max(
            0,
            int(entry["invocation_count"]) - int(entry["injection_miss_count"]),
        )
        entry["miss_ratio"] = _round_ratio(
            int(entry["injection_miss_count"]),
            int(entry["invocation_count"]),
        )
        if used_at is not None:
            entry["last_used_at"] = _isoformat_utc(used_at)
        effective_miss_threshold = float(
            miss_threshold
            if miss_threshold is not None
            else settings.AGENT_EXPERIENCE_MISS_THRESHOLD
        )
        effective_min_sample = max(
            1,
            int(
                min_miss_sample
                if min_miss_sample is not None
                else settings.AGENT_EXPERIENCE_MIN_MISS_SAMPLE
            ),
        )
        should_refine = (
            int(entry["invocation_count"]) >= effective_min_sample
            and float(entry["miss_ratio"]) >= effective_miss_threshold
        )
        entry["needs_refinement"] = bool(should_refine)
        if should_refine:
            entry["degraded"] = True
            entry["degraded_reason"] = "high_miss_ratio"
        elif not bool(entry.get("requires_manual_review")):
            entry["degraded"] = False
            entry["degraded_reason"] = ""
        targets[target_id] = entry
        self.save(payload)
        return dict(entry)

    def record_writeback_result(
        self,
        target_id: str,
        *,
        status: str,
        reason: str | None = None,
        at: datetime | None = None,
    ) -> dict[str, Any]:
        payload = self.load()
        targets = payload.setdefault("targets", {})
        entry = self._normalize_entry(targets.get(target_id) or {})
        normalized_status = str(status or "").strip()
        if normalized_status == "written":
            entry["rewrite_count"] = int(entry.get("rewrite_count", 0)) + 1
            entry["needs_refinement"] = False
            if not bool(entry.get("requires_manual_review")):
                entry["degraded"] = False
                entry["degraded_reason"] = ""
            if at is not None:
                entry["last_rewrite_at"] = _isoformat_utc(at)
        elif normalized_status == "skipped_review":
            entry["review_fail_count"] = int(entry.get("review_fail_count", 0)) + 1
            if int(entry["review_fail_count"]) >= 2:
                entry["requires_manual_review"] = True
        elif normalized_status == "skipped_sanitizer":
            entry["sanitizer_fail_count"] = int(
                entry.get("sanitizer_fail_count", 0)
            ) + 1
            if int(entry["sanitizer_fail_count"]) >= 2:
                entry["requires_manual_review"] = True
        elif normalized_status in {"skipped", "dry_run"}:
            entry["writeback_skip_count"] = int(
                entry.get("writeback_skip_count", 0)
            ) + 1
        elif normalized_status == "rolled_back":
            entry["rollback_count"] = int(entry.get("rollback_count", 0)) + 1
            if at is not None:
                entry["last_rollback_at"] = _isoformat_utc(at)
            entry["needs_refinement"] = False
            entry["requires_manual_review"] = False
            entry["degraded"] = False
            entry["degraded_reason"] = ""
        if reason is not None:
            entry["last_writeback_reason"] = str(reason)
        if at is not None:
            entry["last_observed_at"] = _isoformat_utc(at)
        targets[target_id] = entry
        self.save(payload)
        return dict(entry)

    @staticmethod
    def _normalize_entry(raw_entry: dict[str, Any]) -> dict[str, Any]:
        entry = dict(raw_entry or {})
        entry.setdefault("invocation_count", 0)
        entry.setdefault("injection_miss_count", 0)
        entry.setdefault("skill_hit_count", 0)
        entry.setdefault("miss_ratio", 0.0)
        entry.setdefault("rewrite_count", 0)
        entry.setdefault("review_fail_count", 0)
        entry.setdefault("sanitizer_fail_count", 0)
        entry.setdefault("writeback_skip_count", 0)
        entry.setdefault("rollback_count", 0)
        entry.setdefault("needs_refinement", False)
        entry.setdefault("requires_manual_review", False)
        entry.setdefault("degraded", False)
        entry.setdefault("degraded_reason", "")
        return entry

    @staticmethod
    def _default_payload() -> dict[str, Any]:
        return {
            "version": 1,
            "targets": {},
        }

    @staticmethod
    def _serialize(payload: dict[str, Any]) -> str:
        if yaml is not None:
            return yaml.safe_dump(
                payload,
                allow_unicode=True,
                sort_keys=True,
            )
        return json.dumps(payload, ensure_ascii=False, indent=2)

    @staticmethod
    def _deserialize(raw_text: str) -> dict[str, Any]:
        if yaml is not None:
            return yaml.safe_load(raw_text) or {}
        return json.loads(raw_text)


def _isoformat_utc(value: datetime) -> str:
    timestamp = value
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    else:
        timestamp = timestamp.astimezone(timezone.utc)
    return timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")


def _round_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(float(numerator) / float(denominator), 4)
