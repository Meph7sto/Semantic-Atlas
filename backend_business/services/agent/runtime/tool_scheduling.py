"""Execution metadata used to schedule agent tool calls safely."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ToolExecutionMetadata:
    """Resolved scheduling properties for one concrete tool invocation.

    ``resource_key`` identifies the object touched by the call. A missing key
    is treated as a group-wide resource for writes, which keeps undeclared or
    ambiguous side effects conservative.
    """

    read_only: bool = False
    idempotent: bool = False
    resource_key: str | None = None
    concurrency_group: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "read_only", bool(self.read_only))
        object.__setattr__(self, "idempotent", bool(self.idempotent))
        object.__setattr__(
            self,
            "resource_key",
            str(self.resource_key).strip() if self.resource_key else None,
        )
        object.__setattr__(
            self,
            "concurrency_group",
            str(self.concurrency_group).strip() if self.concurrency_group else None,
        )

    @classmethod
    def coerce(cls, value: Any) -> ToolExecutionMetadata:
        if isinstance(value, cls):
            return value
        if isinstance(value, Mapping):
            return cls(
                read_only=value.get("read_only", False),
                idempotent=value.get("idempotent", False),
                resource_key=value.get("resource_key"),
                concurrency_group=value.get("concurrency_group"),
            )
        return cls()
