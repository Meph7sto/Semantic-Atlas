"""Generic tool-call loop execution for agent conversations."""

from __future__ import annotations

import copy
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
from backend_business.services.agent.runtime.tool_scheduling import (
    ToolExecutionMetadata,
)

from .prompt_interface import PromptBuilderProtocol


logger = logging.getLogger(__name__)


class ToolExecutorProtocol(Protocol):
    def get_tools_list(
        self,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]: ...

    def execute(
        self, tool_name: str, arguments: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]: ...

    def execute_streaming(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> Generator[dict[str, Any], None, dict[str, Any]]: ...


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
class _ContextUpdate:
    before_exists: bool
    before_value: Any
    after_exists: bool
    after_value: Any
    replaced_paths: frozenset[tuple[Any, ...]] = frozenset()


@dataclass(frozen=True)
class _ToolExecutionOutcome:
    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    result: dict[str, Any]
    context_updates: dict[str, _ContextUpdate]
    phase_completion: dict[str, Any] | None = None


@dataclass(frozen=True)
class _ScheduledToolCall:
    index: int
    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    metadata: ToolExecutionMetadata


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
                "importance": {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 1,
                    "description": "该记忆对后续任务的重要度，0 到 1；不确定时可省略",
                },
                "task_refs": {
                    "type": "array",
                    "items": {"type": "string"},
                    "maxItems": 16,
                    "description": (
                        "与该记忆直接相关的 requirement_id、任务或主题标识。"
                        "仅真正跨任务适用的不变量可使用 global-invariant"
                    ),
                },
            },
            "required": ["entry_type", "content"],
            "additionalProperties": False,
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
                        "仅 judge 入口节点使用。true 表示需要展开拓扑图，false 表示走直接对话路径。"
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
        max_concurrent_tool_calls_per_round: int = 4,
    ) -> None:
        self.ai_proxy = ai_proxy_client
        self.tool_executor = tool_executor
        self.prompt_builder = prompt_builder
        self.max_tool_call_rounds = max_tool_call_rounds
        self.stage_container_key = stage_container_key
        self.stage_node_type = stage_node_type
        self.stage_role_type = stage_role_type
        self.stage_node_key_builder = stage_node_key_builder or (
            lambda round_index: f"tool_loop_round_{round_index}"
        )
        self.stage_label_builder = stage_label_builder or (
            lambda round_index: f"Tool Loop Round {round_index}"
        )
        self.actor_manager_getter = actor_manager_getter
        self.graph_meta_patcher = graph_meta_patcher
        self.graph_meta_patch_builder = graph_meta_patch_builder
        self.scratchpad = scratchpad
        self.enable_complete_phase = enable_complete_phase
        if max_concurrent_tool_calls_per_round < 1:
            raise ValueError("max_concurrent_tool_calls_per_round must be positive")
        self.max_concurrent_tool_calls_per_round = max_concurrent_tool_calls_per_round

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
    def _build_stage_event_payload(
        recorder: Any, node_key: str, *, status: str, **extra: Any
    ) -> dict[str, Any]:
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

    @staticmethod
    def _copy_context_value(value: Any) -> Any:
        try:
            return copy.deepcopy(value)
        except Exception:
            return value

    @staticmethod
    def _capture_context_references(
        context: dict[str, Any],
    ) -> dict[str, dict[tuple[Any, ...], Any]]:
        """Remember mutable object identities before a tool runs.

        Value diffs alone cannot distinguish an in-place append from assigning
        a replacement collection with similar contents. Keeping the original
        object references lets the deterministic merge honor explicit
        replacements while still combining independent in-place mutations.
        """

        captured: dict[str, dict[tuple[Any, ...], Any]] = {}

        def capture_value(
            value: Any,
            *,
            path: tuple[Any, ...],
            references: dict[tuple[Any, ...], Any],
            visited: set[int],
        ) -> None:
            if not isinstance(value, (dict, list, set)):
                return
            references[path] = value
            value_id = id(value)
            if value_id in visited:
                return
            visited.add(value_id)
            if isinstance(value, dict):
                for child_key, child_value in value.items():
                    capture_value(
                        child_value,
                        path=(*path, child_key),
                        references=references,
                        visited=visited,
                    )

        for key, value in context.items():
            if key == "tool_results" or str(key).startswith("_"):
                continue
            references: dict[tuple[Any, ...], Any] = {}
            capture_value(
                value,
                path=(),
                references=references,
                visited=set(),
            )
            if references:
                captured[key] = references
        return captured

    @staticmethod
    def _resolve_context_value_path(
        value: Any,
        path: tuple[Any, ...],
    ) -> tuple[bool, Any]:
        current = value
        for component in path:
            if not isinstance(current, dict) or component not in current:
                return False, None
            current = current[component]
        return True, current

    def _extract_context_updates(
        self,
        *,
        before: dict[str, Any],
        after: dict[str, Any],
        original_context_references: dict[
            str,
            dict[tuple[Any, ...], Any],
        ]
        | None = None,
    ) -> dict[str, _ContextUpdate]:
        updates: dict[str, _ContextUpdate] = {}
        ordered_keys = [
            *after.keys(),
            *(key for key in before if key not in after),
        ]
        for key in ordered_keys:
            if key == "tool_results" or str(key).startswith("_"):
                continue
            before_exists = key in before
            after_exists = key in after
            before_value = before.get(key)
            after_value = after.get(key)
            if before_exists == after_exists and self._context_values_equal(
                before_value, after_value
            ):
                continue

            replaced_paths: set[tuple[Any, ...]] = set()
            if after_exists and original_context_references is not None:
                for path, original_value in original_context_references.get(
                    key,
                    {},
                ).items():
                    path_exists, current_value = self._resolve_context_value_path(
                        after_value,
                        path,
                    )
                    if path_exists and current_value is not original_value:
                        replaced_paths.add(path)

            updates[key] = _ContextUpdate(
                before_exists=before_exists,
                before_value=self._copy_context_value(before_value),
                after_exists=after_exists,
                after_value=self._copy_context_value(after_value),
                replaced_paths=frozenset(replaced_paths),
            )
        return updates

    @staticmethod
    def _clone_parallel_context_snapshot(
        context: dict[str, Any],
    ) -> dict[str, Any]:
        """Clone the per-round context snapshot visible to parallel tool calls.

        Parallel tool calls within the same round all read from the same
        pre-dispatch snapshot. They do not observe each other's writes.
        """
        snapshot: dict[str, Any] = {}
        for key, value in context.items():
            if str(key).startswith("_"):
                snapshot[key] = value
                continue
            try:
                snapshot[key] = copy.deepcopy(value)
            except Exception:
                snapshot[key] = value
        return snapshot

    def _resolve_tool_execution_metadata(
        self,
        *,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> ToolExecutionMetadata:
        if tool_name == "scratchpad_write" and self.scratchpad is not None:
            subgraph = str(context.get("_current_subgraph") or "default").strip()
            return ToolExecutionMetadata(
                read_only=False,
                idempotent=False,
                resource_key=f"{self.stage_container_key}:{subgraph}",
                concurrency_group="scratchpad",
            )
        if tool_name == "complete_phase" and self.enable_complete_phase:
            return ToolExecutionMetadata(
                read_only=False,
                idempotent=False,
                resource_key=self.stage_container_key,
                concurrency_group="phase-control",
            )

        resolver = getattr(
            self.tool_executor,
            "get_tool_execution_metadata",
            None,
        )
        if not callable(resolver):
            return ToolExecutionMetadata()
        try:
            resolved = resolver(tool_name, arguments, context)
        except Exception:
            logger.warning(
                "Tool execution metadata resolution failed; using conservative defaults: tool=%s",
                tool_name,
                exc_info=True,
            )
            return ToolExecutionMetadata()
        return ToolExecutionMetadata.coerce(resolved)

    @staticmethod
    def _tool_calls_conflict(
        left: _ScheduledToolCall,
        right: _ScheduledToolCall,
    ) -> bool:
        if left.metadata.read_only and right.metadata.read_only:
            return False

        left_resource = left.metadata.resource_key
        right_resource = right.metadata.resource_key
        if left_resource is not None and right_resource is not None:
            return left_resource == right_resource

        # A write without a resource key is a global barrier. This conservative
        # fallback prevents undeclared side effects from bypassing declared
        # groups and resources.
        return True

    @classmethod
    def _can_start_tool_call(
        cls,
        candidate: _ScheduledToolCall,
        *,
        active_calls: list[_ScheduledToolCall],
        earlier_pending_calls: list[_ScheduledToolCall],
    ) -> bool:
        return not any(
            cls._tool_calls_conflict(candidate, other)
            for other in [*active_calls, *earlier_pending_calls]
        )

    @classmethod
    def _merge_context_value(
        cls,
        *,
        base: Any,
        existing: Any,
        update: Any,
        replaced_paths: frozenset[tuple[Any, ...]],
        path: tuple[Any, ...] = (),
    ) -> Any:
        if path in replaced_paths or cls._context_values_equal(existing, base):
            return cls._copy_context_value(update)

        if isinstance(base, dict) and isinstance(existing, dict) and isinstance(update, dict):
            if not update:
                return {}
            merged = cls._copy_context_value(existing)
            for key in base:
                if key not in update:
                    merged.pop(key, None)
            for key, value in update.items():
                child_path = (*path, key)
                if key not in base:
                    merged[key] = cls._copy_context_value(value)
                elif not cls._context_values_equal(base[key], value):
                    if key not in merged:
                        merged[key] = cls._copy_context_value(value)
                    else:
                        merged[key] = cls._merge_context_value(
                            base=base[key],
                            existing=merged[key],
                            update=value,
                            replaced_paths=replaced_paths,
                            path=child_path,
                        )
            return merged

        if isinstance(base, list) and isinstance(existing, list) and isinstance(update, list):
            if not update:
                return []
            base_length = len(base)
            if len(update) >= base_length and cls._context_values_equal(update[:base_length], base):
                merged = cls._copy_context_value(existing)
                merged.extend(cls._copy_context_value(update[base_length:]))
                return merged
            return cls._copy_context_value(update)

        if isinstance(base, set) and isinstance(existing, set) and isinstance(update, set):
            if not update:
                return set()
            return (set(existing) - (set(base) - set(update))) | (set(update) - set(base))

        return cls._copy_context_value(update)

    @staticmethod
    def _merge_parallel_tool_outcomes(
        *,
        normalized_context: dict[str, Any],
        public_context: dict[str, Any],
        outcomes: list[_ToolExecutionOutcome],
    ) -> None:
        """Deterministically merge same-round tool outcomes back into context.

        Merge semantics:
        - Each tool call sees only the round-start snapshot.
        - Same-round tool calls are isolated from each other's writes.
        - Accepted context updates replay in original tool index order into
          both the runner state and the caller-visible public context.
        - ``tool_results`` are appended in that same deterministic order.
        """
        for outcome in outcomes:
            for key, update in outcome.context_updates.items():
                if not update.after_exists:
                    normalized_context.pop(key, None)
                    public_context.pop(key, None)
                    continue
                if not update.before_exists or key not in normalized_context:
                    normalized_context[key] = ToolLoopRunner._copy_context_value(
                        update.after_value,
                    )
                else:
                    normalized_context[key] = ToolLoopRunner._merge_context_value(
                        base=update.before_value,
                        existing=normalized_context[key],
                        update=update.after_value,
                        replaced_paths=update.replaced_paths,
                    )
                public_context[key] = copy.deepcopy(normalized_context[key])
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
            tuple(str(item).strip() for item in raw_target_container_keys if str(item).strip())
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

    @staticmethod
    def _resolve_scratchpad_task_refs(
        *,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> list[str]:
        explicit_refs = arguments.get("task_refs")
        if isinstance(explicit_refs, str) and explicit_refs.strip():
            return [explicit_refs.strip()]
        if isinstance(explicit_refs, (list, tuple)):
            normalized_refs = [
                str(value).strip() for value in explicit_refs if str(value or "").strip()
            ]
            if normalized_refs:
                return normalized_refs
        return [
            str(value).strip()
            for value in (
                context.get("resolved_requirement_id"),
                context.get("selected_requirement_id"),
                context.get("requirement_id"),
                context.get("_current_subgraph"),
            )
            if str(value or "").strip()
        ]

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
        scheduled_calls: list[_ScheduledToolCall] = []

        for tool_index, tool_call in enumerate(tool_calls, start=1):
            function_payload = tool_call.get("function") or {}
            tool_name = function_payload.get("name") or ""
            arguments = _coerce_tool_arguments(function_payload.get("arguments"))
            tool_call_id = tool_call.get("id") or f"{node_key}-tool-{tool_index}"
            metadata = self._resolve_tool_execution_metadata(
                tool_name=tool_name,
                arguments=arguments,
                context=round_context_snapshot,
            )
            scheduled_calls.append(
                _ScheduledToolCall(
                    index=tool_index - 1,
                    tool_name=tool_name,
                    tool_call_id=tool_call_id,
                    arguments=arguments,
                    metadata=metadata,
                )
            )

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

        outcomes: dict[int, _ToolExecutionOutcome] = {}
        pending_calls = list(scheduled_calls)
        active_calls: dict[int, _ScheduledToolCall] = {}
        cancellation_error: RuntimeError | None = None

        def start_worker(call: _ScheduledToolCall) -> None:
            tool_context = self._clone_parallel_context_snapshot(
                round_context_snapshot,
            )
            worker = threading.Thread(
                target=self._run_tool_worker,
                args=(
                    result_queue,
                    call.index,
                    call.tool_name,
                    call.tool_call_id,
                    call.arguments,
                    round_context_snapshot,
                    tool_context,
                ),
                name=f"tool-loop-{call.index + 1}",
                daemon=True,
            )
            active_calls[call.index] = call
            worker_threads.append(worker)
            worker.start()

        while pending_calls or active_calls:
            if cancellation_error is None:
                try:
                    self._raise_if_cancellation_requested(round_context_snapshot)
                except RuntimeError as exc:
                    cancellation_error = exc
                    pending_calls.clear()
            while (
                cancellation_error is None
                and pending_calls
                and len(active_calls) < self.max_concurrent_tool_calls_per_round
            ):
                try:
                    self._raise_if_cancellation_requested(round_context_snapshot)
                except RuntimeError as exc:
                    cancellation_error = exc
                    pending_calls.clear()
                    break
                selected_position: int | None = None
                for position, candidate in enumerate(pending_calls):
                    if self._can_start_tool_call(
                        candidate,
                        active_calls=list(active_calls.values()),
                        earlier_pending_calls=pending_calls[:position],
                    ):
                        selected_position = position
                        break
                if selected_position is None:
                    break
                start_worker(pending_calls.pop(selected_position))

            if not active_calls:
                if cancellation_error is not None:
                    break
                # The first pending call cannot conflict with an earlier call,
                # so this is only a defensive deadlock escape.
                start_worker(pending_calls.pop(0))

            try:
                item_type, index, payload = result_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            if item_type == "event":
                if cancellation_error is None:
                    call = active_calls.get(index)
                    if isinstance(payload, dict) and call is not None:
                        payload = dict(payload)
                        data = dict(payload.get("data") or {})
                        data.setdefault("tool_call_index", index)
                        data.setdefault("tool_call_id", call.tool_call_id)
                        data.setdefault("tool", call.tool_name)
                        payload["data"] = data
                    yield payload
                continue
            if item_type == "result":
                outcomes[index] = payload
                active_calls.pop(index, None)

        for worker in worker_threads:
            worker.join()

        if cancellation_error is not None:
            raise cancellation_error

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
        original_context_references = self._capture_context_references(
            tool_context,
        )
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
                    importance=arguments.get("importance"),
                    task_refs=self._resolve_scratchpad_task_refs(
                        arguments=arguments,
                        context=tool_context,
                    ),
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
                            original_context_references=original_context_references,
                        ),
                        phase_completion=phase_completion,
                    ),
                )
            )
        except BaseException as exc:
            result_queue.put(
                (
                    "result",
                    index,
                    _ToolExecutionOutcome(
                        tool_name=tool_name,
                        tool_call_id=tool_call_id,
                        arguments=arguments,
                        result={
                            "error": str(exc) or type(exc).__name__,
                            "is_error": True,
                        },
                        context_updates=self._extract_context_updates(
                            before=base_context,
                            after=tool_context,
                            original_context_references=original_context_references,
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
            run_ref = normalized_context.get("_agent_run_ref")
            bind_stage_run_ref = getattr(recorder, "bind_stage_run_ref", None)
            if isinstance(run_ref, dict) and callable(bind_stage_run_ref):
                bind_stage_run_ref(
                    node_key,
                    created_by=user_id,
                    run_ref=run_ref,
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
                    (t.get("function") or {}).get("name") == "scratchpad_write" for t in tools_list
                ):
                    tools_list = [*tools_list, _SCRATCHPAD_WRITE_TOOL_DEF]
            if self.enable_complete_phase:
                # Inject complete_phase tool for explicit phase completion signals
                if not any(
                    (t.get("function") or {}).get("name") == "complete_phase" for t in tools_list
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
            reasoning_content = str(response.get("reasoning_content") or "").strip()
            finish_reason = response.get("finish_reason")

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_content,
            }
            if reasoning_content:
                assistant_message["reasoning_content"] = reasoning_content
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
                                        "expand_topology": outcome.phase_completion[
                                            "expand_topology"
                                        ],
                                        "target_template_graph_id": outcome.phase_completion[
                                            "target_template_graph_id"
                                        ],
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
                        public_context=context,
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
                    output_summary["target_template_graph_id"] = phase_completion[
                        "target_template_graph_id"
                    ]
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
