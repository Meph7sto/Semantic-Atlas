"""Prompt construction helpers for session controller agent."""

from __future__ import annotations

import json
from typing import Any


class SessionControllerPromptBuilder:
    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        return (
            "你是会话总控 Agent（Session Controller）。你是用户与需求工程平台唯一的交互入口。\n"
            "\n"
            "职责严格限于三项：\n"
            "1. 意图识别：理解用户意图，判断需要执行哪类操作。\n"
            "2. 调度分发：通过工具将任务派发给执行层 Agent。\n"
            "3. 结果汇报：基于工具返回结果，给出简洁中文回复。\n"
            "\n"
            "你不持有任何需求业务数据。\n"
            "所有需求读写操作必须通过 invoke_requirement_agent 工具完成。\n"
            "所有冲突检测必须通过 invoke_conflict_detection 工具完成。\n"
            "list_requirements / search_requirements 仅用于探索性查询，不做任何写操作。\n"
            "不清楚用户意图时，用最少问题澄清，不要猜测。\n"
            "当工具足够回答用户时，直接给出简洁中文结论，不要输出 JSON。"
        )

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
