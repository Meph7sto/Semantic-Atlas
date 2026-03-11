"""Tool-call loop execution for requirement agent conversations."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.tools import RequirementAgentTools

from .prompt_builder import RequirementAgentPromptBuilder
from .runtime_graph_recorder import _RuntimeGraphRecorder
from .utils import coerce_tool_arguments


class RequirementAgentToolLoopRunner:
    def __init__(
        self,
        *,
        ai_proxy_client: Any,
        tools: RequirementAgentTools,
        execution_graph_service: ExecutionGraphService,
        actor_manager_getter: Any,
        prompt_builder: RequirementAgentPromptBuilder,
        max_tool_call_rounds: int,
    ) -> None:
        self.ai_proxy = ai_proxy_client
        self.tools = tools
        self.execution_graph_service = execution_graph_service
        self.actor_manager_getter = actor_manager_getter
        self.prompt_builder = prompt_builder
        self.max_tool_call_rounds = max_tool_call_rounds

    def run(
        self,
        *,
        recorder: _RuntimeGraphRecorder,
        user_id: str,
        user_message: str,
        project_id: str,
        requirement_id: str | None,
        session_id: str,
        prompt_payload_format: str,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self.prompt_builder.build_tool_loop_system_prompt()},
            {
                "role": "user",
                "content": self.prompt_builder.build_tool_loop_user_message(
                    project_id=project_id,
                    user_message=user_message,
                    requirement_id=requirement_id,
                    historical_node_context=recorder.historical_node_context,
                    prompt_payload_format=prompt_payload_format,
                ),
            },
        ]
        context: dict[str, Any] = {
            "project_id": project_id,
            "user_id": user_id,
            "session_id": session_id,
            "graph_id": recorder.graph_id,
            "selected_requirement_id": requirement_id,
            "resolved_requirement_id": requirement_id,
            "resolved_requirement_ids": {requirement_id} if requirement_id else set(),
            "historical_node_context": recorder.historical_node_context,
            "tool_results": [],
            "write_performed": False,
            "clarification_required": False,
            "actor_manager": self.actor_manager_getter(),
        }

        for round_index in range(1, self.max_tool_call_rounds + 1):
            node_key = recorder.stage_node_key(f"requirements_agent_tool_loop_round_{round_index}")
            recorder.start_stage(
                node_key=node_key,
                label=recorder.stage_label(f"Tool Loop Round {round_index}"),
                node_type="llm",
                role_type="agent",
                container_key="requirements_agent",
                created_by=user_id,
                input_summary=self.prompt_builder.build_tool_loop_input_summary(
                    round_index=round_index,
                    messages=messages,
                    context=context,
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
                tools=self.tools.get_tools_list(),
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
                    arguments = coerce_tool_arguments(function_payload.get("arguments"))
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
                        tool_result = self.tools.execute(tool_name, arguments, context)
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
                    context["tool_results"].append(
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

                recorder.complete_stage(
                    node_key,
                    created_by=user_id,
                    output_summary=output_summary,
                )
                self.execution_graph_service.patch_graph_meta(
                    recorder.graph_id,
                    {"resolved_requirement_id": context.get("resolved_requirement_id")},
                    updated_by=user_id,
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

            recorder.complete_stage(
                node_key,
                created_by=user_id,
                output_summary=output_summary,
            )
            self.execution_graph_service.patch_graph_meta(
                recorder.graph_id,
                {"resolved_requirement_id": context.get("resolved_requirement_id")},
                updated_by=user_id,
            )
            yield {
                "event": "stage",
                "data": {
                    "graph_id": recorder.graph_id,
                    "node_key": node_key,
                    "status": "succeeded",
                },
            }
            return {
                "tool_loop_reply": assistant_content,
                "context": context,
                "rounds": round_index,
            }

        raise RuntimeError(f"工具调用轮数超过上限 {self.max_tool_call_rounds}，已终止本次请求")
