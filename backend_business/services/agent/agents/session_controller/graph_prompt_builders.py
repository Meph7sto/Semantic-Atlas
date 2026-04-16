"""Prompt builders for SessionController graph-executor stages."""

from __future__ import annotations

import json
from typing import Any

from .prompt_builder import SessionControllerPromptBuilder


class SessionControllerDecisionGraphPromptBuilder:
    """Decision-stage prompt builder for the GraphExecutor migration path."""

    def __init__(self) -> None:
        self._base = SessionControllerPromptBuilder()

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        base_prompt = self._base.build_system_prompt(context=context)
        return (
            f"{base_prompt}\n\n"
            "你当前处于执行图中的“总控决策阶段”。\n"
            "和 classic 模式不同，本阶段结束时不要直接输出 JSON 文本作为 assistant 回复。\n"
            "当你确认本阶段已完成时，必须调用 complete_phase，并按以下规则填写参数：\n"
            "1. `conclusion` 必须是一个 JSON 对象字符串，字段协议与 Session Controller 结构化结果一致。\n"
            "2. 如果该 JSON 的 `should_suspend` 为 false，则把 `route_key` 设为 `reply`。\n"
            "3. 如果该 JSON 的 `should_suspend` 为 true，则不要填写 `route_key`，运行时会顺序进入挂起回复阶段。\n"
            "4. 不要输出 Markdown、代码块或额外解释；结束阶段只能通过 complete_phase。\n"
            "5. `context` 字段可选；如本轮已有可复用的中间上下文（例如 write_result、approval_result），可放入其中。"
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
                "请阅读 Scratchpad 中最近一次来自 `sg_controller_intake` 的结构化决策 JSON，"
                "生成一段直接发给用户的中文回复。\n"
                "如果 mode=clarify，优先复用 clarification_question。\n"
                "如果 mode=approval_pending，明确说明审批已发出且当前流程会挂起等待。\n"
                "完成后必须调用 complete_phase，并把用户可见回复文本写入 `conclusion`。"
            )
        else:
            instructions = (
                "你负责执行图中的“最终回复阶段”。\n"
                "请阅读 Scratchpad 中最近一次来自 `sg_controller_intake` 的结构化决策 JSON，"
                "生成一段面向用户的自然中文回复。\n"
                "优先保持 assistant_reply_seed 的事实与措辞；如它已足够自然，可直接复用或轻微润色。\n"
                "完成后必须调用 complete_phase，并把最终回复文本写入 `conclusion`。"
            )
        if scratchpad_text:
            return f"{instructions}\n\n{scratchpad_text}"
        return instructions

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
