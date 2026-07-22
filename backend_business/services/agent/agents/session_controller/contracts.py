"""Contracts for session controller tool-loop decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any


class SessionControllerDecisionMode(str, Enum):
    DIRECT_REPLY = "direct_reply"
    CLARIFY = "clarify"
    BROWSE = "browse"
    DELEGATE_REQUIREMENT = "delegate_requirement"
    DELEGATE_CONFLICT = "delegate_conflict"
    DELEGATE_CLASSIFICATION = "delegate_classification"
    DELEGATE_TRACEABILITY = "delegate_traceability"
    APPROVAL_PENDING = "approval_pending"
    ERROR = "error"

    @classmethod
    def _missing_(cls, value: object):
        normalized = str(value or "").strip()
        if not normalized.startswith("delegate_"):
            return None
        member = str.__new__(cls, normalized)
        member._name_ = normalized.upper()
        member._value_ = normalized
        cls._value2member_map_[normalized] = member
        return member


class SuspendReason(str, Enum):
    CLARIFICATION = "clarification"
    APPROVAL_PENDING = "approval_pending"
    EXTERNAL_WAIT = "external_wait"


@dataclass(slots=True)
class SessionControllerLoopResult:
    mode: SessionControllerDecisionMode
    tool_loop_reply: str = ""
    assistant_reply_seed: str | None = None
    clarification_question: str | None = None
    delegated_agent: str | None = None
    resolved_requirement_id: str | None = None
    dispatched_agents: list[str] = field(default_factory=list)
    approval_pending: bool = False
    approval_result: dict[str, Any] | None = None
    should_suspend: bool = False
    suspend_reason: SuspendReason | None = None
    context: dict[str, Any] = field(default_factory=dict)
    rounds: int = 0
    phase_completed: bool = False
    route_key: str | None = None
    conclusion: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        payload["suspend_reason"] = (
            self.suspend_reason.value if self.suspend_reason is not None else None
        )
        return payload
