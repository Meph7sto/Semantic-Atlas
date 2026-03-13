"""Prompt construction helpers for requirement agent stages."""

from __future__ import annotations

from typing import Any

from .constants import DEFAULT_PROMPT_PAYLOAD_FORMAT
from .payload_codec import serialize_prompt_payload


class RequirementAgentPromptBuilder:
    def build_tool_loop_system_prompt(self) -> str:
        return (
            "你是需求管理 Agent。你运行在当前单个项目内，只能使用提供的工具查询或修改需求。"
            "必须优先依赖工具结果，不得编造需求内容或状态。"
            "如果用户要求修改需求，只有在 requirement_id 明确时才允许调用 update_requirement_content。"
            "若前端没有显式 requirement_id，必须先通过 list/search/get 明确定位到唯一需求；若仍不明确，则停止写入并转为中文澄清。"
            "search_requirements.keyword 不能为空白。"
            "工具返回是摘要结构；需要翻页时再继续调用列表或搜索工具。"
            "当工具足够回答用户时，直接给出简洁中文结论，不要输出 JSON。"
        )

    def build_tool_loop_user_message(
        self,
        *,
        project_id: str,
        user_message: str,
        requirement_id: str | None,
        historical_node_context: list[dict[str, Any]] | None = None,
        prompt_payload_format: str = DEFAULT_PROMPT_PAYLOAD_FORMAT,
    ) -> str:
        payload = {
            "project_id": project_id,
            "selected_requirement_id": requirement_id,
            "user_message": user_message,
            "historical_node_context": historical_node_context or [],
            "scope": "当前轮对话，附带会话链上一轮执行图的历史节点上下文摘要",
        }
        return serialize_prompt_payload(
            payload,
            prompt_payload_format=prompt_payload_format,
            markdown_title="当前任务上下文",
        )

    def build_final_reply_prompt(
        self,
        *,
        user_message: str,
        tool_loop_reply: str,
        mode: str,
        context: dict[str, Any],
        prompt_payload_format: str = DEFAULT_PROMPT_PAYLOAD_FORMAT,
    ) -> tuple[str, str]:
        system_prompt = (
            "你是面向需求工程用户的中文助手。"
            "根据给定的工具执行结果和阶段结论，输出自然、简洁、直接的最终回复。"
            "如果需要澄清，就只问最小必要问题。"
            "如果已经成功更新需求，要明确说明修改内容与最新版本。"
            "不要输出 JSON。"
        )
        prompt = serialize_prompt_payload(
            {
                "user_message": user_message,
                "mode": mode,
                "tool_loop_reply": tool_loop_reply,
                "resolved_requirement_id": context.get("resolved_requirement_id"),
                "resolved_requirement_summary": context.get("resolved_requirement_summary"),
                "last_write_result": context.get("last_write_result"),
                "tool_results": context.get("tool_results") or [],
            },
            prompt_payload_format=prompt_payload_format,
            markdown_title="最终回复生成上下文",
        )
        return system_prompt, prompt

    @staticmethod
    def build_tool_loop_input_summary(
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "round": round_index,
            "message_count": len(messages),
            "selected_requirement_id": context.get("selected_requirement_id"),
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            "historical_node_count": len(context.get("historical_node_context") or []),
        }

    @staticmethod
    def normalize_mode(context: dict[str, Any]) -> str:
        if context.get("write_performed"):
            return "requirement_update"
        if context.get("clarification_required"):
            return "clarification"
        return "chat"
