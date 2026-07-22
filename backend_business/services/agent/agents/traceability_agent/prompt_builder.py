"""Prompt construction for the requirement traceability agent."""

from __future__ import annotations

import json
from typing import Any


class TraceabilityAgentPromptBuilder:
    """Keep traceability analysis grounded in the shared requirement tools."""

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        high_level_requirement_id = str(
            context.get("high_level_requirement_id") or ""
        ).strip()
        low_level_requirement_id = str(
            context.get("low_level_requirement_id") or ""
        ).strip()
        prompt = (
            "你是需求追溯 Agent，只处理当前项目内顶层需求到低层需求的追溯分析。"
            "你的职责是判断低层需求是否细化、实现或支撑顶层需求，并清楚说明依据。"
            "不得修改需求，不得编造需求内容、需求 ID 或追溯结论。"
            "当顶层和底层需求 ID 都已提供时，优先直接调用 trace_requirement_relation；"
            "该工具会读取真实需求内容并按传入顺序分析。"
            "当任一 ID 不明确时，先用 search_requirements、list_requirements 或 get_requirement_state 定位，"
            "确认两条需求后再调用 trace_requirement_relation。"
            "工具返回后，基于返回的 relation 给出简洁中文结论，明确这对需求是否存在追溯关系及其依据。"
            "不要输出 JSON。"
        )
        if high_level_requirement_id and low_level_requirement_id:
            prompt += (
                "当前已明确顶层需求为 "
                f"{high_level_requirement_id}，底层需求为 {low_level_requirement_id}。"
                "不要交换两者的层级方向。"
            )
        extra_system_context = str(context.get("_extra_system_context") or "").strip()
        if extra_system_context:
            prompt = f"{prompt}\n\n{extra_system_context}"
        return prompt

    @staticmethod
    def build_user_message(*, user_message: str, context: dict[str, Any]) -> str:
        return json.dumps(
            {
                "project_id": context.get("project_id"),
                "high_level_requirement_id": context.get(
                    "high_level_requirement_id"
                ),
                "low_level_requirement_id": context.get(
                    "low_level_requirement_id"
                ),
                "user_message": user_message,
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
            "message_count": len(messages),
            "project_id": context.get("project_id"),
            "high_level_requirement_id": context.get("high_level_requirement_id"),
            "low_level_requirement_id": context.get("low_level_requirement_id"),
        }
