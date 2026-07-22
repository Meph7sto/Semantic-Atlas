"""Regression tests for side-effect-aware ToolLoopRunner scheduling."""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Any

import pytest

os.environ["SKIP_DB_INIT"] = "1"

from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
from backend_business.services.agent.runtime import (
    ToolCapabilityExecutor,
    ToolExecutionMetadata,
)
from backend_business.services.agent.tools.requirement_agent_tools import (
    RequirementAgentTools,
)


class _Recorder:
    graph_id = "graph-scheduling"

    def __init__(self) -> None:
        self.tool_results: list[dict[str, Any]] = []

    @staticmethod
    def stage_node_key(node_key: str) -> str:
        return node_key

    @staticmethod
    def stage_label(label: str) -> str:
        return label

    def start_stage(self, **kwargs: Any) -> None:
        return None

    def complete_stage(self, *args: Any, **kwargs: Any) -> None:
        return None

    def record_tool_call_result(self, *args: Any, **kwargs: Any) -> None:
        self.tool_results.append(dict(kwargs))


class _PromptBuilder:
    @staticmethod
    def build_system_prompt(*, context: dict[str, Any]) -> str:
        return "system"

    @staticmethod
    def build_user_message(
        *,
        user_message: str,
        context: dict[str, Any],
    ) -> str:
        return user_message

    @staticmethod
    def build_round_input_summary(
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {"round": round_index}


class _AiProxy:
    def __init__(self, tool_calls: list[dict[str, Any]]) -> None:
        self._responses = [
            {
                "content": "",
                "tool_calls": tool_calls,
                "finish_reason": "tool_calls",
            },
            {"content": "done", "tool_calls": [], "finish_reason": "stop"},
        ]

    def chat_completion_with_tools(self, **kwargs: Any) -> dict[str, Any]:
        return self._responses.pop(0)


class _SchedulingProbeExecutor:
    def __init__(self, *, barrier_size: int | None = None) -> None:
        self._lock = threading.Lock()
        self._barrier = (
            threading.Barrier(barrier_size, timeout=1.0) if barrier_size is not None else None
        )
        self.active = 0
        self.max_active = 0
        self.active_by_resource: dict[str, int] = {}
        self.max_active_by_resource: dict[str, int] = {}
        self.trace: list[tuple[str, int]] = []

    @staticmethod
    def get_tools_list() -> list[dict[str, Any]]:
        return [
            {
                "type": "function",
                "function": {
                    "name": "probe",
                    "parameters": {"type": "object"},
                },
            }
        ]

    @staticmethod
    def get_tool_execution_metadata(
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> ToolExecutionMetadata:
        return ToolExecutionMetadata(
            read_only=bool(arguments.get("read_only")),
            idempotent=bool(arguments.get("idempotent")),
            resource_key=arguments.get("resource_key"),
            concurrency_group=arguments.get("concurrency_group"),
        )

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        index = int(arguments["index"])
        resource_key = str(arguments.get("resource_key") or "global")
        with self._lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
            resource_active = self.active_by_resource.get(resource_key, 0) + 1
            self.active_by_resource[resource_key] = resource_active
            self.max_active_by_resource[resource_key] = max(
                self.max_active_by_resource.get(resource_key, 0),
                resource_active,
            )
            self.trace.append(("start", index))

        try:
            if arguments.get("wait_at_barrier") and self._barrier is not None:
                self._barrier.wait()
            time.sleep(float(arguments.get("delay", 0.01)))
            return {"index": index, "resource_key": resource_key}
        finally:
            with self._lock:
                self.trace.append(("finish", index))
                self.active -= 1
                self.active_by_resource[resource_key] -= 1


def _tool_call(index: int, **arguments: Any) -> dict[str, Any]:
    return {
        "id": f"call-{index}",
        "type": "function",
        "function": {
            "name": "probe",
            "arguments": json.dumps({"index": index, **arguments}),
        },
    }


def _run_tool_loop(
    *,
    executor: Any,
    tool_calls: list[dict[str, Any]],
    max_concurrent: int = 4,
    context: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], Any, _Recorder]:
    recorder = _Recorder()
    runner = ToolLoopRunner(
        ai_proxy_client=_AiProxy(tool_calls),
        tool_executor=executor,
        prompt_builder=_PromptBuilder(),
        max_tool_call_rounds=2,
        max_concurrent_tool_calls_per_round=max_concurrent,
    )
    generator = runner.run(
        recorder=recorder,
        user_id="user-1",
        user_message="test scheduling",
        context=context or {"project_id": "project-1", "tool_results": []},
    )
    events: list[dict[str, Any]] = []
    while True:
        try:
            events.append(next(generator))
        except StopIteration as stop:
            return events, stop.value, recorder


def test_same_resource_writes_are_serialized_in_model_order() -> None:
    executor = _SchedulingProbeExecutor()
    calls = [
        _tool_call(
            index,
            read_only=False,
            idempotent=False,
            resource_key="requirement:req-1",
            concurrency_group="requirements",
            delay=0.02,
        )
        for index in range(3)
    ]

    _events, result, recorder = _run_tool_loop(
        executor=executor,
        tool_calls=calls,
    )

    assert executor.max_active_by_resource["requirement:req-1"] == 1
    assert executor.trace == [
        ("start", 0),
        ("finish", 0),
        ("start", 1),
        ("finish", 1),
        ("start", 2),
        ("finish", 2),
    ]
    assert [item["result"]["index"] for item in result.context["tool_results"]] == [
        0,
        1,
        2,
    ]
    assert [item["result_payload"]["index"] for item in recorder.tool_results] == [
        0,
        1,
        2,
    ]


def test_safe_reads_for_different_requirements_still_run_in_parallel() -> None:
    executor = _SchedulingProbeExecutor(barrier_size=2)
    calls = [
        _tool_call(
            index,
            read_only=True,
            idempotent=True,
            resource_key=f"requirement:req-{index}",
            concurrency_group="requirements",
            wait_at_barrier=True,
        )
        for index in range(2)
    ]

    _events, result, _recorder = _run_tool_loop(
        executor=executor,
        tool_calls=calls,
    )

    assert executor.max_active == 2
    assert not any(item["result"].get("is_error") for item in result.context["tool_results"])


def test_same_resource_writes_serialize_across_concurrency_groups() -> None:
    executor = _SchedulingProbeExecutor()
    calls = [
        _tool_call(
            0,
            read_only=False,
            resource_key="requirement:req-1",
            concurrency_group="writes-a",
        ),
        _tool_call(
            1,
            read_only=False,
            resource_key="requirement:req-1",
            concurrency_group="writes-b",
        ),
    ]

    _events, _result, _recorder = _run_tool_loop(
        executor=executor,
        tool_calls=calls,
    )

    assert executor.max_active_by_resource["requirement:req-1"] == 1


def test_undeclared_write_is_a_global_barrier_for_declared_calls() -> None:
    executor = _SchedulingProbeExecutor()
    calls = [
        _tool_call(0),
        _tool_call(
            1,
            read_only=True,
            idempotent=True,
            resource_key="requirement:req-2",
            concurrency_group="reads",
        ),
    ]

    _events, _result, _recorder = _run_tool_loop(
        executor=executor,
        tool_calls=calls,
    )

    assert executor.max_active == 1


class _NestedContextExecutor(_SchedulingProbeExecutor):
    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        index = int(arguments["index"])
        context["nested"]["seen"].append(index)
        context["resolved_requirement_ids"].add(f"req-{index}")
        return super().execute(tool_name, arguments, context)


def test_parallel_nested_context_updates_are_isolated_and_merged_deterministically() -> None:
    executor = _NestedContextExecutor(barrier_size=2)
    calls = [
        _tool_call(
            index,
            read_only=True,
            idempotent=True,
            resource_key=f"requirement:req-{index}",
            wait_at_barrier=True,
        )
        for index in range(2)
    ]

    public_context = {
        "project_id": "project-1",
        "tool_results": [],
        "nested": {"seen": []},
        "resolved_requirement_ids": set(),
    }
    _events, result, _recorder = _run_tool_loop(
        executor=executor,
        tool_calls=calls,
        context=public_context,
    )

    assert result.context["nested"] == {"seen": [0, 1]}
    assert result.context["resolved_requirement_ids"] == {"req-0", "req-1"}
    assert public_context["nested"] == {"seen": [0, 1]}
    assert public_context["resolved_requirement_ids"] == {"req-0", "req-1"}


class _ContextMutationExecutor(_SchedulingProbeExecutor):
    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        mode = arguments["mode"]
        if mode == "mutate":
            context["items"].append("first")
            context["settings"]["first"] = True
            context["nested"]["items"].append("first")
            context["nested"]["settings"]["first"] = True
            context["labels"].add("first")
        elif mode == "replace":
            context["items"] = ["replacement"]
            context["settings"] = {"replacement": True}
            context["nested"]["items"] = ["replacement"]
            context["nested"]["settings"] = {"replacement": True}
            context["labels"] = {"replacement"}
            context.pop("obsolete")
        elif mode == "clear":
            context["items"].clear()
            context["settings"].clear()
            context["nested"]["items"].clear()
            context["nested"]["settings"].clear()
            context["labels"].clear()
            del context["obsolete"]
        else:
            raise AssertionError(f"unexpected mutation mode: {mode}")
        return super().execute(tool_name, arguments, context)


def _mutable_context() -> dict[str, Any]:
    return {
        "project_id": "project-1",
        "tool_results": [],
        "items": ["base"],
        "settings": {"base": True},
        "nested": {
            "items": ["base"],
            "settings": {"base": True},
        },
        "labels": {"base"},
        "obsolete": "remove-me",
    }


def test_later_explicit_replacements_win_in_deterministic_model_order() -> None:
    executor = _ContextMutationExecutor(barrier_size=2)
    public_context = _mutable_context()
    calls = [
        _tool_call(
            0,
            mode="mutate",
            read_only=True,
            idempotent=True,
            resource_key="resource:first",
            wait_at_barrier=True,
            delay=0.03,
        ),
        _tool_call(
            1,
            mode="replace",
            read_only=True,
            idempotent=True,
            resource_key="resource:replacement",
            wait_at_barrier=True,
        ),
    ]

    _events, result, _recorder = _run_tool_loop(
        executor=executor,
        tool_calls=calls,
        context=public_context,
    )

    expected_nested = {
        "items": ["replacement"],
        "settings": {"replacement": True},
    }
    assert executor.max_active == 2
    assert result.context["items"] == ["replacement"]
    assert result.context["settings"] == {"replacement": True}
    assert result.context["nested"] == expected_nested
    assert result.context["labels"] == {"replacement"}
    assert "obsolete" not in result.context
    assert public_context["items"] == ["replacement"]
    assert public_context["settings"] == {"replacement": True}
    assert public_context["nested"] == expected_nested
    assert public_context["labels"] == {"replacement"}
    assert "obsolete" not in public_context


def test_single_tool_can_clear_collections_and_delete_context_keys() -> None:
    public_context = _mutable_context()

    _events, result, _recorder = _run_tool_loop(
        executor=_ContextMutationExecutor(),
        tool_calls=[_tool_call(0, mode="clear")],
        context=public_context,
    )

    assert result.context["items"] == []
    assert result.context["settings"] == {}
    assert result.context["nested"] == {"items": [], "settings": {}}
    assert result.context["labels"] == set()
    assert "obsolete" not in result.context
    assert public_context["items"] == []
    assert public_context["settings"] == {}
    assert public_context["nested"] == {"items": [], "settings": {}}
    assert public_context["labels"] == set()
    assert "obsolete" not in public_context


class _CancellableStreamingExecutor:
    def __init__(self) -> None:
        self.started: list[int] = []
        self.release = threading.Event()

    @staticmethod
    def get_tools_list(context=None) -> list[dict[str, Any]]:
        return []

    @staticmethod
    def get_tool_execution_metadata(tool_name, arguments, context):
        return ToolExecutionMetadata(
            read_only=False,
            resource_key=f"resource:{arguments['index']}",
        )

    def execute_streaming(self, tool_name, arguments, context):
        index = int(arguments["index"])
        self.started.append(index)
        context["worker_updates"].append(index)
        yield {"event": "tool_started", "data": {"index": index}}
        self.release.wait(timeout=1)
        return {"index": index}


def test_cancellation_does_not_start_pending_calls_in_current_round() -> None:
    cancellation = threading.Event()
    executor = _CancellableStreamingExecutor()
    runner = ToolLoopRunner(
        ai_proxy_client=_AiProxy([_tool_call(0), _tool_call(1)]),
        tool_executor=executor,
        prompt_builder=_PromptBuilder(),
        max_tool_call_rounds=2,
        max_concurrent_tool_calls_per_round=1,
    )
    public_context = {
        "tool_results": [],
        "worker_updates": [],
        "_runtime_cancel_event": cancellation,
    }
    generator = runner.run(
        recorder=_Recorder(),
        user_id="user-1",
        user_message="cancel scheduling",
        context=public_context,
    )
    while True:
        event = next(generator)
        if event["event"] == "tool_started":
            break

    cancellation.set()
    executor.release.set()
    with pytest.raises(RuntimeError, match="cancelled"):
        list(generator)

    assert executor.started == [0]
    assert public_context["worker_updates"] == []


def test_undeclared_side_effects_use_conservative_serial_fallback() -> None:
    executor = _SchedulingProbeExecutor()

    _events, _result, _recorder = _run_tool_loop(
        executor=executor,
        tool_calls=[_tool_call(0), _tool_call(1)],
    )

    assert executor.max_active == 1
    assert executor.trace == [
        ("start", 0),
        ("finish", 0),
        ("start", 1),
        ("finish", 1),
    ]


def test_round_cap_and_tool_result_order_are_deterministic() -> None:
    executor = _SchedulingProbeExecutor()
    calls = [
        _tool_call(
            index,
            read_only=True,
            idempotent=True,
            resource_key=f"requirement:req-{index}",
            concurrency_group="requirements",
            delay=(5 - index) * 0.01,
        )
        for index in range(5)
    ]

    events, result, recorder = _run_tool_loop(
        executor=executor,
        tool_calls=calls,
        max_concurrent=2,
    )

    assert executor.max_active == 2
    assert [item["result"]["index"] for item in result.context["tool_results"]] == [
        0,
        1,
        2,
        3,
        4,
    ]
    assert [item["result_payload"]["index"] for item in recorder.tool_results] == [
        0,
        1,
        2,
        3,
        4,
    ]
    result_events = [event for event in events if event["event"] == "tool_result"]
    assert [event["data"]["result"]["index"] for event in result_events] == [
        0,
        1,
        2,
        3,
        4,
    ]


def test_requirement_write_metadata_uses_requirement_resource_key() -> None:
    metadata = RequirementAgentTools.get_tool_execution_metadata(
        "update_requirement_content",
        {"requirement_id": "req-42", "updates": {"title": "new"}},
        {"project_id": "project-1"},
    )

    assert metadata == ToolExecutionMetadata(
        read_only=False,
        idempotent=False,
        resource_key="requirement:project-1:req-42",
        concurrency_group="requirements",
    )


def test_capability_wrapper_preserves_tool_execution_metadata() -> None:
    executor = _SchedulingProbeExecutor()
    wrapped = ToolCapabilityExecutor(
        tool_executor=executor,
        allowed_tool_names={"probe"},
        policy_id="test-policy",
    )

    metadata = wrapped.get_tool_execution_metadata(
        "probe",
        {
            "read_only": True,
            "idempotent": True,
            "resource_key": "requirement:req-1",
            "concurrency_group": "requirements",
        },
        {},
    )

    assert metadata.read_only is True
    assert metadata.idempotent is True
    assert metadata.resource_key == "requirement:req-1"
    assert metadata.concurrency_group == "requirements"
