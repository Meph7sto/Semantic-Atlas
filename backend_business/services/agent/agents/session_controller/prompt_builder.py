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
            "所有需求分类必须通过 invoke_requirement_classification_agent 工具完成。\n"
            "list_requirements / search_requirements 仅用于探索性查询，不做任何写操作。\n"
            "如果用户是在修改需求属性（如优先级、标题、描述、验收标准、备注），"
            "必须调用 invoke_requirement_agent。\n"
            "即使该需求正文里包含“冲突检测”“接口”“算法”等业务术语，也不能因此改派到 invoke_conflict_detection。\n"
            "只有当用户明确要求比较/检查两个或多个需求是否冲突时，才调用 invoke_conflict_detection。\n"
            "不清楚用户意图时，用最少问题澄清，不要猜测。\n"
            "\n"
            "输出规则非常严格：\n"
            "1. 如果还需要调用工具，就直接调用工具，不要先输出自然语言。\n"
            "2. 如果你决定结束本轮，必须只输出一个 JSON 对象，不能输出 Markdown、代码块或额外解释。\n"
            "3. JSON 字段使用以下协议：\n"
            '{'
            '"mode":"direct_reply|clarify|browse|delegate_requirement|delegate_conflict|delegate_classification|approval_pending|error",'
            '"tool_loop_reply":"面向系统的中间结论摘要",'
            '"assistant_reply_seed":"可选，给最终回复阶段使用的中文草稿",'
            '"clarification_question":"可选，仅 clarify 时提供",'
            '"delegated_agent":"requirement_agent|conflict_detection|requirement_classification_agent|null",'
            '"resolved_requirement_id":"可选",'
            '"dispatched_agents":["可选"],'
            '"approval_pending":false,'
            '"should_suspend":false,'
            '"suspend_reason":"clarification|approval_pending|external_wait|null"'
            '}\n'
            "4. `clarify` 必须提供 clarification_question，并设置 should_suspend=true、suspend_reason=clarification。\n"
            "5. `approval_pending` 必须设置 approval_pending=true、should_suspend=true、suspend_reason=approval_pending。\n"
            "6. 子 Agent 工具返回后，你必须继续完成总控判断，并输出上述 JSON 对象。"
            "不要把工具返回直接当作最终结束信号。\n"
            "7. 只有在已经实际委托子 Agent 且本轮结论来自该子 Agent 时，才使用 delegate_requirement / delegate_conflict / delegate_classification。\n"
            "8. `tool_loop_reply` 用于系统日志和后续最终回复阶段，必须简洁、准确。"
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
