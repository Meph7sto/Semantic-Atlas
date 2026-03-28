"""Prompt construction helpers for requirement classification agent."""

from __future__ import annotations

import json
from typing import Any


class RequirementClassificationPromptBuilder:
    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        return (
            "你是需求分类 Agent。你运行在当前单个项目内，只能使用提供的工具读取需求并完成分类。"
            "你的职责仅限于：定位需求、执行分类、解释分类结果。"
            "不得修改需求，不得编造需求内容，不得跳过工具直接猜测需求细节。"
            "当目标需求不明确时，必须先使用 list/search/get 工具定位。"
            "当工具已经足够回答时，输出简洁中文，不要输出 JSON。"
        )

    def build_user_message(self, *, user_message: str, context: dict[str, Any]) -> str:
        payload = {
            "project_id": context.get("project_id"),
            "selected_requirement_id": context.get("selected_requirement_id"),
            "user_message": user_message,
        }
        return json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def build_round_input_summary(
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "round": round_index,
            "message_count": len(messages),
            "project_id": context.get("project_id"),
            "selected_requirement_id": context.get("selected_requirement_id"),
            "resolved_requirement_id": context.get("resolved_requirement_id"),
        }

    def build_final_reply_prompt(
        self,
        *,
        user_message: str,
        tool_loop_reply: str,
        mode: str,
        context: dict[str, Any],
    ) -> tuple[str, str]:
        system_prompt = (
            "你是面向需求工程用户的中文助手。"
            "请基于给定的分类结果生成自然、简洁、直接的最终回复。"
            "如果还不能确定目标需求，就只提出最小必要澄清问题。"
            "不要输出 JSON。"
        )
        payload = {
            "user_message": user_message,
            "mode": mode,
            "tool_loop_reply": tool_loop_reply,
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            "classification_result": context.get("classification_result"),
        }
        return system_prompt, json.dumps(payload, ensure_ascii=False)

    @staticmethod
    def normalize_mode(context: dict[str, Any]) -> str:
        if context.get("classification_result"):
            return "classification"
        return "clarification"
