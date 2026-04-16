"""Subgraph-level runtime execution engine.

Drives the runtime execution graph forward on a per-subgraph basis.

This module defines:
- SubgraphPromptBuilder  — generates prompts for llm subgraphs
- SubgraphRunner         — orchestrates run / resume / advance / route
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from backend_business.services.agent.runtime.context import ExecutionContext
from backend_business.services.agent.runtime.scratchpad import Scratchpad

from .subgraph_state import (
    ContainerExecutionError,
    SubgraphStatus,
    SuspendSignal,
    validate_subgraph_transition,
)
from .prompt_interface import PromptBuilderProtocol
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

    conclusion: str
    """Last subgraph's complete_phase conclusion (return-edge payload)."""

    scratchpad_snapshot: list[dict[str, Any]]
    """Serialised scratchpad entries for persistence / debugging."""


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

    def init(self, subgraph_id: str, status: SubgraphStatus) -> None:
        self._statuses[subgraph_id] = status

    def get(self, subgraph_id: str) -> SubgraphStatus:
        return self._statuses.get(subgraph_id, SubgraphStatus.PENDING)

    def transition(
        self, subgraph_id: str, target: SubgraphStatus
    ) -> None:
        current = self.get(subgraph_id)
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

    # -- public API -----------------------------------------------------------

    def run(
        self,
        *,
        skeleton: RuntimeGraphSkeleton,
        tool_executor: Any,
        ai_proxy_client: Any,
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
        pad = scratchpad if scratchpad is not None else Scratchpad()
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
            )

        # Continue from the next subgraph
        return (yield from self._continue_from(
            start_sg=next_sg,
            container_subgraphs=subgraphs,
            container=container,
            skeleton=skeleton,
            tool_executor=tool_executor,
            ai_proxy_client=ai_proxy_client,
            recorder=recorder,
            actor=actor,
            user_message=user_input,
            tracker=tracker,
            pad=pad,
            execution_context=execution_context,
        ))

    # -- container-level orchestration ----------------------------------------

    def _execute_container(
        self,
        *,
        container: RuntimeContainer,
        skeleton: RuntimeGraphSkeleton,
        tool_executor: Any,
        ai_proxy_client: Any,
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        pad: Scratchpad | None = None,
    ) -> Generator[dict[str, Any], None, ContainerResult]:
        """Execute all subgraphs in *container* sequentially."""
        runtime_pad = pad if pad is not None else Scratchpad()
        execution_context = ExecutionContext(scratchpad=runtime_pad)
        subgraphs = skeleton.get_subgraphs_for_container(container.container_id)
        if not subgraphs:
            return ContainerResult(conclusion="", scratchpad_snapshot=[])

        first_sg = subgraphs[0]
        return (yield from self._continue_from(
            start_sg=first_sg,
            container_subgraphs=subgraphs,
            container=container,
            skeleton=skeleton,
            tool_executor=tool_executor,
            ai_proxy_client=ai_proxy_client,
            recorder=recorder,
            actor=actor,
            user_message=user_message,
            tracker=tracker,
            pad=runtime_pad,
            execution_context=execution_context,
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
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        pad: Scratchpad,
        execution_context: ExecutionContext,
    ) -> Generator[dict[str, Any], None, ContainerResult]:
        """Drive subgraphs starting from *start_sg* until no more remain."""
        last_conclusion = ""
        current_sg: RuntimeSubgraph | None = start_sg

        while current_sg is not None:
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
                    recorder=recorder,
                    actor=actor,
                    user_message=user_message,
                    tracker=tracker,
                    execution_context=execution_context,
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

            current_sg = self._resolve_next_subgraph(
                current_sg=current_sg,
                route_key=route_key,
                container_subgraphs=container_subgraphs,
                skeleton=skeleton,
            )

        return ContainerResult(
            conclusion=last_conclusion,
            scratchpad_snapshot=pad.snapshot(),
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
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        execution_context: ExecutionContext,
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
                recorder=recorder,
                actor=actor,
                user_message=user_message,
                tracker=tracker,
                execution_context=execution_context,
            ))
        elif node_type == "invoke":
            yield from self._advance_invoke(
                sg=sg,
                skeleton=skeleton,
                pad=pad,
                tool_executor=tool_executor,
                ai_proxy_client=ai_proxy_client,
                recorder=recorder,
                actor=actor,
                user_message=user_message,
                tracker=tracker,
                execution_context=execution_context,
            )
            return None
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
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        execution_context: ExecutionContext,
    ) -> Generator[dict[str, Any], None, str | None]:
        """Execute an llm subgraph via ToolLoopRunner."""
        execution_context.begin_subgraph(sg.subgraph_key)
        context = _build_subgraph_context(sg=sg, recorder=recorder, pad=pad)
        prompt_builder = _resolve_prompt_builder(
            sg=sg,
            pad=pad,
            context=context,
        )

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy_client,
            tool_executor=tool_executor,
            prompt_builder=prompt_builder,
            scratchpad=pad,
            enable_complete_phase=True,
            stage_container_key=_container_key_for_container(
                container=container,
                recorder=recorder,
                actor=actor,
            ),
            stage_node_key_builder=lambda r: f"sg_{sg.subgraph_key}_r{r}",
            stage_label_builder=lambda r: f"{sg.label} Round {r}",
        )

        # Locate the subgraph's start/end node IDs for recorder context
        start_node_id = _find_subgraph_boundary_node_id(
            skeleton, sg.subgraph_id, "start",
        )
        end_node_id = _find_subgraph_boundary_node_id(
            skeleton, sg.subgraph_id, "end",
        )

        # Enter subgraph context so recorder assigns subgraph_id to LLM nodes
        enter_subgraph = getattr(recorder, "enter_subgraph", None)
        if callable(enter_subgraph) and start_node_id:
            enter_subgraph(
                subgraph_id=sg.subgraph_id,
                start_node_id=start_node_id,
            )

        context["_execution_context"] = execution_context
        result: ToolLoopResult | None = None

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

        # Leave subgraph context — creates LLM→end edge
        leave_subgraph = getattr(recorder, "leave_subgraph", None)
        if callable(leave_subgraph) and end_node_id:
            leave_subgraph(
                end_node_id=end_node_id,
                created_by=actor,
            )

        execution_context.end_subgraph(
            sg.subgraph_key,
            output=(
                result.conclusion
                if result and result.conclusion is not None
                else (result.tool_loop_reply if result else None)
            ),
        )
        tracker.transition(sg.subgraph_id, SubgraphStatus.COMPLETED)
        return result.route_key if result else None

    def _advance_invoke(
        self,
        *,
        sg: RuntimeSubgraph,
        skeleton: RuntimeGraphSkeleton,
        pad: Scratchpad,
        tool_executor: Any,
        ai_proxy_client: Any,
        recorder: Any,
        actor: str,
        user_message: str,
        tracker: _SubgraphStatusTracker,
        execution_context: ExecutionContext,
    ) -> Generator[dict[str, Any], None, None]:
        """Execute an invoke subgraph: synchronously call target container."""
        # Find the call edge originating from this subgraph
        outgoing = skeleton.get_outgoing_edges(sg.subgraph_id)
        call_edge = next(
            (e for e in outgoing if e.edge_type == "call"), None
        )
        if call_edge is None:
            raise ValueError(
                f"invoke subgraph '{sg.subgraph_key}' 缺少 call 出边"
            )

        # Find target subgraph's container
        target_sg = _find_subgraph_by_node_id(skeleton, call_edge.target_node_id)
        target_container = _find_container(skeleton, target_sg.container_id)

        # Synchronously execute target container
        target_result: ContainerResult = yield from self._execute_container(
            container=target_container,
            skeleton=skeleton,
            tool_executor=tool_executor,
            ai_proxy_client=ai_proxy_client,
            recorder=recorder,
            actor=actor,
            user_message=user_message,
            tracker=tracker,
        )

        # Inject return conclusion into caller's scratchpad
        pad.append_stage_output(
            sg.subgraph_key,
            f"[跨容器调用返回] {target_result.conclusion}",
        )

        tracker.transition(sg.subgraph_id, SubgraphStatus.COMPLETED)

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


def _latest_stage_output(pad: Scratchpad) -> str:
    """Return the content of the most recent ``stage_output`` entry."""
    entries = pad.read(filter_type="stage_output")
    if not entries:
        return ""
    return str(entries[-1].content)


def _build_subgraph_context(
    *,
    sg: RuntimeSubgraph,
    recorder: Any,
    pad: Scratchpad,
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
        user_message = str(task_context.get("user_message") or "").strip()
    else:
        user_message = ""
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
    if resolved_requirement_id:
        context["resolved_requirement_id"] = resolved_requirement_id
    prompt_builder_kind = str(config.get("prompt_builder") or "").strip()
    if prompt_builder_kind.startswith("session_controller_") and user_message:
        from backend_business.services.agent.agents.session_controller.prompt_builder import (
            infer_routing_hint,
        )

        context["routing_hint"] = infer_routing_hint(user_message)
    return context


def _resolve_prompt_builder(
    *,
    sg: RuntimeSubgraph,
    pad: Scratchpad,
    context: dict[str, Any],
) -> PromptBuilderProtocol:
    config = sg.config_json or {}
    prompt_builder_kind = str(config.get("prompt_builder") or "").strip()
    if prompt_builder_kind == "session_controller_decision":
        from backend_business.services.agent.agents.session_controller.graph_prompt_builders import (
            SessionControllerDecisionGraphPromptBuilder,
        )

        return SessionControllerDecisionGraphPromptBuilder()
    if prompt_builder_kind == "session_controller_final_reply":
        from backend_business.services.agent.agents.session_controller.graph_prompt_builders import (
            SessionControllerReplyGraphPromptBuilder,
        )

        return SessionControllerReplyGraphPromptBuilder(reply_kind="final")
    if prompt_builder_kind == "session_controller_suspend_reply":
        from backend_business.services.agent.agents.session_controller.graph_prompt_builders import (
            SessionControllerReplyGraphPromptBuilder,
        )

        return SessionControllerReplyGraphPromptBuilder(reply_kind="suspend")
    return SubgraphPromptBuilder(
        task_description=sg.task_description,
        scratchpad=pad,
        extra_system_context=str(context.get("_extra_system_context") or ""),
    )


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
