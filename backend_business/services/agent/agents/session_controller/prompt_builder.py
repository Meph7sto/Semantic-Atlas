"""Prompt construction helpers for session controller agent."""

from __future__ import annotations

import json
from typing import Any


def infer_routing_hint(user_message: str) -> dict[str, str] | None:
    text = " ".join(str(user_message or "").strip().lower().split())
    if not text:
        return None

    update_keywords = (
        "改为",
        "改成",
        "修改",
        "更新",
        "设置",
        "设为",
        "调整",
        "变更",
    )
    field_keywords = (
        "优先级",
        "priority",
        "标题",
        "title",
        "描述",
        "description",
        "验收标准",
        "acceptance",
        "备注",
        "notes",
        "内容",
    )
    requirement_reference_keywords = (
        "需求",
        "requirement",
        "req-",
        "这条",
        "该条",
        "这一条",
        "这个需求",
    )
    explicit_conflict_request_keywords = (
        "检测冲突",
        "检查冲突",
        "是否冲突",
        "有没有冲突",
        "冲突吗",
        "conflict check",
    )

    has_update_intent = any(keyword in text for keyword in update_keywords)
    touches_requirement_field = any(keyword in text for keyword in field_keywords)
    mentions_requirement_target = any(
        keyword in text for keyword in requirement_reference_keywords
    )
    asks_conflict_check = any(
        keyword in text for keyword in explicit_conflict_request_keywords
    )

    if has_update_intent and (touches_requirement_field or mentions_requirement_target):
        return {
            "preferred_tool": "invoke_requirement_agent",
            "reason": (
                "用户在修改需求属性。即使需求正文里出现“冲突检测”等业务术语，"
                "这仍然是需求管理任务，不应路由到冲突检测 Agent。"
            ),
        }

    if asks_conflict_check:
        return {
            "preferred_tool": "invoke_conflict_detection",
            "reason": "用户明确要求执行需求冲突检测。",
        }

    return None


class SessionControllerPromptBuilder:
    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        base_prompt = (
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
            "如果用户是在修改需求属性（如优先级、标题、描述、验收标准、备注），"
            "必须调用 invoke_requirement_agent。\n"
            "即使该需求正文里包含“冲突检测”“接口”“算法”等业务术语，也不能因此改派到 invoke_conflict_detection。\n"
            "只有当用户明确要求比较/检查两个或多个需求是否冲突时，才调用 invoke_conflict_detection。\n"
            "不清楚用户意图时，用最少问题澄清，不要猜测。\n"
            "当工具足够回答用户时，直接给出简洁中文结论，不要输出 JSON。"
        )
        routing_hint = context.get("routing_hint") or {}
        preferred_tool = str(routing_hint.get("preferred_tool") or "").strip()
        reason = str(routing_hint.get("reason") or "").strip()
        if preferred_tool:
            base_prompt += (
                "\n\n本轮路由提示："
                f"优先调用 {preferred_tool}。"
            )
            if reason:
                base_prompt += f"原因：{reason}"
        scratchpad_text = context.get("_scratchpad_prompt_text") or ""
        if scratchpad_text:
            base_prompt += (
                "\n\n以下是跨轮会话记事本。它记录了之前已经确认过的对象、执行结果和后续线索。"
                "当用户使用“它”“这个”“刚才那个”这类指代，且记事本中存在唯一明确的当前焦点时，"
                "优先沿用该焦点；如果记事本不能唯一定位，再发起最小必要澄清。\n\n"
                f"{scratchpad_text}"
            )
        return base_prompt

    def build_user_message(self, *, user_message: str, context: dict[str, Any]) -> str:
        payload = {
            "project_id": context.get("project_id"),
            "user_message": user_message,
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            "routing_hint": context.get("routing_hint"),
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
