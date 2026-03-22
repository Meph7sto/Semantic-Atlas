"""Generic tool-call loop execution for agent conversations."""

from __future__ import annotations

import json
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any, Protocol

from backend_business.services.agent.runtime.scratchpad import Scratchpad

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


class CompletePhaseSignal(Exception):
    """Internal signal raised when LLM calls the complete_phase tool.

    This is NOT a real error — it is used to break out of the tool-call
    loop and indicate that the current subgraph/phase has been explicitly
    completed by the model.
    """

    def __init__(self, conclusion: str, route_key: str | None = None) -> None:
        self.conclusion = conclusion
        self.route_key = route_key
        super().__init__(f"complete_phase signal: route_key={route_key}")


@dataclass(frozen=True)
class ToolLoopResult:
    tool_loop_reply: str
    context: dict[str, Any]
    rounds: int
    phase_completed: bool = False
    route_key: str | None = None
    expand_topology: bool | None = None
    target_template_graph_id: str | None = None
    conclusion: str | None = None


# scratchpad_write tool definition injected when scratchpad mode is active
_SCRATCHPAD_WRITE_TOOL_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "scratchpad_write",
        "description": (
            "将重要发现、判断或工具结果摘录写入 Scratchpad 工作记忆。"
            "这些内容会在后续阶段中作为上下文保留，帮助跨阶段传递关键信息。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entry_type": {
                    "type": "string",
                    "enum": ["note", "tool_excerpt"],
                    "description": (
                        "条目类型。note: 自由备注（发现/判断/决策依据）；"
                        "tool_excerpt: 工具结果的选择性摘录（标记为只读，不可覆盖）"
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "要写入 Scratchpad 的内容",
                },
            },
            "required": ["entry_type", "content"],
        },
    },
}

# complete_phase tool definition injected when phase completion mode is active
_COMPLETE_PHASE_TOOL_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "complete_phase",
        "description": (
            "当你判断当前阶段的任务已经完成时，调用此工具发出显式的阶段完成信号。"
            "调用后运行时会标记当前阶段完成并推进到下一阶段。"
            "这是阶段完成的唯一信号——不要依赖返回纯文本来表示完成，请显式调用此工具。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "conclusion": {
                    "type": "string",
                    "description": "当前阶段的结论描述，概括本阶段完成的工作和关键产出",
                },
                "route_key": {
                    "type": "string",
                    "description": (
                        "路由字段，用于条件出边匹配。"
                        "如果当前拓扑节点配置了 conditional_edges，"
                        "运行时会用此值与条件逐一比对来决定下一阶段。"
                        "无条件流转时可不传。"
                    ),
                },
                "expand_topology": {
                    "type": "boolean",
                    "description": (
                        "仅 judge 入口节点使用。"
                        "true 表示需要展开拓扑图，false 表示走直接对话路径。"
                    ),
                },
                "target_template_graph_id": {
                    "type": "string",
                    "description": (
                        "仅 judge 入口节点使用。"
                        "当 expand_topology=true 时，填写候选拓扑图的 graph_id。"
                    ),
                },
            },
            "required": ["conclusion"],
        },
    },
}


class ToolLoopRunner:
    def __init__(
        self,
        *,
        ai_proxy_client: Any,
        tool_executor: ToolExecutorProtocol,
        prompt_builder: PromptBuilderProtocol,
        max_tool_call_rounds: int = 50,
        stage_container_key: str = "agent",
        stage_node_type: str = "llm",
        stage_role_type: str = "agent",
        stage_node_key_builder: Callable[[int], str] | None = None,
        stage_label_builder: Callable[[int], str] | None = None,
        actor_manager_getter: Callable[[], Any] | None = None,
        graph_meta_patcher: Callable[[str, dict[str, Any], str], None] | None = None,
        graph_meta_patch_builder: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
        scratchpad: Scratchpad | None = None,
        enable_complete_phase: bool = False,
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
        self.scratchpad = scratchpad
        self.enable_complete_phase = enable_complete_phase

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
                edge_type_from_previous="seq",
            )
            yield {
                "event": "stage",
                "data": {
                    "graph_id": recorder.graph_id,
                    "node_key": node_key,
                    "status": "running",
                },
            }

            tools_list = self.tool_executor.get_tools_list()
            if self.scratchpad is not None:
                # Inject scratchpad_write tool when scratchpad mode is active
                if not any(
                    (t.get("function") or {}).get("name") == "scratchpad_write"
                    for t in tools_list
                ):
                    tools_list = [*tools_list, _SCRATCHPAD_WRITE_TOOL_DEF]
            if self.enable_complete_phase:
                # Inject complete_phase tool for explicit phase completion signals
                if not any(
                    (t.get("function") or {}).get("name") == "complete_phase"
                    for t in tools_list
                ):
                    tools_list = [*tools_list, _COMPLETE_PHASE_TOOL_DEF]

            response = self.ai_proxy.chat_completion_with_tools(
                messages=messages,
                tools=tools_list,
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
                        if tool_name == "complete_phase" and self.enable_complete_phase:
                            # Built-in complete_phase handling: explicit phase completion signal
                            conclusion = arguments.get("conclusion", "")
                            route_key = arguments.get("route_key")
                            expand_topology = arguments.get("expand_topology")
                            target_template_graph_id = arguments.get("target_template_graph_id")
                            tool_result = {"ok": True, "message": "阶段完成信号已确认"}

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

                            # Auto-append conclusion to Scratchpad as stage_output
                            if self.scratchpad is not None:
                                self.scratchpad.append_stage_output(
                                    normalized_context.get("_current_subgraph") or "unknown",
                                    conclusion,
                                )

                            output_summary["phase_completed"] = True
                            output_summary["route_key"] = route_key
                            output_summary["expand_topology"] = expand_topology
                            output_summary["target_template_graph_id"] = target_template_graph_id
                            output_summary["conclusion"] = conclusion

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
                                    "phase_completed": True,
                                },
                            }
                            return ToolLoopResult(
                                tool_loop_reply=conclusion or assistant_content,
                                context=normalized_context,
                                rounds=round_index,
                                phase_completed=True,
                                route_key=route_key,
                                expand_topology=expand_topology,
                                target_template_graph_id=target_template_graph_id,
                                conclusion=conclusion,
                            )

                        elif tool_name == "scratchpad_write" and self.scratchpad is not None:
                            # Built-in scratchpad_write handling
                            self.scratchpad.write(
                                entry_type=arguments.get("entry_type", "note"),
                                content=arguments.get("content", ""),
                                source_subgraph=normalized_context.get("_current_subgraph"),
                                readonly=(arguments.get("entry_type") == "tool_excerpt"),
                            )
                            tool_result = {"ok": True, "message": "已写入 Scratchpad"}
                        else:
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
