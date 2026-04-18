"""Generic tool-call loop execution for agent conversations."""

from __future__ import annotations

import inspect
import json
import logging
import queue
import threading
from collections.abc import Callable, Generator
from dataclasses import dataclass
from typing import Any, Protocol

from backend_business.services.agent.runtime.context import ContextEntry
from backend_business.services.agent.runtime.scratchpad import Scratchpad

from .prompt_interface import PromptBuilderProtocol


logger = logging.getLogger(__name__)


class ToolExecutorProtocol(Protocol):
    def get_tools_list(
        self,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        ...

    def execute(self, tool_name: str, arguments: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        ...

    def execute_streaming(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
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


def _summarize_model_response_for_diagnostics(response: dict[str, Any]) -> dict[str, Any]:
    tool_calls = response.get("tool_calls")
    normalized_tool_calls = tool_calls if isinstance(tool_calls, list) else []
    reasoning_text = str(response.get("reasoning_content") or "").strip()
    return {
        "finish_reason": response.get("finish_reason"),
        "content_present": bool(str(response.get("content") or "").strip()),
        "reasoning_content_present": bool(reasoning_text),
        "tool_call_count": len(normalized_tool_calls),
        "tool_call_names": [
            str(((item.get("function") or {}).get("name")) or "").strip()
            for item in normalized_tool_calls[:5]
            if isinstance(item, dict)
        ],
        "response_keys": sorted(str(key) for key in response.keys()),
    }


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
class _ToolExecutionOutcome:
    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    context_updates: dict[str, Any]
    phase_completion: dict[str, Any] | None = None


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
    target_container_keys: tuple[str, ...] = ()
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
                "target_container_keys": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": (
                        "仅 judge 入口节点使用。"
                        "当 expand_topology=true 且只需要展开模板中的部分业务容器时，"
                        "填写需要额外展开的 container_key 列表。"
                        "不要填写入口容器本身。"
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

    def _execute_tool_with_streaming_support(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        execute_streaming = getattr(self.tool_executor, "execute_streaming", None)
        if callable(execute_streaming):
            execution = execute_streaming(tool_name, arguments, context)
        else:
            execution = self.tool_executor.execute(tool_name, arguments, context)

        if inspect.isgenerator(execution):
            result: dict[str, Any] | None = None
            try:
                while True:
                    yield next(execution)
            except StopIteration as stop:
                result = stop.value or {}
            return result

        return execution

    def _get_tools_list(
        self,
        *,
        context: dict[str, Any],
    ) -> list[dict[str, Any]]:
        get_tools_list = getattr(self.tool_executor, "get_tools_list")
        try:
            signature = inspect.signature(get_tools_list)
        except (TypeError, ValueError):
            signature = None
        if signature is not None and "context" in signature.parameters:
            return get_tools_list(context=context)
        return get_tools_list()

    @staticmethod
    def _build_stage_event_payload(recorder: Any, node_key: str, *, status: str, **extra: Any) -> dict[str, Any]:
        builder = getattr(recorder, "build_stage_event_data", None)
        if callable(builder):
            return builder(node_key, status=status, **extra)
        payload = {
            "graph_id": recorder.graph_id,
            "node_key": node_key,
            "status": status,
        }
        payload.update(extra)
        return payload

    @staticmethod
    def _build_tool_result_event_payload(
        recorder: Any,
        node_key: str,
        *,
        tool: str,
        tool_call_id: str,
        result: Any,
    ) -> dict[str, Any]:
        builder = getattr(recorder, "build_tool_result_event_data", None)
        if callable(builder):
            return builder(
                node_key,
                tool=tool,
                tool_call_id=tool_call_id,
                result=result,
            )
        return {
            "graph_id": recorder.graph_id,
            "node_key": node_key,
            "tool": tool,
            "tool_call_id": tool_call_id,
            "result": result,
        }

    @staticmethod
    def _context_values_equal(left: Any, right: Any) -> bool:
        try:
            return left == right
        except Exception:
            return left is right

    def _extract_context_updates(
        self,
        *,
        before: dict[str, Any],
        after: dict[str, Any],
    ) -> dict[str, Any]:
        updates: dict[str, Any] = {}
        for key, value in after.items():
            if key == "tool_results" or str(key).startswith("_"):
                continue
            if not self._context_values_equal(before.get(key), value):
                updates[key] = value
        return updates

    @staticmethod
    def _clone_parallel_context_snapshot(
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Clone the per-round context snapshot visible to parallel tool calls.

        Parallel tool calls within the same round all read from the same
        pre-dispatch snapshot. They do not observe each other's writes.
        """
        snapshot = dict(context)
        if "tool_results" in context:
            snapshot["tool_results"] = list(context.get("tool_results") or [])
        return snapshot

    @staticmethod
    def _merge_parallel_tool_outcomes(
        *,
        normalized_context: dict[str, Any],
        outcomes: list[_ToolExecutionOutcome],
    ) -> None:
        """Deterministically merge same-round tool outcomes back into context.

        Merge semantics:
        - Each tool call sees only the round-start snapshot.
        - Same-round tool calls are isolated from each other's writes.
        - Context updates replay in original tool index order.
        - ``tool_results`` are appended in that same deterministic order.
        """
        for outcome in outcomes:
            normalized_context.update(outcome.context_updates)
            normalized_context.setdefault("tool_results", []).append(
                {
                    "tool_name": outcome.tool_name,
                    "arguments": outcome.arguments,
                    "result": outcome.result,
                }
            )

    @staticmethod
    def _raise_if_cancellation_requested(context: dict[str, Any]) -> None:
        for key in ("_runtime_cancel_event", "_branch_stop_token"):
            token = context.get(key)
            if token is not None and callable(getattr(token, "is_set", None)) and token.is_set():
                raise RuntimeError("runtime execution cancelled")

    def _normalize_phase_completion(
        self,
        *,
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        raw_target_container_keys = arguments.get("target_container_keys")
        target_container_keys = (
            tuple(
                str(item).strip()
                for item in raw_target_container_keys
                if str(item).strip()
            )
            if isinstance(raw_target_container_keys, list)
            else ()
        )
        return {
            "conclusion": arguments.get("conclusion", ""),
            "route_key": arguments.get("route_key"),
            "expand_topology": arguments.get("expand_topology"),
            "target_template_graph_id": arguments.get("target_template_graph_id"),
            "target_container_keys": target_container_keys,
        }

    def _execute_tool_batch(
        self,
        *,
        tool_calls: list[dict[str, Any]],
        recorder: Any,
        node_key: str,
        normalized_context: dict[str, Any],
    ) -> Generator[dict[str, Any], None, list[_ToolExecutionOutcome]]:
        result_queue: queue.Queue[tuple[str, int, Any]] = queue.Queue()
        worker_threads: list[threading.Thread] = []
        round_context_snapshot = self._clone_parallel_context_snapshot(
            normalized_context,
        )

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

            tool_context = self._clone_parallel_context_snapshot(
                round_context_snapshot,
            )

            worker = threading.Thread(
                target=self._run_tool_worker,
                args=(
                    result_queue,
                    tool_index - 1,
                    tool_name,
                    tool_call_id,
                    arguments,
                    round_context_snapshot,
                    tool_context,
                ),
                name=f"tool-loop-{tool_index}",
                daemon=True,
            )
            worker.start()
            worker_threads.append(worker)

        outcomes: dict[int, _ToolExecutionOutcome] = {}
        completed_workers = 0

        while completed_workers < len(worker_threads):
            item_type, index, payload = result_queue.get()
            if item_type == "event":
                yield payload
                continue
            if item_type == "result":
                completed_workers += 1
                outcomes[index] = payload

        for worker in worker_threads:
            worker.join()

        return [outcomes[index] for index in sorted(outcomes)]

    def _run_tool_worker(
        self,
        result_queue: "queue.Queue[tuple[str, int, Any]]",
        index: int,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any],
        base_context: dict[str, Any],
        tool_context: dict[str, Any],
    ) -> None:
        try:
            phase_completion: dict[str, Any] | None = None
            if tool_name == "complete_phase" and self.enable_complete_phase:
                phase_completion = self._normalize_phase_completion(arguments=arguments)
                tool_result = {"ok": True, "message": "阶段完成信号已确认"}
            elif tool_name == "scratchpad_write" and self.scratchpad is not None:
                self.scratchpad.write(
                    entry_type=arguments.get("entry_type", "note"),
                    content=arguments.get("content", ""),
                    source_subgraph=tool_context.get("_current_subgraph"),
                    readonly=(arguments.get("entry_type") == "tool_excerpt"),
                )
                tool_result = {"ok": True, "message": "已写入 Scratchpad"}
            else:
                execute_streaming = getattr(self.tool_executor, "execute_streaming", None)
                if callable(execute_streaming):
                    execution = execute_streaming(tool_name, arguments, tool_context)
                else:
                    execution = self.tool_executor.execute(tool_name, arguments, tool_context)

                if inspect.isgenerator(execution):
                    try:
                        while True:
                            result_queue.put(("event", index, next(execution)))
                    except StopIteration as stop:
                        tool_result = stop.value or {}
                else:
                    tool_result = execution

            result_queue.put(
                (
                    "result",
                    index,
                    _ToolExecutionOutcome(
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        arguments=arguments,
                        result=tool_result,
                        context_updates=self._extract_context_updates(
                            before=base_context,
                            after=tool_context,
                        ),
                        phase_completion=phase_completion,
                    ),
                )
            )
        except Exception as exc:
            result_queue.put(
                (
                    "result",
                    index,
                    _ToolExecutionOutcome(
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        arguments=arguments,
                        result={
                            "error": str(exc),
                            "is_error": True,
                        },
                        context_updates=self._extract_context_updates(
                            before=base_context,
                            after=tool_context,
                        ),
                        phase_completion=None,
                    ),
                )
            )

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
        execution_context = normalized_context.get("_execution_context")

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
        if execution_context is not None and user_message.strip():
            execution_context.add(
                ContextEntry(
                    kind="user_message",
                    value=user_message,
                )
            )

        for round_index in range(1, self.max_tool_call_rounds + 1):
            self._raise_if_cancellation_requested(normalized_context)
            messages[0]["content"] = self.prompt_builder.build_system_prompt(
                context=normalized_context,
            )
            node_key = recorder.stage_node_key(self.stage_node_key_builder(round_index))
            normalized_context["_active_stage_node_key"] = node_key
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
                "data": self._build_stage_event_payload(
                    recorder,
                    node_key,
                    status="running",
                ),
            }

            tools_list = self._get_tools_list(context=normalized_context)
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
                outcomes = yield from self._execute_tool_batch(
                    tool_calls=tool_calls,
                    recorder=recorder,
                    node_key=node_key,
                    normalized_context=normalized_context,
                )
                self._raise_if_cancellation_requested(normalized_context)
                phase_completion: dict[str, Any] | None = None

                for outcome in outcomes:
                    recorder.record_tool_call_result(
                        node_key,
                        created_by=user_id,
                        tool_name=outcome.tool_name,
                        request_payload={
                            "tool_call_id": outcome.tool_call_id,
                            "arguments": outcome.arguments,
                        },
                        result_payload=outcome.result,
                    )
                    if phase_completion is None and outcome.phase_completion is not None:
                        phase_completion = outcome.phase_completion
                        if execution_context is not None:
                            execution_context.add(
                                ContextEntry(
                                    kind="phase_conclusion",
                                    value={
                                        "conclusion": outcome.phase_completion["conclusion"],
                                        "route_key": outcome.phase_completion["route_key"],
                                        "expand_topology": outcome.phase_completion["expand_topology"],
                                        "target_template_graph_id": outcome.phase_completion["target_template_graph_id"],
                                        "target_container_keys": list(
                                            outcome.phase_completion["target_container_keys"]
                                        ),
                                    },
                                    node_key=node_key,
                                )
                            )
                        continue

                    self._merge_parallel_tool_outcomes(
                        normalized_context=normalized_context,
                        outcomes=[outcome],
                    )
                    if execution_context is not None:
                        execution_context.add(
                            ContextEntry(
                                kind="tool_result",
                                value={
                                    "tool_name": outcome.tool_name,
                                    "arguments": outcome.arguments,
                                    "result": outcome.result,
                                },
                                node_key=node_key,
                            )
                        )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": outcome.tool_call_id,
                            "content": json.dumps(outcome.result, ensure_ascii=False),
                        }
                    )
                    yield {
                        "event": "tool_result",
                        "data": self._build_tool_result_event_payload(
                            recorder,
                            node_key,
                            tool=outcome.tool_name,
                            tool_call_id=outcome.tool_call_id,
                            result=outcome.result,
                        ),
                    }

                if phase_completion is not None:
                    if self.scratchpad is not None and execution_context is None:
                        self.scratchpad.append_stage_output(
                            normalized_context.get("_current_subgraph") or "unknown",
                            phase_completion["conclusion"],
                        )

                    output_summary["phase_completed"] = True
                    output_summary["route_key"] = phase_completion["route_key"]
                    output_summary["expand_topology"] = phase_completion["expand_topology"]
                    output_summary["target_template_graph_id"] = phase_completion["target_template_graph_id"]
                    output_summary["target_container_keys"] = list(
                        phase_completion["target_container_keys"]
                    )
                    output_summary["conclusion"] = phase_completion["conclusion"]

                    self._complete_round_and_patch_meta(
                        recorder=recorder,
                        node_key=node_key,
                        user_id=user_id,
                        output_summary=output_summary,
                        context=normalized_context,
                    )
                    yield {
                        "event": "stage",
                        "data": self._build_stage_event_payload(
                            recorder,
                            node_key,
                            status="succeeded",
                            phase_completed=True,
                        ),
                    }
                    return ToolLoopResult(
                        tool_loop_reply=phase_completion["conclusion"] or assistant_content,
                        context=normalized_context,
                        rounds=round_index,
                        phase_completed=True,
                        route_key=phase_completion["route_key"],
                        expand_topology=phase_completion["expand_topology"],
                        target_template_graph_id=phase_completion["target_template_graph_id"],
                        target_container_keys=phase_completion["target_container_keys"],
                        conclusion=phase_completion["conclusion"],
                    )

                self._complete_round_and_patch_meta(
                    recorder=recorder,
                    node_key=node_key,
                    user_id=user_id,
                    output_summary=output_summary,
                    context=normalized_context,
                )
                yield {
                    "event": "stage",
                    "data": self._build_stage_event_payload(
                        recorder,
                        node_key,
                        status="succeeded",
                    ),
                }
                continue

            if not assistant_content:
                diagnostics = _summarize_model_response_for_diagnostics(response)
                logger.warning(
                    "Model returned empty tool-loop response: graph_id=%s node_key=%s round=%s diagnostics=%s",
                    recorder.graph_id,
                    node_key,
                    round_index,
                    json.dumps(diagnostics, ensure_ascii=False),
                )
                raise ValueError(
                    "模型未返回文本或工具调用 "
                    f"(finish_reason={diagnostics['finish_reason']!r}, "
                    f"reasoning_content_present={diagnostics['reasoning_content_present']}, "
                    f"tool_call_count={diagnostics['tool_call_count']}, "
                    f"response_keys={diagnostics['response_keys']})"
                )

            self._complete_round_and_patch_meta(
                recorder=recorder,
                node_key=node_key,
                user_id=user_id,
                output_summary=output_summary,
                context=normalized_context,
            )
            if execution_context is not None:
                execution_context.add(
                    ContextEntry(
                        kind="assistant_message",
                        value=assistant_content,
                        node_key=node_key,
                    )
                )
            yield {
                "event": "stage",
                "data": self._build_stage_event_payload(
                    recorder,
                    node_key,
                    status="succeeded",
                ),
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
