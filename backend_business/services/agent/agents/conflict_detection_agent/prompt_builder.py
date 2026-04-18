"""Prompt construction helpers for conflict detection agent."""

from __future__ import annotations

import json
from typing import Any


class ConflictDetectionPromptBuilder:
    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        prompt = (
            "你是需求冲突检测 Agent。你运行在当前单个项目内，只能使用提供的工具来读取需求和检测冲突。"
            "你的唯一职责是判断用户指定的需求之间是否存在冲突。"
            "工作流程："
            "1. 如果用户没有指定明确的需求 ID，先使用 list_requirements 工具查看项目中的需求列表。"
            "2. 使用 get_requirement_detail 工具获取需要检测的需求的完整内容。"
            "3. 使用 check_conflict 工具检测两条需求之间是否存在冲突。"
            "4. 基于工具返回的结果，给出简洁的中文结论：是否冲突，以及冲突的具体原因。"
            "必须依赖工具结果，不得编造需求内容或冲突判断。"
            "当工具足够回答用户时，直接给出简洁中文结论，不要输出 JSON。"
        )
        extra_system_context = str(context.get("_extra_system_context") or "").strip()
        if extra_system_context:
            prompt = f"{prompt}\n\n{extra_system_context}"
        return prompt

    def build_user_message(self, *, user_message: str, context: dict[str, Any]) -> str:
        payload = {
            "project_id": context.get("project_id"),
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
        }
