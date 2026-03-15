"""Generic tool-call loop execution for agent conversations."""

from __future__ import annotations

import json
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any, Protocol

from .prompt_interface import PromptBuilderProtocol


class ToolExecutorProtocol(Protocol):
    def get_tools_list(self) -> list[dict[str, Any]]:
        ...

    def execute(self, tool_name: str, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...


def _coerce_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if raw_arguments is None:
        return {}
    if isinstance(raw_arguments, dict):
        return dict(raw_arguments)
    if isinstance(raw_arguments, str):
        text = raw_arguments.strip()
        if not text:
            return {}
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("tool arguments 必须是对象")
        return parsed
    raise ValueError("tool arguments 格式无效")


@dataclass(frozen=True)
class ToolCallEvent:
    graph_id: str
    node_key: str
    tool: str
    tool_call_id: str
    arguments: dict[str, Any]
    result: dict[str, Any] | None = None
    error: str | None = None


@dataclass(frozen=True)
class ToolLoopResult:
    tool_loop_reply: str
    context: dict[str, Any]
    rounds: int


class ToolLoopRunner:
    def __init__(
        self,
        *,
        ai_proxy_client: Any,
        tool_executor: ToolExecutorProtocol,
        prompt_builder: PromptBuilderProtocol,
        max_tool_call_rounds: int = 6,
        stage_container_key: str = "agent",
        stage_node_type: str = "llm",
        stage_role_type: str = "agent",
        stage_node_key_builder: Callable[[int], str] | None = None,
        stage_label_builder: Callable[[int], str] | None = None,
        actor_manager_getter: Callable[[], Any] | None = None,
        graph_meta_patcher: Callable[[str, dict[str, Any], str], None] | None = None,
        graph_meta_patch_builder: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> None:
        self.ai_proxy = ai_proxy_client
        self.tool_executor = tool_executor
        self.prompt_builder = prompt_builder
        self.max_tool_call_rounds = max_tool_call_rounds
        self.stage_container_key = stage_container_key
        self.stage_node_type = stage_node_type
        self.stage_role_type = stage_role_type
        self.stage_node_key_builder = stage_node_key_builder or (lambda round_index: f"tool_loop_round_{round_index}")
        self.stage_label_builder = stage_label_builder or (lambda round_index: f"Tool Loop Round {round_index}")
        self.actor_manager_getter = actor_manager_getter
        self.graph_meta_patcher = graph_meta_patcher
        self.graph_meta_patch_builder = graph_meta_patch_builder

    def run(
        self,
        *,
        recorder: Any,
        user_id: str,
        user_message: str,
        context: dict[str, Any],
    ) -> Generator[dict[str, Any], None, ToolLoopResult]:
        normalized_context = dict(context)
        if self.actor_manager_getter:
            normalized_context["actor_manager"] = self.actor_manager_getter()

        messages: list[dict[str, Any]] = [
            {
                "role": "system",
                "content": self.prompt_builder.build_system_prompt(context=normalized_context),
            },
            {
                "role": "user",
                "content": self.prompt_builder.build_user_message(
                    user_message=user_message,
                    context=normalized_context,
                ),
            },
        ]

        for round_index in range(1, self.max_tool_call_rounds + 1):
            node_key = recorder.stage_node_key(self.stage_node_key_builder(round_index))
            recorder.start_stage(
                node_key=node_key,
                label=recorder.stage_label(self.stage_label_builder(round_index)),
                node_type=self.stage_node_type,
                role_type=self.stage_role_type,
                container_key=self.stage_container_key,
                created_by=user_id,
                input_summary=self.prompt_builder.build_round_input_summary(
                    round_index=round_index,
                    messages=messages,
                    context=normalized_context,
                ),
                edge_type_from_previous="call",
            )
            yield {
                "event": "stage",
                "data": {
                    "graph_id": recorder.graph_id,
                    "node_key": node_key,
                    "status": "running",
                },
            }

            response = self.ai_proxy.chat_completion_with_tools(
                messages=messages,
                tools=self.tool_executor.get_tools_list(),
                temperature=0.2,
                tool_choice="auto",
            )
            tool_calls = response.get("tool_calls") or []
            assistant_content = str(response.get("content") or "").strip()
            finish_reason = response.get("finish_reason")

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_content,
            }
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)

            output_summary: dict[str, Any] = {
                "round": round_index,
                "finish_reason": finish_reason,
                "content": assistant_content or None,
                "tool_calls": tool_calls,
            }

            if tool_calls:
                for tool_index, tool_call in enumerate(tool_calls, start=1):
                    function_payload = tool_call.get("function") or {}
                    tool_name = function_payload.get("name") or ""
                    arguments = _coerce_tool_arguments(function_payload.get("arguments"))
                    tool_call_id = tool_call.get("id") or f"{node_key}-tool-{tool_index}"

                    yield {
                        "event": "tool_call",
                        "data": {
                            "graph_id": recorder.graph_id,
                            "node_key": node_key,
                            "tool": tool_name,
                            "tool_call_id": tool_call_id,
                            "arguments": arguments,
                        },
                    }

                    try:
                        tool_result = self.tool_executor.execute(tool_name, arguments, normalized_context)
                    except Exception as exc:
                        tool_result = {
                            "error": str(exc),
                            "is_error": True,
                        }

                    recorder.record_tool_call_result(
                        node_key,
                        created_by=user_id,
                        tool_name=tool_name,
                        request_payload={
                            "tool_call_id": tool_call_id,
                            "arguments": arguments,
                        },
                        result_payload=tool_result,
                    )
                    normalized_context.setdefault("tool_results", []).append(
                        {
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "result": tool_result,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps(tool_result, ensure_ascii=False),
                        }
                    )
                    yield {
                        "event": "tool_result",
                        "data": {
                            "graph_id": recorder.graph_id,
                            "node_key": node_key,
                            "tool": tool_name,
                            "tool_call_id": tool_call_id,
                            "result": tool_result,
                        },
                    }

                self._complete_round_and_patch_meta(
                    recorder=recorder,
                    node_key=node_key,
                    user_id=user_id,
                    output_summary=output_summary,
                    context=normalized_context,
                )
                yield {
                    "event": "stage",
                    "data": {
                        "graph_id": recorder.graph_id,
                        "node_key": node_key,
                        "status": "succeeded",
                    },
                }
                continue

            if not assistant_content:
                raise ValueError("模型未返回文本或工具调用")

            self._complete_round_and_patch_meta(
                recorder=recorder,
                node_key=node_key,
                user_id=user_id,
                output_summary=output_summary,
                context=normalized_context,
            )
            yield {
                "event": "stage",
                "data": {
                    "graph_id": recorder.graph_id,
                    "node_key": node_key,
                    "status": "succeeded",
                },
            }
            return ToolLoopResult(
                tool_loop_reply=assistant_content,
                context=normalized_context,
                rounds=round_index,
            )

        raise RuntimeError(f"工具调用轮数超过上限 {self.max_tool_call_rounds}，已终止本次请求")

    def _complete_round_and_patch_meta(
        self,
        *,
        recorder: Any,
        node_key: str,
        user_id: str,
        output_summary: dict[str, Any],
        context: dict[str, Any],
    ) -> None:
        recorder.complete_stage(
            node_key,
            created_by=user_id,
            output_summary=output_summary,
        )

        if not self.graph_meta_patcher or not self.graph_meta_patch_builder:
            return

        meta_patch = self.graph_meta_patch_builder(context)
        if not meta_patch:
            return
        self.graph_meta_patcher(recorder.graph_id, meta_patch, user_id)

