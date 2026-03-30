"""Prompt interfaces for generic tool-loop execution."""

from __future__ import annotations

from typing import Any, Protocol


class PromptBuilderProtocol(Protocol):
    """Build prompts and stage summaries for a generic tool loop."""

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        ...

    def build_user_message(self, *, user_message: str, context: dict[str, Any]) -> str:
        ...

    def build_round_input_summary(
        self,
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        ...

