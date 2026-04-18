"""Prompt builders for SessionController graph-executor stages."""

from __future__ import annotations

import json
from typing import Any

from backend_business.services.agent.agents.conflict_detection_agent.prompt_builder import (
    ConflictDetectionPromptBuilder,
)
from backend_business.services.agent.agents.requirement_agent.constants import (
    DEFAULT_PROMPT_PAYLOAD_FORMAT,
)
from backend_business.services.agent.agents.requirement_agent.prompt_builder import (
    RequirementAgentPromptBuilder,
)
from backend_business.services.agent.agents.requirement_classification_agent.prompt_builder import (
    RequirementClassificationPromptBuilder,
)

from .prompt_builder import SessionControllerPromptBuilder


def _append_extra_system_context(base_prompt: str, context: dict[str, Any]) -> str:
    extra_system_context = str(context.get("_extra_system_context") or "").strip()
    if not extra_system_context:
        return base_prompt
    return f"{base_prompt}\n\n{extra_system_context}"


class SessionControllerDecisionGraphPromptBuilder:
    """Decision-stage prompt builder for the GraphExecutor migration path."""

    def __init__(self) -> None:
        self._base = SessionControllerPromptBuilder()

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        base_prompt = self._base.build_system_prompt(context=context)
        return _append_extra_system_context(
            (
            f"{base_prompt}\n\n"
            "你当前处于执行图中的“总控决策阶段”。\n"
            "本阶段结束时不要直接输出 JSON 文本作为 assistant 回复。\n"
            "当你确认本阶段已完成时，必须调用 complete_phase，并按以下规则填写参数：\n"
            "1. `conclusion` 必须是一个 JSON 对象字符串，字段协议与 Session Controller 结构化结果一致。\n"
            "2. 如果你刚刚调用了 `invoke_requirement_agent` 并准备让运行时执行原生 invoke，"
            "把 `route_key` 设为 `invoke_requirement`。\n"
            "3. 如果你刚刚调用了 `invoke_conflict_detection` 并准备让运行时执行原生 invoke，"
            "把 `route_key` 设为 `invoke_conflict`。\n"
            "4. 如果你刚刚调用了 `invoke_requirement_classification_agent` 并准备让运行时执行原生 invoke，"
            "把 `route_key` 设为 `invoke_classification`。\n"
            "5. 如果该 JSON 的 `should_suspend` 为 true，则把 `route_key` 设为 `suspend`。\n"
            "6. 如果该 JSON 的 `should_suspend` 为 false 且不需要 invoke，则把 `route_key` 设为 `reply`。\n"
            "7. 不要输出 Markdown、代码块或额外解释；结束阶段只能通过 complete_phase。\n"
            "8. `context` 字段可选；如本轮已有可复用的中间上下文（例如 write_result、approval_result），可放入其中。"
            ),
            context,
        )

    def build_user_message(self, *, user_message: str, context: dict[str, Any]) -> str:
        return self._base.build_user_message(user_message=user_message, context=context)

    @staticmethod
    def build_round_input_summary(
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "round": round_index,
            "mode": "session_controller_decision",
            "project_id": context.get("project_id"),
            "message_count": len(messages),
        }


class SessionControllerReplyGraphPromptBuilder:
    """Reply-stage prompt builder for final-reply and suspend-reply stages."""

    def __init__(self, *, reply_kind: str) -> None:
        self._reply_kind = reply_kind

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        scratchpad_text = context.get("_scratchpad_prompt_text") or ""
        if self._reply_kind == "suspend":
            instructions = (
                "你负责执行图中的“挂起回复阶段”。\n"
                "请阅读 Scratchpad 中最近一次来自 Session Controller 决策/委托子图的结构化决策 JSON，"
                "生成一段直接发给用户的中文回复。\n"
                "如果 mode=clarify，优先复用 clarification_question。\n"
                "如果 mode=approval_pending，明确说明审批已发出且当前流程会挂起等待。\n"
                "完成后必须调用 complete_phase，并把用户可见回复文本写入 `conclusion`。"
            )
        else:
            instructions = (
                "你负责执行图中的“最终回复阶段”。\n"
                "请阅读 Scratchpad 中最近一次来自 Session Controller 决策/委托子图的结构化决策 JSON，"
                "生成一段面向用户的自然中文回复。\n"
                "优先保持 assistant_reply_seed 的事实与措辞；如它已足够自然，可直接复用或轻微润色。\n"
                "完成后必须调用 complete_phase，并把最终回复文本写入 `conclusion`。"
            )
        if scratchpad_text:
            instructions = f"{instructions}\n\n{scratchpad_text}"
        return _append_extra_system_context(instructions, context)

    def build_user_message(self, *, user_message: str, context: dict[str, Any]) -> str:
        return json.dumps(
            {
                "user_message": user_message,
                "reply_kind": self._reply_kind,
            },
            ensure_ascii=False,
        )

    @staticmethod
    def build_round_input_summary(
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "round": round_index,
            "mode": context.get("_current_subgraph"),
            "message_count": len(messages),
        }


class SessionControllerRequirementDelegatePromptBuilder:
    """Prompt builder for runtime-native requirement-agent delegation."""

    def __init__(self) -> None:
        self._base = RequirementAgentPromptBuilder()

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        base_context = dict(context)
        base_context.pop("_extra_system_context", None)
        base = self._base.build_tool_loop_system_prompt(context=base_context)
        scratchpad_text = context.get("_scratchpad_prompt_text") or ""
        if scratchpad_text:
            base += f"\n\n{scratchpad_text}"
        return _append_extra_system_context(base, context)

    def build_user_message(self, *, user_message: str, context: dict[str, Any]) -> str:
        return self._base.build_tool_loop_user_message(
            project_id=context["project_id"],
            user_message=user_message,
            requirement_id=context.get("selected_requirement_id"),
            historical_node_context=context.get("historical_node_context"),
            prompt_payload_format=context.get(
                "prompt_payload_format",
                DEFAULT_PROMPT_PAYLOAD_FORMAT,
            ),
        )

    def build_round_input_summary(
        self,
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._base.build_tool_loop_input_summary(
            round_index=round_index,
            messages=messages,
            context=context,
        )


class SessionControllerConflictDelegatePromptBuilder:
    """Prompt builder for runtime-native conflict-detection delegation."""

    def __init__(self) -> None:
        self._base = ConflictDetectionPromptBuilder()

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        base_context = dict(context)
        base_context.pop("_extra_system_context", None)
        base = self._base.build_system_prompt(context=base_context)
        scratchpad_text = context.get("_scratchpad_prompt_text") or ""
        if scratchpad_text:
            base = f"{base}\n\n{scratchpad_text}"
        return _append_extra_system_context(base, context)

    def build_user_message(self, *, user_message: str, context: dict[str, Any]) -> str:
        return self._base.build_user_message(user_message=user_message, context=context)

    def build_round_input_summary(
        self,
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._base.build_round_input_summary(
            round_index=round_index,
            messages=messages,
            context=context,
        )


class SessionControllerClassificationDelegatePromptBuilder:
    """Prompt builder for runtime-native requirement-classification delegation."""

    def __init__(self) -> None:
        self._base = RequirementClassificationPromptBuilder()

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        base_context = dict(context)
        base_context.pop("_extra_system_context", None)
        base = self._base.build_system_prompt(context=base_context)
        scratchpad_text = context.get("_scratchpad_prompt_text") or ""
        if scratchpad_text:
            base = f"{base}\n\n{scratchpad_text}"
        return _append_extra_system_context(base, context)

    def build_user_message(self, *, user_message: str, context: dict[str, Any]) -> str:
        return self._base.build_user_message(user_message=user_message, context=context)

    def build_round_input_summary(
        self,
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._base.build_round_input_summary(
            round_index=round_index,
            messages=messages,
            context=context,
        )
