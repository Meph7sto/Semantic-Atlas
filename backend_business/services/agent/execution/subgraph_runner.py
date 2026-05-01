"""Subgraph-level runtime execution engine.

Drives the runtime execution graph forward on a per-subgraph basis.

This module defines:
- SubgraphPromptBuilder  — generates prompts for llm subgraphs
- SubgraphRunner         — orchestrates run / resume / advance / route
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import queue
import threading
from typing import Any

from backend_business.services.agent.runtime.context import ExecutionContext
from backend_business.services.agent.runtime.scratchpad import Scratchpad
from backend_business.services.agent.runtime.agent_runtime import (
    AgentRunResult,
    AgentRuntimeRegistry,
    RunRequest,
)
from backend_business.services.agent.runtime.tool_capability import (
    ToolCapabilityExecutor,
)
from backend_business.services.agent.experience import (
    ExperienceOrchestrator,
    ExperiencePolicyResolver,
    ExperienceTarget,
    SkillLoader,
    SkillRegistry,
    SkillRetriever,
    resolve_experience_target_from_subgraph,
)

from .subgraph_state import (
    ContainerExecutionError,
    SubgraphStatus,
    SuspendSignal,
    validate_subgraph_transition,
)
from .prompt_interface import PromptBuilderFactory, PromptBuilderProtocol
from .tool_loop_runner import ToolLoopRunner, ToolLoopResult
from .topology_instantiator import (
    RuntimeContainer,
    RuntimeEdge,
    RuntimeGraphSkeleton,
    RuntimeSubgraph,
)


# ---------------------------------------------------------------------------
# Execution result
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContainerResult:
    """Outcome of executing a single container's subgraph sequence."""

    conclusion: Any
    """Last subgraph's complete_phase conclusion (return-edge payload)."""

    scratchpad_snapshot: list[dict[str, Any]]
    """Serialised entries for the executed container's scratchpad."""

    scratchpad_store_snapshot: list[dict[str, Any]]
    """Serialised entries for every container's scratchpad."""


@dataclass(frozen=True)
class _InvokeBranchResult:
    call_edge: RuntimeEdge
    target_container: RuntimeContainer
    result: ContainerResult


@dataclass(frozen=True)
class _InvokeBranchRuntimeHandle:
    runtime: Any
    agent_run_id: str


# ---------------------------------------------------------------------------
# Prompt builder for llm subgraphs
# ---------------------------------------------------------------------------


class SubgraphPromptBuilder:
    """Builds system / user prompts for a single llm subgraph.

    The system prompt injects the subgraph's ``task_description`` and the
    current scratchpad context.  The user message simply passes through the
    original user message (or an empty string when a prior context already
    provides sufficient information).
    """

    def __init__(
        self,
        *,
        task_description: str,
        scratchpad: Scratchpad,
        extra_system_context: str = "",
    ) -> None:
        self._task_description = task_description
        self._scratchpad = scratchpad
        self._extra_system_context = extra_system_context

    # -- PromptBuilderProtocol ------------------------------------------------

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        parts: list[str] = []
        if self._task_description:
            parts.append(f"## 当前阶段任务\n\n{self._task_description}")
        pad_text = self._scratchpad.format_for_prompt()
        if pad_text:
            parts.append(f"\n\n{pad_text}")
        execution_context = context.get("_execution_context")
        if execution_context is not None:
            local_context_text = execution_context.format_local_for_prompt(
                context.get("_current_subgraph"),
            )
            if local_context_text:
                parts.append(f"\n\n{local_context_text}")
        if self._extra_system_context:
            parts.append(f"\n\n{self._extra_system_context}")
        return "\n".join(parts)

    def build_user_message(
        self, *, user_message: str, context: dict[str, Any]
    ) -> str:
        return user_message

    def build_round_input_summary(
        self,
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "round": round_index,
            "subgraph_key": context.get("_current_subgraph", ""),
        }


# ---------------------------------------------------------------------------
# Mutable status tracker
# ---------------------------------------------------------------------------


class _SubgraphStatusTracker:
    """In-memory mutable status map for subgraphs within a single run.

    Stores ``SubgraphStatus`` keyed by ``subgraph_id``.  The runner
    updates this map and persists changes via the graph_service at each
    transition.
    """

    def __init__(self) -> None:
        self._statuses: dict[str, SubgraphStatus] = {}
        self._lock = threading.RLock()

    def init(self, subgraph_id: str, status: SubgraphStatus) -> None:
        with self._lock:
            self._statuses[subgraph_id] = status

    def get(self, subgraph_id: str) -> SubgraphStatus:
        with self._lock:
            return self._statuses.get(subgraph_id, SubgraphStatus.PENDING)

    def transition(
        self, subgraph_id: str, target: SubgraphStatus
    ) -> None:
        with self._lock:
            current = self._statuses.get(subgraph_id, SubgraphStatus.PENDING)
            if not validate_subgraph_transition(current, target):
                raise ValueError(
                    f"非法状态转移: {current.value} → {target.value} "
                    f"(subgraph {subgraph_id})"
                )
            self._statuses[subgraph_id] = target


# ---------------------------------------------------------------------------
# SubgraphRunner
# ---------------------------------------------------------------------------


class SubgraphRunner:
    """Drives the runtime execution graph forward one subgraph at a time.

    The runner is **agent-agnostic**: it does not know anything about the
    business semantics of the topology graph.  All behaviour differences
    are expressed through ``task_description`` (injected into the LLM
    prompt) and the externally-provided ``tool_executor``.

    Usage::

        runner = SubgraphRunner()
        events = runner.run(
            skeleton=skeleton,
            tool_executor=my_tools,
            ai_proxy_client=ai,
            recorder=recorder,
            actor="user-123",
            user_message="请检测需求冲突",
        )
        for event in events:
            send_to_client(event)
    """

    def __init__(
        self,
        *,
        agent_runtime_registry: AgentRuntimeRegistry | None = None,
        experience_orchestrator: ExperienceOrchestrator | None = None,
        experience_retriever: SkillRetriever | None = None,
        skill_loader: SkillLoader | None = None,
        skill_registry: SkillRegistry | None = None,
        policies: ExperiencePolicyResolver | None = None,
        prompt_builder_factory: PromptBuilderFactory | None = None,
    ) -> None:
        self._agent_runtime_registry = agent_runtime_registry
        self._experience_orchestrator = experience_orchestrator
        self._experience_retriever = experience_retriever or SkillRetriever()
        self._skill_loader = skill_loader or SkillLoader()
        self._skill_registry = skill_registry or SkillRegistry(self._experience_retriever.root_path)
        self._policies = policies or ExperiencePolicyResolver()
        self._prompt_builder_factory = prompt_builder_factory

    # -- public API -----------------------------------------------------------

    def run(
        self,
        *,
        skeleton: RuntimeGraphSkeleton,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None = None,
        recorder: Any,
        actor: str,
        user_message: str = "",
        scratchpad: Scratchpad | None = None,
    ) -> Generator[dict[str, Any], None, ContainerResult]:
        """Execute the graph from the entry container's first pending subgraph.

        Yields SSE-style event dicts and returns a ``ContainerResult``.
        """
        tracker = _SubgraphStatusTracker()
        for sg in skeleton.subgraphs:
            tracker.init(sg.subgraph_id, SubgraphStatus.PENDING)

        entry_container = skeleton.get_entry_container()
        return (yield from self._execute_container(
            container=entry_container,
            skeleton=skeleton,
            tool_executor=tool_executor,
            ai_proxy_client=ai_proxy_client,
            graph_service=graph_service,
            recorder=recorder,
            actor=actor,
            user_message=user_message,
            tracker=tracker,
            pad=scratchpad,
        ))

    def resume(
        self,
        *,
        skeleton: RuntimeGraphSkeleton,
        suspended_subgraph_id: str,
        user_input: str,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None = None,
        recorder: Any,
        actor: str,
        scratchpad: Scratchpad | None = None,
    ) -> Generator[dict[str, Any], None, ContainerResult]:
        """Resume execution from a previously suspended handoff subgraph.

        The suspended subgraph is marked completed with the user_input
        injected into the scratchpad, then execution continues from the
        next subgraph.
        """
        tracker = _SubgraphStatusTracker()
        for sg in skeleton.subgraphs:
            if sg.subgraph_id == suspended_subgraph_id:
                # handoff was left in RUNNING
                tracker.init(sg.subgraph_id, SubgraphStatus.RUNNING)
            else:
                tracker.init(
                    sg.subgraph_id,
                    SubgraphStatus.COMPLETED
                    if sg.order_index < _find_subgraph(skeleton, suspended_subgraph_id).order_index
                    and sg.container_id == _find_subgraph(skeleton, suspended_subgraph_id).container_id
                    else SubgraphStatus.PENDING,
                )

        suspended_sg = _find_subgraph(skeleton, suspended_subgraph_id)
        container = _find_container(skeleton, suspended_sg.container_id)
        subgraphs = skeleton.get_subgraphs_for_container(container.container_id)

        # Create scratchpad and inject user input
        root_pad = scratchpad if scratchpad is not None else Scratchpad()
        pad = root_pad.for_container(container.container_key)
        execution_context = ExecutionContext(scratchpad=pad)
        pad.append_stage_output(
            suspended_sg.subgraph_key,
            f"[用户输入] {user_input}",
        )

        # Mark suspended handoff as completed
        tracker.transition(suspended_subgraph_id, SubgraphStatus.COMPLETED)

        # Find next subgraph after the suspended one
        next_sg = self._resolve_next_subgraph(
            current_sg=suspended_sg,
            route_key=None,
            container_subgraphs=subgraphs,
            skeleton=skeleton,
        )

        if next_sg is None:
            return ContainerResult(
                conclusion=user_input,
                scratchpad_snapshot=pad.snapshot(),
                scratchpad_store_snapshot=pad.snapshot_all(),
            )

        # Continue from the next subgraph
        return (yield from self._continue_from(
            start_sg=next_sg,
            container_subgraphs=subgraphs,
            container=container,
            skeleton=skeleton,
            tool_executor=tool_executor,
            ai_proxy_client=ai_proxy_client,
            graph_service=graph_service,
            recorder=recorder,
            actor=actor,
            user_message=user_input,
            tracker=tracker,
            pad=pad,
            execution_context=execution_context,
            runtime_context=None,
        ))

    # -- container-level orchestration ----------------------------------------

    def _execute_container(
        self,
        *,
        container: RuntimeContainer,
        skeleton: RuntimeGraphSkeleton,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None,
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        pad: Scratchpad | None = None,
        runtime_context: dict[str, Any] | None = None,
    ) -> Generator[dict[str, Any], None, ContainerResult]:
        """Execute all subgraphs in *container* sequentially."""
        runtime_pad = (
            (pad if pad is not None else Scratchpad()).for_container(container.container_key)
        )
        execution_context = ExecutionContext(scratchpad=runtime_pad)
        subgraphs = skeleton.get_subgraphs_for_container(container.container_id)
        if not subgraphs:
            return ContainerResult(
                conclusion="",
                scratchpad_snapshot=[],
                scratchpad_store_snapshot=runtime_pad.snapshot_all(),
            )

        first_sg = subgraphs[0]
        return (yield from self._continue_from(
            start_sg=first_sg,
            container_subgraphs=subgraphs,
            container=container,
            skeleton=skeleton,
            tool_executor=tool_executor,
            ai_proxy_client=ai_proxy_client,
            graph_service=graph_service,
            recorder=recorder,
            actor=actor,
            user_message=user_message,
            tracker=tracker,
            pad=runtime_pad,
            execution_context=execution_context,
            runtime_context=runtime_context,
        ))

    def _continue_from(
        self,
        *,
        start_sg: RuntimeSubgraph,
        container_subgraphs: list[RuntimeSubgraph],
        container: RuntimeContainer,
        skeleton: RuntimeGraphSkeleton,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None,
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        pad: Scratchpad,
        execution_context: ExecutionContext,
        runtime_context: dict[str, Any] | None,
    ) -> Generator[dict[str, Any], None, ContainerResult]:
        """Drive subgraphs starting from *start_sg* until no more remain."""
        last_conclusion: Any = ""
        current_sg: RuntimeSubgraph | None = start_sg

        while current_sg is not None:
            _raise_if_runtime_cancelled(runtime_context)
            # Transition Pending → Running
            tracker.transition(current_sg.subgraph_id, SubgraphStatus.RUNNING)
            yield {
                "event": "subgraph_status",
                "data": {
                    "subgraph_id": current_sg.subgraph_id,
                    "status": "running",
                },
            }

            try:
                route_key = yield from self._advance_subgraph(
                    sg=current_sg,
                    container=container,
                    skeleton=skeleton,
                    pad=pad,
                    tool_executor=tool_executor,
                    ai_proxy_client=ai_proxy_client,
                    graph_service=graph_service,
                    recorder=recorder,
                    actor=actor,
                    user_message=user_message,
                    tracker=tracker,
                    execution_context=execution_context,
                    runtime_context=runtime_context,
                )
                # _advance_subgraph transitions to COMPLETED internally
                last_conclusion = (
                    _latest_stage_output(pad) or last_conclusion
                )
                yield {
                    "event": "subgraph_status",
                    "data": {
                        "subgraph_id": current_sg.subgraph_id,
                        "status": "completed",
                    },
                }
            except SuspendSignal:
                # handoff — propagate upward, do not mark completed
                raise
            except Exception as exc:
                tracker.transition(
                    current_sg.subgraph_id, SubgraphStatus.FAILED
                )
                yield {
                    "event": "subgraph_status",
                    "data": {
                        "subgraph_id": current_sg.subgraph_id,
                        "status": "failed",
                    },
                }
                raise ContainerExecutionError(
                    container_id=container.container_id,
                    subgraph_id=current_sg.subgraph_id,
                    cause=exc,
                ) from exc

            _raise_if_runtime_cancelled(runtime_context)
            next_sg = self._resolve_next_subgraph(
                current_sg=current_sg,
                route_key=route_key,
                container_subgraphs=container_subgraphs,
                skeleton=skeleton,
            )
            if next_sg is not None:
                _ensure_runtime_transition_edge(
                    graph_service=_resolve_graph_service(
                        graph_service=graph_service,
                        recorder=recorder,
                    ),
                    graph_id=skeleton.graph_id,
                    skeleton=skeleton,
                    source_subgraph=current_sg,
                    target_subgraph=next_sg,
                    actor=actor,
                    route_key=route_key,
                )
            current_sg = next_sg

        return ContainerResult(
            conclusion=last_conclusion,
            scratchpad_snapshot=pad.snapshot(),
            scratchpad_store_snapshot=pad.snapshot_all(),
        )

    # -- single-subgraph advance ----------------------------------------------

    def _advance_subgraph(
        self,
        *,
        sg: RuntimeSubgraph,
        container: RuntimeContainer,
        skeleton: RuntimeGraphSkeleton,
        pad: Scratchpad,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None,
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        execution_context: ExecutionContext,
        runtime_context: dict[str, Any] | None,
    ) -> Generator[dict[str, Any], None, str | None]:
        """Advance a single subgraph.  Returns ``route_key`` (may be None).

        Raises ``SuspendSignal`` for handoff subgraphs.
        """
        node_type = sg.node_type
        if node_type == "llm":
            return (yield from self._advance_llm(
                sg=sg,
                container=container,
                skeleton=skeleton,
                pad=pad,
                tool_executor=tool_executor,
                ai_proxy_client=ai_proxy_client,
                graph_service=graph_service,
                recorder=recorder,
                actor=actor,
                user_message=user_message,
                tracker=tracker,
                execution_context=execution_context,
                runtime_context=runtime_context,
            ))
        elif node_type == "invoke":
            return (yield from self._advance_invoke(
                sg=sg,
                container=container,
                skeleton=skeleton,
                pad=pad,
                tool_executor=tool_executor,
                ai_proxy_client=ai_proxy_client,
                graph_service=graph_service,
                recorder=recorder,
                actor=actor,
                user_message=user_message,
                tracker=tracker,
                execution_context=execution_context,
            ))
        elif node_type == "handoff":
            self._advance_handoff(sg)
            return None  # unreachable — _advance_handoff always raises
        else:
            raise ValueError(f"未知的 node_type: {node_type}")

    def _advance_llm(
        self,
        *,
        sg: RuntimeSubgraph,
        container: RuntimeContainer,
        skeleton: RuntimeGraphSkeleton,
        pad: Scratchpad,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None,
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        execution_context: ExecutionContext,
        runtime_context: dict[str, Any] | None,
    ) -> Generator[dict[str, Any], None, str | None]:
        """Execute an llm subgraph via AgentRuntime."""
        execution_context.begin_subgraph(sg.subgraph_key)
        runtime_registry = self._resolve_agent_runtime_registry(graph_service)
        runtime_binding = runtime_registry.resolve(
            container_key=container.container_key,
            agent_type=container.container_key or container.role_type or "agent",
            runtime_profile=str(
                _find_container_runtime_profile(
                    skeleton=skeleton,
                    container=container,
                )
                or "default"
            ),
        )
        runtime_tool_executor = self._resolve_runtime_tool_executor(
            container=container,
            tool_executor=tool_executor,
            runtime_binding=runtime_binding,
            runtime_context=runtime_context,
        )
        run_request = self._build_llm_run_request(
            sg=sg,
            container=container,
            skeleton=skeleton,
            pad=pad,
            tool_executor=runtime_tool_executor,
            ai_proxy_client=ai_proxy_client,
            graph_service=graph_service,
            recorder=recorder,
            actor=actor,
            user_message=user_message,
            execution_context=execution_context,
            runtime_context=runtime_context,
            runtime_binding=runtime_binding,
        )
        agent_run_id = runtime_binding.runtime.submit(run_request)
        for event in runtime_binding.runtime.stream(agent_run_id):
            yield event
        runtime_result = runtime_binding.runtime.await_result(agent_run_id)
        if runtime_result.status != "succeeded":
            raise ContainerExecutionError(
                container_id=container.container_id,
                subgraph_id=sg.subgraph_id,
                cause=RuntimeError(runtime_result.error_message or runtime_result.status),
                agent_run_id=agent_run_id,
                error_code=runtime_result.error_code,
            )

        runtime_payload = (
            dict(runtime_result.return_payload or {})
            if isinstance(runtime_result.return_payload, dict)
            else {}
        )
        output = runtime_payload.get("output")
        execution_context.end_subgraph(
            sg.subgraph_key,
            output=output,
        )
        tracker.transition(sg.subgraph_id, SubgraphStatus.COMPLETED)
        return str(runtime_payload.get("route_key") or "").strip() or None

    def _advance_invoke(
        self,
        *,
        sg: RuntimeSubgraph,
        container: RuntimeContainer,
        skeleton: RuntimeGraphSkeleton,
        pad: Scratchpad,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None,
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        execution_context: ExecutionContext,
    ) -> Generator[dict[str, Any], None, str | None]:
        """Execute an invoke subgraph, fan-outing over every call edge in parallel."""
        outgoing = skeleton.get_outgoing_edges(sg.subgraph_id)
        call_edges = sorted(
            (edge for edge in outgoing if edge.edge_type == "call"),
            key=lambda edge: (edge.order_index, edge.edge_id),
        )
        if not call_edges:
            raise ValueError(
                f"invoke subgraph '{sg.subgraph_key}' 缺少 call 出边"
            )

        target_containers: list[tuple[RuntimeEdge, RuntimeContainer]] = []
        seen_target_containers: set[str] = set()
        for call_edge in call_edges:
            target_sg = _find_subgraph_by_node_id(skeleton, call_edge.target_node_id)
            target_container = _find_container(skeleton, target_sg.container_id)
            if target_container.container_id in seen_target_containers:
                raise ValueError(
                    f"invoke subgraph '{sg.subgraph_key}' 指向了重复的目标容器 "
                    f"'{target_container.container_key}'"
                )
            seen_target_containers.add(target_container.container_id)
            target_containers.append((call_edge, target_container))

        caller_sg = _find_latest_completed_subgraph_in_container(
            skeleton=skeleton,
            container=container,
            current_subgraph=sg,
            tracker=tracker,
        )
        invoke_request = _resolve_invoke_request(
            current_sg=sg,
            caller_sg=caller_sg,
            execution_context=execution_context,
        )
        delegated_user_message = str(
            invoke_request.get("task_description") or user_message
        ).strip() or user_message
        invoke_payload = _build_invoke_payload_snapshot(
            invoke_request=invoke_request,
            delegated_user_message=delegated_user_message,
        )
        child_runtime_context = _build_invoke_runtime_context(
            invoke_request=invoke_request,
        )
        resolved_graph_service = _resolve_graph_service(
            graph_service=graph_service,
            recorder=recorder,
        )
        invoke_start_node_id = _find_subgraph_boundary_node_id(
            skeleton,
            sg.subgraph_id,
            "start",
        )
        invoke_end_node_id = _find_subgraph_boundary_node_id(
            skeleton,
            sg.subgraph_id,
            "end",
        )
        _ensure_runtime_edge(
            graph_service=resolved_graph_service,
            graph_id=skeleton.graph_id,
            source_node_id=invoke_start_node_id,
            target_node_id=invoke_end_node_id,
            edge_type="seq",
            label="seq",
            actor=actor,
            config_json={
                "runtime": True,
                "invoke_passthrough": True,
                "subgraph_key": sg.subgraph_key,
            },
        )

        branch_results = yield from self._execute_invoke_branches(
            target_containers=target_containers,
            skeleton=skeleton,
            tool_executor=tool_executor,
            ai_proxy_client=ai_proxy_client,
            graph_service=resolved_graph_service,
            recorder=recorder,
            actor=actor,
            user_message=delegated_user_message,
            tracker=tracker,
            pad=pad,
            runtime_context=child_runtime_context,
            invoke_payload=invoke_payload,
        )

        target_payloads: list[Any] = []
        for branch in branch_results:
            target_payloads.append(branch.result.conclusion)
            target_terminal_subgraph = _find_last_completed_subgraph_in_container(
                skeleton=skeleton,
                container=branch.target_container,
                tracker=tracker,
            )
            target_end_node_id = (
                _find_subgraph_boundary_node_id(
                    skeleton,
                    target_terminal_subgraph.subgraph_id,
                    "end",
                )
                if target_terminal_subgraph is not None
                else None
            )
            _ensure_runtime_edge(
                graph_service=resolved_graph_service,
                graph_id=skeleton.graph_id,
                source_node_id=target_end_node_id,
                target_node_id=invoke_end_node_id,
                edge_type="return",
                label="return",
                actor=actor,
                config_json={
                    "runtime": True,
                    "invoke_return": True,
                    "source_subgraph": (
                        target_terminal_subgraph.subgraph_key
                        if target_terminal_subgraph is not None
                        else None
                    ),
                    "target_subgraph": sg.subgraph_key,
                    "target_container_key": branch.target_container.container_key,
                },
            )

        controller_decision = _build_session_controller_invoke_decision(
            invoke_subgraph=sg,
            invoke_request=invoke_request,
            target_result=target_payloads[0] if len(target_payloads) == 1 else target_payloads,
        )
        pad.append_stage_output(
            sg.subgraph_key,
            json.dumps(controller_decision, ensure_ascii=False),
        )

        tracker.transition(sg.subgraph_id, SubgraphStatus.COMPLETED)
        return "suspend" if controller_decision.get("should_suspend") else "reply"

    def _execute_invoke_branches(
        self,
        *,
        target_containers: list[tuple[RuntimeEdge, RuntimeContainer]],
        skeleton: RuntimeGraphSkeleton,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None,
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        pad: Scratchpad,
        runtime_context: dict[str, Any] | None,
        invoke_payload: dict[str, Any],
    ) -> Generator[dict[str, Any], None, list[_InvokeBranchResult]]:
        result_queue: queue.Queue[tuple[str, int, Any]] = queue.Queue()
        branch_threads: list[threading.Thread] = []
        branch_stop_token = threading.Event()
        branch_runtime_context = dict(runtime_context or {})
        branch_runtime_context["_branch_stop_token"] = branch_stop_token
        branch_runtime_handles: dict[int, _InvokeBranchRuntimeHandle] = {}
        branch_runtime_handles_lock = threading.RLock()
        recorder_cursor = getattr(recorder, "capture_cursor", lambda: None)()
        runtime_registry = self._resolve_agent_runtime_registry(graph_service)

        for branch_index, (call_edge, target_container) in enumerate(target_containers):
            runtime_binding = runtime_registry.resolve(
                container_key=target_container.container_key,
                agent_type=target_container.container_key or target_container.role_type or "agent",
                runtime_profile=str(
                    (
                        _find_container_runtime_profile(
                            skeleton=skeleton,
                            container=target_container,
                        )
                        or "default"
                    )
                ),
            )
            worker = threading.Thread(
                target=self._run_container_worker,
                args=(
                    result_queue,
                    branch_index,
                    recorder_cursor,
                    call_edge,
                    target_container,
                    runtime_binding,
                    skeleton,
                    tool_executor,
                    ai_proxy_client,
                    graph_service,
                    recorder,
                    actor,
                    user_message,
                    tracker,
                    pad,
                    branch_runtime_context,
                    invoke_payload,
                    branch_stop_token,
                    branch_runtime_handles,
                    branch_runtime_handles_lock,
                ),
                name=f"invoke-{target_container.container_key or branch_index}",
                daemon=True,
            )
            worker.start()
            branch_threads.append(worker)

        results: dict[int, _InvokeBranchResult] = {}
        first_error: Exception | None = None
        completed_branches = 0

        while completed_branches < len(branch_threads):
            item_type, branch_index, payload = result_queue.get()
            if item_type == "event":
                yield payload
                continue
            if item_type == "submitted":
                continue
            completed_branches += 1
            if item_type == "error":
                if first_error is None:
                    first_error = payload
                    branch_stop_token.set()
                    self._cancel_pending_invoke_branches(
                        active_handles=branch_runtime_handles,
                        active_handles_lock=branch_runtime_handles_lock,
                        exclude_branch_index=branch_index,
                    )
                continue
            if item_type == "cancelled":
                continue
            results[branch_index] = payload

        for worker in branch_threads:
            worker.join()

        if first_error is not None:
            raise first_error

        return [results[index] for index in sorted(results)]

    @staticmethod
    def _cancel_pending_invoke_branches(
        *,
        active_handles: dict[int, _InvokeBranchRuntimeHandle],
        active_handles_lock: threading.RLock,
        exclude_branch_index: int | None = None,
    ) -> None:
        with active_handles_lock:
            handles = [
                handle
                for branch_index, handle in active_handles.items()
                if branch_index != exclude_branch_index
            ]
        for handle in handles:
            try:
                handle.runtime.cancel(handle.agent_run_id)
            except Exception:
                continue

    def _run_container_worker(
        self,
        result_queue: "queue.Queue[tuple[str, int, Any]]",
        branch_index: int,
        recorder_cursor: dict[str, Any] | None,
        call_edge: RuntimeEdge,
        target_container: RuntimeContainer,
        runtime_binding: Any,
        skeleton: RuntimeGraphSkeleton,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None,
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        pad: Scratchpad,
        runtime_context: dict[str, Any] | None,
        invoke_payload: dict[str, Any],
        branch_stop_token: threading.Event,
        branch_runtime_handles: dict[int, _InvokeBranchRuntimeHandle],
        branch_runtime_handles_lock: threading.RLock,
    ) -> None:
        bind_cursor = getattr(recorder, "bind_cursor", None)
        if callable(bind_cursor):
            bind_cursor(recorder_cursor)

        try:
            if branch_stop_token.is_set():
                result_queue.put(("cancelled", branch_index, None))
                return
            self._annotate_call_edge(
                graph_service=graph_service,
                call_edge=call_edge,
                actor=actor,
                target_container=target_container,
                invoke_payload=invoke_payload,
            )
            run_request = self._build_container_run_request(
                target_container=target_container,
                runtime_binding=runtime_binding,
                call_edge=call_edge,
                skeleton=skeleton,
                tool_executor=tool_executor,
                ai_proxy_client=ai_proxy_client,
                graph_service=graph_service,
                recorder=recorder,
                actor=actor,
                user_message=user_message,
                tracker=tracker,
                pad=pad,
                runtime_context=runtime_context,
                invoke_payload=invoke_payload,
            )
            agent_run_id = runtime_binding.runtime.submit(run_request)
            with branch_runtime_handles_lock:
                branch_runtime_handles[branch_index] = _InvokeBranchRuntimeHandle(
                    runtime=runtime_binding.runtime,
                    agent_run_id=agent_run_id,
                )
            result_queue.put(("submitted", branch_index, agent_run_id))
            if branch_stop_token.is_set():
                runtime_binding.runtime.cancel(agent_run_id)
            for event in runtime_binding.runtime.stream(agent_run_id):
                if branch_stop_token.is_set():
                    runtime_binding.runtime.cancel(agent_run_id)
                result_queue.put(("event", branch_index, event))
            runtime_result = runtime_binding.runtime.await_result(agent_run_id)
            if runtime_result.status == "cancelled":
                result_queue.put(("cancelled", branch_index, runtime_result))
                return
            if runtime_result.status != "succeeded":
                raise ContainerExecutionError(
                    container_id=target_container.container_id,
                    subgraph_id=(
                        skeleton.get_subgraphs_for_container(target_container.container_id)[0].subgraph_id
                        if skeleton.get_subgraphs_for_container(target_container.container_id)
                        else ""
                    ),
                    cause=RuntimeError(runtime_result.error_message or runtime_result.status),
                    agent_run_id=agent_run_id,
                    error_code=runtime_result.error_code,
                )
            result_queue.put(
                (
                    "result",
                    branch_index,
                    _InvokeBranchResult(
                        call_edge=call_edge,
                        target_container=target_container,
                        result=runtime_result.return_payload,
                    ),
                )
            )
        except Exception as exc:
            result_queue.put(("error", branch_index, exc))
        finally:
            with branch_runtime_handles_lock:
                branch_runtime_handles.pop(branch_index, None)

    def _resolve_agent_runtime_registry(
        self,
        graph_service: Any | None,
    ) -> AgentRuntimeRegistry:
        if self._agent_runtime_registry is not None:
            return self._agent_runtime_registry
        return AgentRuntimeRegistry(execution_graph_service=graph_service)

    def _build_container_run_request(
        self,
        *,
        target_container: RuntimeContainer,
        runtime_binding: Any,
        call_edge: RuntimeEdge,
        skeleton: RuntimeGraphSkeleton,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None,
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        pad: Scratchpad,
        runtime_context: dict[str, Any] | None,
        invoke_payload: dict[str, Any],
    ) -> RunRequest:
        effective_runtime_context = dict(runtime_context or {})

        def _run_target_container() -> Generator[dict[str, Any], None, ContainerResult]:
            return self._execute_container(
                container=target_container,
                skeleton=skeleton,
                tool_executor=tool_executor,
                ai_proxy_client=ai_proxy_client,
                graph_service=graph_service,
                recorder=recorder,
                actor=actor,
                user_message=user_message,
                tracker=tracker,
                pad=pad,
                runtime_context=effective_runtime_context,
            )

        subgraphs = skeleton.get_subgraphs_for_container(target_container.container_id)
        target_subgraph_id = subgraphs[0].subgraph_id if subgraphs else None
        return RunRequest(
            graph_id=skeleton.graph_id,
            subgraph_id=target_subgraph_id,
            container_key=target_container.container_key,
            agent_type=target_container.container_key or target_container.role_type or "agent",
            input_payload={
                "runner": _run_target_container,
                "runtime_context": effective_runtime_context,
                "input_ref": {
                    "source_edge_id": call_edge.edge_id,
                    "target_container_key": target_container.container_key,
                    "user_message": user_message,
                    "task_description": str(
                        invoke_payload.get("task_description") or user_message or ""
                    ).strip(),
                    "invoke_payload": dict(invoke_payload),
                },
            },
            memory_scope_ref=f"{skeleton.graph_id}:{target_container.container_key}",
            tool_policy_id=str((runtime_binding.capability_policy or {}).get("policy_id") or target_container.container_key),
            quota_policy_id=str((runtime_binding.quota_policy or {}).get("policy_id") or "default"),
            quota_policy=dict(runtime_binding.quota_policy or {}),
            memory_policy=dict(runtime_binding.memory_policy or {}),
        )

    def _build_llm_run_request(
        self,
        *,
        sg: RuntimeSubgraph,
        container: RuntimeContainer,
        skeleton: RuntimeGraphSkeleton,
        pad: Scratchpad,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None,
        recorder: Any,
        actor: str,
        user_message: str,
        execution_context: ExecutionContext,
        runtime_context: dict[str, Any] | None,
        runtime_binding: Any,
    ) -> RunRequest:
        effective_runtime_context = dict(runtime_context or {})

        def _run_llm_subgraph() -> Generator[dict[str, Any], None, dict[str, Any]]:
            return self._run_llm_subgraph_locally(
                sg=sg,
                container=container,
                skeleton=skeleton,
                pad=pad,
                tool_executor=tool_executor,
                ai_proxy_client=ai_proxy_client,
                graph_service=graph_service,
                recorder=recorder,
                actor=actor,
                user_message=user_message,
                execution_context=execution_context,
                runtime_context=effective_runtime_context,
            )

        return RunRequest(
            graph_id=skeleton.graph_id,
            subgraph_id=sg.subgraph_id,
            container_key=container.container_key,
            agent_type=container.container_key or container.role_type or "agent",
            input_payload={
                "runner": _run_llm_subgraph,
                "runtime_context": effective_runtime_context,
                "input_ref": {
                    "subgraph_key": sg.subgraph_key,
                    "node_type": sg.node_type,
                    "user_message": user_message,
                },
            },
            memory_scope_ref=f"{skeleton.graph_id}:{container.container_key}",
            tool_policy_id=str((runtime_binding.capability_policy or {}).get("policy_id") or container.container_key),
            quota_policy_id=str((runtime_binding.quota_policy or {}).get("policy_id") or "default"),
            quota_policy=dict(runtime_binding.quota_policy or {}),
            memory_policy=dict(runtime_binding.memory_policy or {}),
        )

    def _run_llm_subgraph_locally(
        self,
        *,
        sg: RuntimeSubgraph,
        container: RuntimeContainer,
        skeleton: RuntimeGraphSkeleton,
        pad: Scratchpad,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any | None,
        recorder: Any,
        actor: str,
        user_message: str,
        execution_context: ExecutionContext,
        runtime_context: dict[str, Any] | None,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        context = _build_subgraph_context(
            sg=sg,
            container=container,
            recorder=recorder,
            pad=pad,
            user_message=user_message,
            runtime_context=runtime_context,
        )
        self._inject_experience_skill_context(
            sg=sg,
            container=container,
            context=context,
            user_message=user_message,
        )
        prompt_builder = _resolve_prompt_builder(
            sg=sg,
            pad=pad,
            context=context,
            prompt_builder_factory=self._prompt_builder_factory,
        )
        resolved_graph_service = _resolve_graph_service(
            graph_service=graph_service,
            recorder=recorder,
        )

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy_client,
            tool_executor=tool_executor,
            prompt_builder=prompt_builder,
            max_tool_call_rounds=_resolve_tool_loop_round_limit(context),
            scratchpad=pad,
            enable_complete_phase=_should_enable_complete_phase(sg),
            stage_container_key=_container_key_for_container(
                container=container,
                recorder=recorder,
                actor=actor,
            ),
            graph_meta_patcher=(
                (
                    lambda graph_id, meta_patch, updated_by: resolved_graph_service.patch_graph_meta(
                        graph_id,
                        meta_patch,
                        updated_by=updated_by,
                    )
                )
                if resolved_graph_service is not None
                and callable(getattr(resolved_graph_service, "patch_graph_meta", None))
                else None
            ),
            graph_meta_patch_builder=lambda runtime_ctx: _build_experience_meta_patch(runtime_ctx),
            stage_node_key_builder=lambda r: f"sg_{sg.subgraph_key}_r{r}",
            stage_label_builder=lambda r: f"{sg.label} Round {r}",
        )

        start_node_id = _find_subgraph_boundary_node_id(
            skeleton, sg.subgraph_id, "start",
        )
        end_node_id = _find_subgraph_boundary_node_id(
            skeleton, sg.subgraph_id, "end",
        )
        enter_subgraph = getattr(recorder, "enter_subgraph", None)
        if callable(enter_subgraph) and start_node_id:
            enter_subgraph(
                subgraph_id=sg.subgraph_id,
                start_node_id=start_node_id,
            )

        context["_execution_context"] = execution_context
        result: ToolLoopResult | None = None
        run_error: Exception | None = None
        gen = runner.run(
            recorder=recorder,
            user_id=actor,
            user_message=user_message,
            context=context,
        )
        try:
            event = next(gen)
            while True:
                yield event
                event = gen.send(None)
        except StopIteration as stop:
            result = stop.value
        except Exception as exc:
            run_error = exc
            raise
        finally:
            leave_subgraph = getattr(recorder, "leave_subgraph", None)
            if callable(leave_subgraph) and end_node_id:
                leave_subgraph(
                    end_node_id=end_node_id,
                    created_by=actor,
                )
            self._maybe_writeback_subgraph_experience(
                sg=sg,
                container=container,
                skeleton=skeleton,
                graph_service=graph_service,
                recorder=recorder,
                pad=pad,
                user_message=user_message,
                result=result,
                error=run_error,
            )
            self._record_injection_feedback(
                target=context.get("_experience_target"),
                context=context,
                missed=run_error is not None,
            )

        return {
            "route_key": result.route_key if result else None,
            "output": _build_subgraph_output(sg=sg, result=result),
        }

    def _record_injection_feedback(
        self,
        *,
        target: ExperienceTarget | None,
        context: dict[str, Any],
        missed: bool,
    ) -> None:
        injected_skill_id = str(context.get("_injected_skill_id") or "").strip()
        if target is None or not injected_skill_id:
            return
        used_at = datetime.now(timezone.utc)
        if self._experience_orchestrator is not None:
            self._experience_orchestrator.record_injection_feedback(
                target=target,
                missed=missed,
                used_at=used_at,
            )
            return
        policy = self._policies.resolve(target)
        self._skill_registry.record_injection_result(
            target.target_id,
            missed=missed,
            used_at=used_at,
            miss_threshold=policy.miss_threshold,
            min_miss_sample=policy.min_miss_sample,
        )

    def _inject_experience_skill_context(
        self,
        *,
        sg: RuntimeSubgraph,
        container: RuntimeContainer,
        context: dict[str, Any],
        user_message: str,
    ) -> None:
        target = context.get("_experience_target")
        if not isinstance(target, ExperienceTarget):
            target = resolve_experience_target_from_subgraph(
                container=container,
                subgraph=sg,
            )
        if target is None:
            return

        retrieved_skills = self._experience_retriever.retrieve_for_injection(
            target=target,
            user_message=str(user_message or "").strip(),
            task_description=str(sg.task_description or "").strip(),
        )
        if not retrieved_skills:
            return

        loaded_prompt = self._skill_loader.render_prompt_bundle(
            retrieved_skills=retrieved_skills,
            relevance_text=str(sg.task_description or "").strip(),
        )
        existing_context = str(context.get("_extra_system_context") or "").strip()
        prompt_text = loaded_prompt.prompt_text
        context["_extra_system_context"] = (
            f"{existing_context}\n\n{prompt_text}"
            if existing_context
            else prompt_text
        )
        context["_injected_skill_id"] = loaded_prompt.skill_id
        context["_injected_skill_ids"] = list(loaded_prompt.skill_ids)
        context["_injected_skill_target_id"] = loaded_prompt.target_id
        if loaded_prompt.shared_skill_ids:
            context["_injected_shared_skill_ids"] = list(loaded_prompt.shared_skill_ids)
        context["_injected_skill_relevance"] = loaded_prompt.score

    def _maybe_writeback_subgraph_experience(
        self,
        *,
        sg: RuntimeSubgraph,
        container: RuntimeContainer,
        skeleton: RuntimeGraphSkeleton,
        graph_service: Any | None,
        recorder: Any,
        pad: Scratchpad,
        user_message: str,
        result: ToolLoopResult | None,
        error: Exception | None,
    ) -> None:
        orchestrator = self._experience_orchestrator
        if orchestrator is None:
            return
        target = resolve_experience_target_from_subgraph(
            container=container,
            subgraph=sg,
        )
        if target is None:
            return
        final_conclusion = _build_subgraph_output(sg=sg, result=result) if result else None
        orchestrator.safe_process_outcome(
            target=target,
            graph_id=skeleton.graph_id,
            graph_service=graph_service,
            recorder=recorder,
            scratchpad_snapshot=pad.snapshot_all(),
            container_key=container.container_key,
            subgraph_key=sg.subgraph_key,
            user_message=user_message,
            task_description=sg.task_description,
            final_conclusion=final_conclusion,
            runtime_status="failed" if error is not None else "succeeded",
            final_error=str(error) if error is not None else None,
        )

    def _resolve_runtime_tool_executor(
        self,
        *,
        container: RuntimeContainer,
        tool_executor: Any,
        runtime_binding: Any,
        runtime_context: dict[str, Any] | None,
    ) -> Any:
        resolved_executor = tool_executor
        container_executor_resolver = getattr(
            tool_executor,
            "resolve_runtime_tool_executor",
            None,
        )
        if callable(container_executor_resolver):
            container_executor = container_executor_resolver(
                container_key=container.container_key,
            )
            if container_executor is not None:
                resolved_executor = container_executor

        capability_policy = dict(runtime_binding.capability_policy or {})
        explicit_tool_names = {
            str(name).strip()
            for name in (
                capability_policy.get("tool_names")
                or capability_policy.get("tools")
                or []
            )
            if str(name).strip()
        }
        return ToolCapabilityExecutor(
            tool_executor=resolved_executor,
            allowed_tool_names=explicit_tool_names or None,
            policy_id=str(
                capability_policy.get("policy_id")
                or capability_policy.get("scope")
                or container.container_key
            ),
        )

    @staticmethod
    def _annotate_call_edge(
        *,
        graph_service: Any | None,
        call_edge: RuntimeEdge,
        actor: str,
        target_container: RuntimeContainer,
        invoke_payload: dict[str, Any],
    ) -> None:
        if graph_service is None or not hasattr(graph_service, "update_edge"):
            return
        merged_config = (
            dict(call_edge.config_json)
            if isinstance(call_edge.config_json, dict)
            else {}
        )
        merged_config.update(
            {
                "runtime": True,
                "target_container_key": target_container.container_key,
                "task_description": str(
                    invoke_payload.get("task_description") or ""
                ).strip(),
                "invoke_payload": dict(invoke_payload),
            }
        )
        graph_service.update_edge(
            call_edge.edge_id,
            config_json=merged_config,
            updated_by=actor,
        )

    @staticmethod
    def _advance_handoff(sg: RuntimeSubgraph) -> None:
        """Handoff subgraph: suspend the graph."""
        raise SuspendSignal(subgraph_id=sg.subgraph_id)

    # -- routing --------------------------------------------------------------

    @staticmethod
    def _resolve_next_subgraph(
        *,
        current_sg: RuntimeSubgraph,
        route_key: str | None,
        container_subgraphs: list[RuntimeSubgraph],
        skeleton: RuntimeGraphSkeleton,
    ) -> RuntimeSubgraph | None:
        """Determine the next subgraph to execute.

        1. If ``conditional_edges`` exist and ``route_key`` is non-empty,
           match and activate the first matching target subgraph.
        2. Otherwise, advance sequentially by ``order_index``.
        3. Return ``None`` when the container is fully executed.
        """
        cond_edges = (current_sg.config_json or {}).get("conditional_edges")
        if cond_edges and route_key:
            for ce in cond_edges:
                if ce.get("condition") == route_key:
                    target_node_id = ce.get("target_node_id")
                    matched = _find_subgraph_by_source_node(
                        skeleton, target_node_id
                    )
                    if matched is not None:
                        return matched

        # Sequential fallback: next subgraph in the same container by order
        for sg in container_subgraphs:
            if sg.order_index > current_sg.order_index:
                return sg
        return None


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _find_subgraph(
    skeleton: RuntimeGraphSkeleton, subgraph_id: str
) -> RuntimeSubgraph:
    for sg in skeleton.subgraphs:
        if sg.subgraph_id == subgraph_id:
            return sg
    raise ValueError(f"subgraph 不存在: {subgraph_id}")


def _find_container(
    skeleton: RuntimeGraphSkeleton, container_id: str
) -> RuntimeContainer:
    for c in skeleton.containers:
        if c.container_id == container_id:
            return c
    raise ValueError(f"container 不存在: {container_id}")


def _find_container_runtime_profile(
    *,
    skeleton: RuntimeGraphSkeleton,
    container: RuntimeContainer,
) -> str | None:
    subgraphs = skeleton.get_subgraphs_for_container(container.container_id)
    for subgraph in subgraphs:
        profile = str((subgraph.config_json or {}).get("runtime_profile") or "").strip()
        if profile:
            return profile
    return None


def _find_subgraph_by_node_id(
    skeleton: RuntimeGraphSkeleton, node_id: str
) -> RuntimeSubgraph:
    """Find the subgraph that owns *node_id*."""
    for n in skeleton.nodes:
        if n.node_id == node_id:
            for sg in skeleton.subgraphs:
                if sg.subgraph_id == n.subgraph_id:
                    return sg
    raise ValueError(f"无法找到 node_id={node_id} 对应的 subgraph")


def _find_subgraph_by_source_node(
    skeleton: RuntimeGraphSkeleton, source_node_id: str
) -> RuntimeSubgraph | None:
    """Find the subgraph whose ``source_node_id`` matches."""
    for sg in skeleton.subgraphs:
        if sg.source_node_id == source_node_id:
            return sg
    return None


def _find_subgraph_boundary_node_id(
    skeleton: RuntimeGraphSkeleton,
    subgraph_id: str,
    node_type: str,
) -> str | None:
    """Return the node_id of the start or end node within *subgraph_id*."""
    for n in skeleton.nodes:
        if n.subgraph_id == subgraph_id and n.node_type == node_type:
            return n.node_id
    return None


def _latest_stage_output(pad: Scratchpad) -> Any:
    """Return the content of the most recent ``stage_output`` entry."""
    entries = pad.read(filter_type="stage_output")
    if not entries:
        return ""
    return entries[-1].content


def _find_last_completed_subgraph_in_container(
    *,
    skeleton: RuntimeGraphSkeleton,
    container: RuntimeContainer,
    tracker: _SubgraphStatusTracker,
) -> RuntimeSubgraph | None:
    candidates = [
        sg
        for sg in skeleton.get_subgraphs_for_container(container.container_id)
        if tracker.get(sg.subgraph_id) == SubgraphStatus.COMPLETED
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.order_index)


def _resolve_graph_service(
    *,
    graph_service: Any | None,
    recorder: Any,
) -> Any | None:
    if graph_service is not None:
        return graph_service
    return getattr(recorder, "_service", None)


def _ensure_runtime_edge(
    *,
    graph_service: Any | None,
    graph_id: str,
    source_node_id: str | None,
    target_node_id: str | None,
    edge_type: str,
    label: str | None,
    actor: str,
    condition_expr: str | None = None,
    config_json: dict[str, Any] | None = None,
) -> None:
    if graph_service is None or not source_node_id or not target_node_id:
        return
    if source_node_id == target_node_id:
        return

    detail = graph_service.get_graph_detail(graph_id)
    edges = detail.get("edges") or []
    for edge in edges:
        if (
            edge.get("source_node_id") == source_node_id
            and edge.get("target_node_id") == target_node_id
            and edge.get("edge_type") == edge_type
        ):
            return

    next_order_index = max(
        (int(edge.get("order_index") or 0) for edge in edges),
        default=-1,
    ) + 1
    graph_service.create_edge(
        graph_id=graph_id,
        source_node_id=source_node_id,
        target_node_id=target_node_id,
        edge_type=edge_type,
        label=label,
        condition_expr=condition_expr,
        config_json=config_json,
        order_index=next_order_index,
        created_by=actor,
    )


def _ensure_runtime_transition_edge(
    *,
    graph_service: Any | None,
    graph_id: str,
    skeleton: RuntimeGraphSkeleton,
    source_subgraph: RuntimeSubgraph,
    target_subgraph: RuntimeSubgraph,
    actor: str,
    route_key: str | None,
) -> None:
    _ensure_runtime_edge(
        graph_service=graph_service,
        graph_id=graph_id,
        source_node_id=_find_subgraph_boundary_node_id(
            skeleton,
            source_subgraph.subgraph_id,
            "end",
        ),
        target_node_id=_find_subgraph_boundary_node_id(
            skeleton,
            target_subgraph.subgraph_id,
            "start",
        ),
        edge_type="seq",
        label="seq",
        actor=actor,
        config_json={
            "runtime": True,
            "subgraph_transition": True,
            "route_key": route_key,
            "source_subgraph": source_subgraph.subgraph_key,
            "target_subgraph": target_subgraph.subgraph_key,
        },
    )


def _build_subgraph_context(
    *,
    sg: RuntimeSubgraph,
    container: RuntimeContainer,
    recorder: Any,
    pad: Scratchpad,
    user_message: str = "",
    runtime_context: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Seed ToolLoopRunner context with recorder task metadata when available."""
    context: dict[str, Any] = {
        "_current_subgraph": sg.subgraph_key,
        "_graph_recorder": recorder,
    }
    task_context = getattr(recorder, "_task_context", None)
    if isinstance(task_context, dict):
        for key in (
            "project_id",
            "session_id",
            "user_id",
            "turn_index",
            "delegated_max_tool_call_rounds",
            "delegated_prompt_payload_format",
            "delegated_context_mode",
        ):
            if key in task_context:
                context[key] = task_context[key]
        task_context_user_message = str(task_context.get("user_message") or "").strip()
    else:
        task_context_user_message = ""
    graph_id = getattr(recorder, "graph_id", "")
    if graph_id:
        context["graph_id"] = graph_id
    context["_scratchpad_prompt_text"] = pad.format_for_prompt()
    config = sg.config_json or {}
    resolved_requirement_id = None
    service = getattr(recorder, "_service", None)
    if service is not None and graph_id:
        try:
            graph = service.get_execution_graph(graph_id)
        except Exception:
            graph = None
        meta = (graph or {}).get("meta_json") or {}
        resolved_requirement_id = meta.get("resolved_requirement_id")
        for key in (
            "classification_result",
            "last_write_result",
            "last_approval_result",
            "approval_pending",
        ):
            if key in meta:
                context[key] = meta.get(key)
    if resolved_requirement_id:
        context["resolved_requirement_id"] = resolved_requirement_id
    if runtime_context:
        context.update(runtime_context)
    resolved_user_message = str(task_context_user_message or user_message or "").strip()
    if resolved_user_message:
        context["_experience_user_message"] = resolved_user_message
    target = resolve_experience_target_from_subgraph(
        container=container,
        subgraph=sg,
    )
    if target is not None:
        context["_experience_target"] = target
        context["_experience_task_description"] = str(sg.task_description or "").strip()
    prompt_builder_kind = str(config.get("prompt_builder") or "").strip()
    if prompt_builder_kind.startswith("session_controller_") and resolved_user_message:
        from backend_business.services.agent.agents.session_controller.prompt_builder import (
            infer_routing_hint,
        )

        context["routing_hint"] = infer_routing_hint(resolved_user_message)
    if bool(config.get("native_invoke_enabled")):
        context["_native_invoke_enabled"] = True
    return context


def _build_experience_meta_patch(context: dict[str, Any]) -> dict[str, Any]:
    patch: dict[str, Any] = {}
    injected_skill_id = str(context.get("_injected_skill_id") or "").strip()
    if injected_skill_id:
        patch["injected_skill_id"] = injected_skill_id
    injected_skill_ids = [
        str(item).strip()
        for item in (context.get("_injected_skill_ids") or [])
        if str(item).strip()
    ]
    if injected_skill_ids:
        patch["injected_skill_ids"] = injected_skill_ids
    injected_skill_target_id = str(
        context.get("_injected_skill_target_id") or ""
    ).strip()
    if injected_skill_target_id:
        patch["injected_skill_target_id"] = injected_skill_target_id
    injected_shared_skill_ids = [
        str(item).strip()
        for item in (context.get("_injected_shared_skill_ids") or [])
        if str(item).strip()
    ]
    if injected_shared_skill_ids:
        patch["injected_shared_skill_ids"] = injected_shared_skill_ids
    injected_skill_relevance = context.get("_injected_skill_relevance")
    if isinstance(injected_skill_relevance, (int, float)):
        patch["injected_skill_relevance"] = float(injected_skill_relevance)
    return patch


def _resolve_prompt_builder(
    *,
    sg: RuntimeSubgraph,
    pad: Scratchpad,
    context: dict[str, Any],
    prompt_builder_factory: PromptBuilderFactory | None = None,
) -> PromptBuilderProtocol:
    config = sg.config_json or {}
    prompt_builder_kind = str(config.get("prompt_builder") or "").strip()
    if prompt_builder_factory is not None:
        prompt_builder = prompt_builder_factory(
            prompt_builder_kind=prompt_builder_kind,
            subgraph=sg,
            scratchpad=pad,
            context=context,
        )
        if prompt_builder is not None:
            return prompt_builder
    return SubgraphPromptBuilder(
        task_description=sg.task_description,
        scratchpad=pad,
        extra_system_context=str(context.get("_extra_system_context") or ""),
    )


def _should_enable_complete_phase(sg: RuntimeSubgraph) -> bool:
    config = sg.config_json or {}
    if "complete_phase_enabled" in config:
        return bool(config.get("complete_phase_enabled"))
    return True


def _resolve_tool_loop_round_limit(context: dict[str, Any]) -> int:
    raw_value = context.get("max_tool_call_rounds")
    try:
        normalized = int(raw_value)
    except (TypeError, ValueError):
        return 50
    return max(1, normalized)


def _build_subgraph_output(
    *,
    sg: RuntimeSubgraph,
    result: ToolLoopResult | None,
) -> Any:
    if result is None:
        return None
    config = sg.config_json or {}
    contract_kind = str(config.get("result_contract") or "").strip()
    if contract_kind == "requirement_agent":
        context = dict(result.context or {})
        raw_mode = str(
            context.get("mode")
            or (
                "approval_pending"
                if context.get("approval_pending")
                else "clarification"
                if context.get("clarification_required")
                else "chat"
            )
        ).strip().lower()
        return {
            "status": "success",
            "tool_loop_reply": result.tool_loop_reply,
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            "write_result": context.get("last_write_result"),
            "mode": raw_mode,
            "clarification_required": raw_mode == "clarification",
            "approval_pending": bool(context.get("approval_pending")),
            "approval_result": context.get("last_approval_result"),
        }
    if contract_kind == "conflict_detection":
        return {
            "status": "success",
            "tool_loop_reply": result.tool_loop_reply,
        }
    if contract_kind == "requirement_classification":
        context = dict(result.context or {})
        return {
            "status": "success",
            "tool_loop_reply": result.tool_loop_reply,
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            "classification_result": context.get("classification_result"),
        }
    if result.conclusion is not None:
        return result.conclusion
    return result.tool_loop_reply


def _find_latest_completed_subgraph_in_container(
    *,
    skeleton: RuntimeGraphSkeleton,
    container: RuntimeContainer,
    current_subgraph: RuntimeSubgraph,
    tracker: _SubgraphStatusTracker,
) -> RuntimeSubgraph | None:
    candidates = [
        sg
        for sg in skeleton.get_subgraphs_for_container(container.container_id)
        if sg.order_index < current_subgraph.order_index
        and tracker.get(sg.subgraph_id) == SubgraphStatus.COMPLETED
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda item: item.order_index)


def _resolve_invoke_request(
    *,
    current_sg: RuntimeSubgraph,
    caller_sg: RuntimeSubgraph | None,
    execution_context: ExecutionContext,
) -> dict[str, Any]:
    if caller_sg is None:
        raise ValueError(f"invoke subgraph '{current_sg.subgraph_key}' 缺少调用来源")
    expected_agent = str((current_sg.config_json or {}).get("delegate_agent") or "").strip()
    entries = execution_context.local_entries(caller_sg.subgraph_key)
    phase_payload: dict[str, Any] = {}
    for entry in reversed(entries):
        if entry.kind != "phase_conclusion":
            continue
        value = entry.value if isinstance(entry.value, dict) else {}
        conclusion = value.get("conclusion")
        if not isinstance(conclusion, str) or not conclusion.strip():
            continue
        try:
            parsed = json.loads(conclusion)
        except json.JSONDecodeError:
            parsed = None
        if isinstance(parsed, dict):
            phase_payload = parsed
            break
    for entry in reversed(entries):
        if entry.kind != "tool_result":
            continue
        value = entry.value if isinstance(entry.value, dict) else {}
        tool_result = value.get("result") if isinstance(value.get("result"), dict) else {}
        if not tool_result.get("native_invoke"):
            continue
        delegated_agent = str(tool_result.get("delegated_agent") or "").strip()
        if expected_agent and delegated_agent != expected_agent:
            continue
        merged = dict(tool_result)
        for key in (
            "resolved_requirement_id",
            "assistant_reply_seed",
            "tool_loop_reply",
            "clarification_question",
            "approval_pending",
            "approval_result",
            "should_suspend",
            "suspend_reason",
        ):
            if phase_payload.get(key) is not None and merged.get(key) is None:
                merged[key] = phase_payload.get(key)
        return merged
    if not expected_agent:
        fallback_request = dict(phase_payload)
        fallback_request.setdefault("delegated_agent", None)
        fallback_request.setdefault("task_description", "")
        return fallback_request
    raise ValueError(
        f"invoke subgraph '{current_sg.subgraph_key}' 未找到匹配的原生 invoke 请求"
    )


def _build_invoke_runtime_context(
    *,
    invoke_request: dict[str, Any],
) -> dict[str, Any]:
    delegated_agent = str(invoke_request.get("delegated_agent") or "").strip()
    requirement_id = str(invoke_request.get("requirement_id") or "").strip() or None
    context: dict[str, Any] = {
        "_native_invoke_enabled": False,
        "delegated_agent": delegated_agent,
    }
    if delegated_agent == "requirement_agent":
        context["selected_requirement_id"] = requirement_id
        context["prompt_payload_format"] = invoke_request.get("prompt_payload_format") or "markdown"
        context["historical_node_context"] = []
        context["max_tool_call_rounds"] = invoke_request.get("max_tool_call_rounds")
    elif delegated_agent == "requirement_classification_agent":
        context["selected_requirement_id"] = requirement_id
        context["selected_requirement_locked"] = bool(requirement_id)
        context["max_tool_call_rounds"] = invoke_request.get("max_tool_call_rounds")
    elif delegated_agent == "conflict_detection":
        context["max_tool_call_rounds"] = invoke_request.get("max_tool_call_rounds")
    if requirement_id:
        context["resolved_requirement_id"] = requirement_id
    return context


def _raise_if_runtime_cancelled(
    runtime_context: dict[str, Any] | None,
) -> None:
    if not runtime_context:
        return
    for key in ("_runtime_cancel_event", "_branch_stop_token"):
        token = runtime_context.get(key)
        if token is not None and callable(getattr(token, "is_set", None)) and token.is_set():
            raise RuntimeError("runtime execution cancelled")


def _build_session_controller_invoke_decision(
    *,
    invoke_subgraph: RuntimeSubgraph,
    invoke_request: dict[str, Any],
    target_result: Any,
) -> dict[str, Any]:
    delegated_agent = str(invoke_request.get("delegated_agent") or "").strip()
    if isinstance(target_result, list):
        normalized_results = [
            item
            if isinstance(item, dict)
            else {
                "status": "success",
                "tool_loop_reply": str(item or "").strip(),
            }
            for item in target_result
        ]
        combined_reply = "\n\n".join(
            str(item.get("tool_loop_reply") or item.get("reply") or "").strip()
            for item in normalized_results
            if str(item.get("tool_loop_reply") or item.get("reply") or "").strip()
        )
        result = {
            "status": "success",
            "tool_loop_reply": combined_reply,
            "approval_pending": any(
                bool(item.get("approval_pending")) for item in normalized_results
            ),
            "mode": next(
                (
                    str(item.get("mode") or "").strip()
                    for item in normalized_results
                    if str(item.get("mode") or "").strip()
                    in {"clarify", "clarification", "approval_pending"}
                ),
                "",
            ),
            "write_result": next(
                (item.get("write_result") for item in normalized_results if item.get("write_result") is not None),
                None,
            ),
            "approval_result": next(
                (
                    item.get("approval_result")
                    for item in normalized_results
                    if item.get("approval_result") is not None
                ),
                None,
            ),
            "classification_result": next(
                (
                    item.get("classification_result")
                    for item in normalized_results
                    if item.get("classification_result") is not None
                ),
                None,
            ),
            "resolved_requirement_id": next(
                (
                    str(item.get("resolved_requirement_id") or "").strip()
                    for item in normalized_results
                    if str(item.get("resolved_requirement_id") or "").strip()
                ),
                "",
            ),
        }
    else:
        result = target_result if isinstance(target_result, dict) else {
            "status": "success",
            "tool_loop_reply": str(target_result or "").strip(),
        }
    tool_loop_reply = str(result.get("tool_loop_reply") or result.get("reply") or "").strip()
    resolved_requirement_id = str(
        result.get("resolved_requirement_id")
        or invoke_request.get("resolved_requirement_id")
        or invoke_request.get("requirement_id")
        or ""
    ).strip() or None
    raw_mode = str(result.get("mode") or "").strip().lower()
    if raw_mode == "clarification":
        raw_mode = "clarify"
    approval_pending = bool(result.get("approval_pending"))
    should_suspend = False
    suspend_reason = None
    mode = {
        "requirement_agent": "delegate_requirement",
        "conflict_detection": "delegate_conflict",
        "requirement_classification_agent": "delegate_classification",
    }.get(delegated_agent, "direct_reply")
    clarification_question = None
    context: dict[str, Any] = {}

    if raw_mode == "clarify":
        mode = "clarify"
        should_suspend = True
        suspend_reason = "clarification"
        clarification_question = tool_loop_reply or None
    elif approval_pending:
        mode = "approval_pending"
        should_suspend = True
        suspend_reason = "approval_pending"

    if result.get("write_result") is not None:
        context["last_write_result"] = result.get("write_result")
    if result.get("approval_result") is not None:
        context["last_approval_result"] = result.get("approval_result")
    if result.get("classification_result") is not None:
        context["classification_result"] = result.get("classification_result")

    return {
        "mode": mode,
        "tool_loop_reply": tool_loop_reply,
        "assistant_reply_seed": tool_loop_reply or None,
        "clarification_question": clarification_question,
        "delegated_agent": delegated_agent or None,
        "resolved_requirement_id": resolved_requirement_id,
        "dispatched_agents": [delegated_agent] if delegated_agent else [],
        "approval_pending": approval_pending,
        "approval_result": result.get("approval_result"),
        "should_suspend": should_suspend,
        "suspend_reason": suspend_reason,
        "context": context,
        "source_subgraph": invoke_subgraph.subgraph_key,
    }


def _build_invoke_payload_snapshot(
    *,
    invoke_request: dict[str, Any],
    delegated_user_message: str,
) -> dict[str, Any]:
    excluded_keys = {
        "approval_pending",
        "approval_result",
        "assistant_reply_seed",
        "classification_result",
        "clarification_question",
        "clarification_required",
        "mode",
        "native_invoke",
        "reply",
        "should_suspend",
        "status",
        "suspend_reason",
        "tool_loop_reply",
        "write_result",
    }
    payload: dict[str, Any] = {}
    for key, value in invoke_request.items():
        if key in excluded_keys:
            continue
        normalized = _normalize_invoke_payload_value(value)
        if normalized in (None, "", [], {}):
            continue
        payload[key] = normalized
    if not str(payload.get("task_description") or "").strip() and delegated_user_message:
        payload["task_description"] = delegated_user_message
    return payload


def _normalize_invoke_payload_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        normalized_dict: dict[str, Any] = {}
        for key, item in value.items():
            normalized_item = _normalize_invoke_payload_value(item)
            if normalized_item in (None, "", [], {}):
                continue
            normalized_dict[str(key)] = normalized_item
        return normalized_dict
    if isinstance(value, (list, tuple, set)):
        normalized_list = []
        for item in value:
            normalized_item = _normalize_invoke_payload_value(item)
            if normalized_item in (None, "", [], {}):
                continue
            normalized_list.append(normalized_item)
        return normalized_list
    return str(value)


def _container_key_for_container(
    *,
    container: RuntimeContainer,
    recorder: Any,
    actor: str,
) -> str:
    """Return a recorder-compatible container_key for a runtime container."""
    container_key = container.container_key or "agent"

    ensure_container = getattr(recorder, "ensure_container", None)
    if callable(ensure_container):
        ensure_container(
            container_key=container_key,
            label=container.label or container_key,
            role_type=container.role_type or "agent",
            created_by=actor,
            config_json={"runtime": True, "source": "subgraph_runner"},
        )

    return container_key
