"""Top-level graph execution orchestrator.

Integrates TopologyInstantiator + SubgraphRunner into a single entry point
for the new "execution graph mode".  The judge node runs as a standard LLM
node inside the container, using ``complete_phase`` to signal its routing
decision.

This module defines:
- ExecutionResult  — immutable outcome of a graph execution
- GraphExecutor    — top-level orchestrator (execute / resume)
"""

from __future__ import annotations

import logging
from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from backend_business.services.agent.runtime import ScratchpadService

from .subgraph_runner import ContainerResult, SubgraphRunner
from .subgraph_state import (
    ContainerExecutionError,
    SuspendSignal,
)
from .tool_loop_runner import ToolLoopResult
from .topology_instantiator import (
    RuntimeGraphSkeleton,
    TopologyInstantiator,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ExecutionResult — immutable return value
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ExecutionResult:
    """Outcome of a full graph execution (execute or resume).

    Attributes
    ----------
    status : str
        One of ``"succeeded"`` / ``"suspended"`` / ``"failed"``.
    graph_id : str
        Runtime graph identifier.
    final_output : str | None
        The last subgraph's conclusion when status is ``"succeeded"``.
    suspended_subgraph_id : str | None
        The subgraph ID that triggered suspension (only when suspended).
    error : str | None
        Human-readable error message (only when failed).
    """

    status: str
    graph_id: str
    final_output: str | None = None
    suspended_subgraph_id: str | None = None
    error: str | None = None


@dataclass(frozen=True)
class JudgeDecision:
    """Validated routing decision returned by the judge node."""

    expand_topology: bool
    selected_template_id: str | None = None


class IntentJudgeError(RuntimeError):
    """Raised when the judge execution or its decision payload is invalid."""

    def __init__(self, graph_id: str, message: str) -> None:
        self.graph_id = graph_id
        super().__init__(message)


# ---------------------------------------------------------------------------
# Judge system prompt — used by _JudgePromptBuilder
# ---------------------------------------------------------------------------

_JUDGE_SYSTEM_PROMPT = """\
你是一个意图分类器兼拓扑图选择器。你是当前 container 的入口 LLM 节点。

你的职责是分析用户消息，判断任务是否复杂到需要展开拓扑图来处理。

请完成判断后，**必须**调用 complete_phase 工具来表达你的决策：

1. **需要展开拓扑图**：
   - expand_topology: 填写 true
   - target_template_graph_id: 填写选中的拓扑图 ID（从下方候选列表中选择）
   - conclusion: 填写你的判断理由

2. **不需要展开拓扑图**（任务足够简单、闲聊、问候等）：
   - expand_topology: 填写 false
   - target_template_graph_id: 不要填写
   - conclusion: 填写你的判断理由

候选拓扑图列表：
{candidates_block}

重要：你必须通过调用 complete_phase 工具来表达决策，不要仅返回文本。
重要：judge 阶段不要使用 route_key；route_key 只用于拓扑内部节点的条件路由。
"""


# ---------------------------------------------------------------------------
# Candidate formatting
# ---------------------------------------------------------------------------


def _format_candidates_block(
    candidates: list[dict[str, Any]],
) -> str:
    """Format candidate templates into a human-readable block for the prompt."""
    if not candidates:
        return "（无候选拓扑图）"
    lines: list[str] = []
    for idx, tpl in enumerate(candidates, start=1):
        graph_id = tpl.get("graph_id", "")
        name = tpl.get("name", "未命名")
        desc = tpl.get("description", "")
        line = f"{idx}. [{graph_id}] {name}"
        if desc:
            line += f" — {desc}"
        lines.append(line)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# _JudgePromptBuilder — prompt builder for the judge LLM node
# ---------------------------------------------------------------------------


class _JudgePromptBuilder:
    """Builds prompts for the intent-judge LLM node.

    The system prompt injects candidate topology templates so the model
    can select the most appropriate one and call ``complete_phase``.
    """

    def __init__(self, candidates_block: str) -> None:
        self._candidates_block = candidates_block

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        return _JUDGE_SYSTEM_PROMPT.format(
            candidates_block=self._candidates_block,
        )

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
        return {"round": round_index, "mode": "intent_judge"}


# ---------------------------------------------------------------------------
# _EmptyToolExecutor — judge only needs built-in complete_phase
# ---------------------------------------------------------------------------


class _EmptyToolExecutor:
    """No-op tool executor — judge only uses the built-in complete_phase."""

    def get_tools_list(self) -> list[dict[str, Any]]:
        return []

    def execute(
        self, tool_name: str, arguments: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        raise ValueError(f"未知工具: {tool_name}")


# ---------------------------------------------------------------------------
# GraphExecutor — top-level orchestrator
# ---------------------------------------------------------------------------


class GraphExecutor:
    """Top-level orchestrator for the new execution-graph mode.

    Combines ``TopologyInstantiator`` (skeleton creation) and
    ``SubgraphRunner`` (runtime advancement) into a unified interface.

    Usage::

        executor = GraphExecutor()
        gen = executor.execute(
            template_graph_id="tpl-123",
            project_id="proj-1",
            user_message="请检测需求冲突",
            tool_executor=my_tools,
            ai_proxy_client=ai,
            graph_service=svc,
            recorder=recorder,
            actor="user-42",
        )
        for event in gen:
            send_to_client(event)
        # gen returns ExecutionResult via StopIteration.value
    """

    def __init__(
        self,
        *,
        instantiator: TopologyInstantiator | None = None,
        runner: SubgraphRunner | None = None,
        scratchpad_service: ScratchpadService | None = None,
    ) -> None:
        self._instantiator = instantiator or TopologyInstantiator()
        self._runner = runner or SubgraphRunner()
        self._scratchpad_service = scratchpad_service

    # -- public API -----------------------------------------------------------

    def execute(
        self,
        *,
        template_graph_id: str | None = None,
        candidate_templates: list[dict[str, Any]] | None = None,
        project_id: str,
        user_message: str,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any,
        recorder: Any,
        actor: str,
        runtime_graph_id: str | None = None,
        runtime_container_key: str = "agent",
        runtime_container_label: str = "Agent",
        runtime_container_role_type: str = "agent",
    ) -> Generator[dict[str, Any], None, ExecutionResult]:
        """Full execution: [gate skeleton] → [judge] → topology or direct reply.

        When ``candidate_templates`` are provided, the executor first
        creates a lightweight gate skeleton (runtime graph + container +
        start/judge entry path). The judge then runs as a standard LLM
        node via ``ToolLoopRunner`` and calls ``complete_phase`` to signal
        its routing decision.

        - **Needs topology** → the selected topology is expanded into the
          *same* runtime graph, then ``SubgraphRunner`` drives the subgraphs.
        - **No topology** → ``ToolLoopRunner`` drives a plain conversation
          with full context (no subgraph mechanism) until the model stops.

        Yields SSE-style event dicts.  Returns ``ExecutionResult`` via
        ``StopIteration.value``.
        """
        effective_template_id = template_graph_id

        # 0. Intent gate -------------------------------------------------------
        if candidate_templates is not None:
            try:
                gate_graph_id, gate_container_id, judge_decision = (
                    yield from self._run_intent_gate(
                        user_message=user_message,
                        candidate_templates=candidate_templates,
                        project_id=project_id,
                        graph_service=graph_service,
                        ai_proxy_client=ai_proxy_client,
                        recorder=recorder,
                        actor=actor,
                        runtime_graph_id=runtime_graph_id,
                        runtime_container_key=runtime_container_key,
                        runtime_container_label=runtime_container_label,
                        runtime_container_role_type=runtime_container_role_type,
                    )
                )
            except IntentJudgeError as exc:
                if exc.graph_id:
                    _persist_graph_status(
                        graph_service, exc.graph_id, "failed", actor,
                    )
                return ExecutionResult(
                    status="failed",
                    graph_id=exc.graph_id,
                    error=str(exc),
                )

            if not judge_decision.expand_topology:
                # No topology needed → normal conversation path
                return (yield from self._drive_normal_conversation(
                    graph_id=gate_graph_id,
                    container_id=gate_container_id,
                    user_message=user_message,
                    tool_executor=tool_executor,
                    ai_proxy_client=ai_proxy_client,
                    graph_service=graph_service,
                    recorder=recorder,
                    actor=actor,
                    stage_container_key=runtime_container_key,
                ))

            # Use judge-selected template
            if effective_template_id is None:
                effective_template_id = judge_decision.selected_template_id

            # Reuse the runtime graph created during gating
            runtime_graph_id = gate_graph_id

        if effective_template_id is None:
            return ExecutionResult(
                status="failed",
                graph_id=runtime_graph_id or "",
                error="未选定拓扑模板：无 template_graph_id 且 judge 未返回有效选择",
            )

        # 1. Expand the selected topology into the runtime graph -----------------
        expand_error_label = "拓扑展开失败" if candidate_templates is not None else "骨架实例化失败"
        try:
            skeleton = self._instantiator.instantiate(
                template_graph_id=effective_template_id,
                project_id=project_id,
                graph_service=graph_service,
                created_by=actor,
                runtime_graph_id=runtime_graph_id,
            )
        except Exception as exc:
            logger.error("%s: %s", expand_error_label, exc, exc_info=True)
            return ExecutionResult(
                status="failed",
                graph_id=runtime_graph_id or "",
                error=f"{expand_error_label}: {exc}",
            )

        if candidate_templates is None:
            yield {
                "event": "skeleton_ready",
                "data": {
                    "graph_id": skeleton.graph_id,
                    "subgraph_count": len(skeleton.subgraphs),
                },
            }
        else:
            yield {
                "event": "topology_expanded",
                "data": {
                    "graph_id": skeleton.graph_id,
                    "subgraph_count": len(skeleton.subgraphs),
                },
            }

        # 2. Run SubgraphRunner -------------------------------------------------
        return (yield from self._drive_runner(
            skeleton=skeleton,
            tool_executor=tool_executor,
            ai_proxy_client=ai_proxy_client,
            graph_service=graph_service,
            recorder=recorder,
            actor=actor,
            user_message=user_message,
        ))

    def resume(
        self,
        *,
        skeleton: RuntimeGraphSkeleton,
        suspended_subgraph_id: str,
        user_input: str,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any,
        recorder: Any,
        actor: str,
    ) -> Generator[dict[str, Any], None, ExecutionResult]:
        """Resume from a previously suspended handoff subgraph.

        Yields SSE-style event dicts.  Returns ``ExecutionResult`` via
        ``StopIteration.value``.
        """
        scratchpad_service = self._resolve_scratchpad_service(graph_service)
        scratchpad = scratchpad_service.load(skeleton.graph_id)
        try:
            gen = self._runner.resume(
                skeleton=skeleton,
                suspended_subgraph_id=suspended_subgraph_id,
                user_input=user_input,
                tool_executor=tool_executor,
                ai_proxy_client=ai_proxy_client,
                recorder=recorder,
                actor=actor,
                scratchpad=scratchpad,
            )
            container_result: ContainerResult = yield from gen
        except SuspendSignal as sig:
            scratchpad_service.save(
                skeleton.graph_id,
                scratchpad,
                updated_by=actor,
            )
            latest_output = _latest_scratchpad_output(scratchpad)
            try:
                graph_service.patch_graph_meta(
                    skeleton.graph_id,
                    {"suspended_subgraph_id": sig.subgraph_id},
                    updated_by=actor,
                )
            except Exception:
                logger.warning("无法持久化 suspended_subgraph_id=%s", sig.subgraph_id, exc_info=True)
            _persist_graph_status(
                graph_service, skeleton.graph_id, "suspended", actor,
            )
            return ExecutionResult(
                status="suspended",
                graph_id=skeleton.graph_id,
                final_output=latest_output or None,
                suspended_subgraph_id=sig.subgraph_id,
            )
        except ContainerExecutionError as exc:
            scratchpad_service.save(
                skeleton.graph_id,
                scratchpad,
                updated_by=actor,
            )
            _persist_graph_status(
                graph_service, skeleton.graph_id, "failed", actor,
            )
            return ExecutionResult(
                status="failed",
                graph_id=skeleton.graph_id,
                error=str(exc),
            )
        except Exception as exc:
            scratchpad_service.save(
                skeleton.graph_id,
                scratchpad,
                updated_by=actor,
            )
            _persist_graph_status(
                graph_service, skeleton.graph_id, "failed", actor,
            )
            return ExecutionResult(
                status="failed",
                graph_id=skeleton.graph_id,
                error=f"resume 执行异常: {exc}",
            )

        # Succeeded
        scratchpad_service.save_snapshot(
            skeleton.graph_id,
            container_result.scratchpad_snapshot,
            updated_by=actor,
        )
        _persist_graph_status(
            graph_service, skeleton.graph_id, "succeeded", actor,
        )
        return ExecutionResult(
            status="succeeded",
            graph_id=skeleton.graph_id,
            final_output=container_result.conclusion,
        )

    # -- internal -------------------------------------------------------------

    def _run_intent_gate(
        self,
        *,
        user_message: str,
        candidate_templates: list[dict[str, Any]] | None,
        project_id: str,
        graph_service: Any,
        ai_proxy_client: Any,
        recorder: Any,
        actor: str,
        runtime_graph_id: str | None,
        runtime_container_key: str,
        runtime_container_label: str,
        runtime_container_role_type: str,
    ) -> Generator[dict[str, Any], None, tuple[str, str, JudgeDecision]]:
        """Create the lightweight gate skeleton, then drive [judge].

        The judge node is a standard LLM node that calls ``complete_phase``
        to signal its routing decision by explicitly returning:

        - ``expand_topology = true`` and ``target_template_graph_id``
        - or ``expand_topology = false`` without a target topology

        Yields SSE-style event dicts. The first emitted event is
        ``skeleton_ready`` and reflects the pre-topology gate skeleton.
        Returns ``(graph_id, container_id, judge_decision)``.
        """
        from .tool_loop_runner import ToolLoopRunner

        graph_id = runtime_graph_id or _create_gate_runtime_graph(
            graph_service=graph_service,
            project_id=project_id,
            actor=actor,
        )["graph_id"]
        container = _ensure_runtime_container(
            graph_service=graph_service,
            graph_id=graph_id,
            container_key=runtime_container_key,
            label=runtime_container_label,
            role_type=runtime_container_role_type,
            actor=actor,
        )
        container_id = container["container_id"]
        start_node = _ensure_start_node(
            graph_service=graph_service,
            graph_id=graph_id,
            container_id=container_id,
            actor=actor,
        )
        yield {
            "event": "skeleton_ready",
            "data": {
                "graph_id": graph_id,
                "subgraph_count": 0,
            },
        }

        # Build candidate block and prompt builder
        candidates = list(candidate_templates or [])
        candidates_block = _format_candidates_block(candidates)
        prompt_builder = _JudgePromptBuilder(candidates_block)

        # Point recorder at the new graph
        recorder.graph_id = graph_id

        # Drive judge via ToolLoopRunner + complete_phase
        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy_client,
            tool_executor=_EmptyToolExecutor(),
            prompt_builder=prompt_builder,
            stage_container_key=runtime_container_key,
            stage_node_key_builder=lambda r: f"intent_judge_r{r}",
            stage_label_builder=lambda r: f"Intent Judge Round {r}",
            enable_complete_phase=True,
        )

        context: dict[str, Any] = {"graph_id": graph_id}
        try:
            gen = runner.run(
                recorder=recorder,
                user_id=actor,
                user_message=user_message,
                context=context,
            )
            result: ToolLoopResult = yield from gen
        except Exception as exc:
            _ensure_start_to_judge_edge(
                graph_service=graph_service,
                graph_id=graph_id,
                container_id=container_id,
                start_node_id=start_node["node_id"],
                actor=actor,
            )
            logger.warning("Judge 节点执行失败: %s", exc, exc_info=True)
            raise IntentJudgeError(graph_id, f"judge 执行异常: {exc}") from exc

        # Parse judge decision from ToolLoopResult
        _ensure_start_to_judge_edge(
            graph_service=graph_service,
            graph_id=graph_id,
            container_id=container_id,
            start_node_id=start_node["node_id"],
            actor=actor,
        )
        try:
            judge_decision = _parse_judge_decision(
                result=result,
                candidates=candidates,
            )
        except ValueError as exc:
            raise IntentJudgeError(graph_id, str(exc)) from exc

        yield {
            "event": "intent_judge_completed",
            "data": {
                "graph_id": graph_id,
                "selected_template_id": judge_decision.selected_template_id,
                "expand_topology": judge_decision.expand_topology,
                "reason": result.conclusion or "",
            },
        }

        return (graph_id, container_id, judge_decision)

    def _drive_normal_conversation(
        self,
        *,
        graph_id: str,
        container_id: str,
        user_message: str,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any,
        recorder: Any,
        actor: str,
        stage_container_key: str,
    ) -> Generator[dict[str, Any], None, ExecutionResult]:
        """Drive a plain conversation when no topology is needed.

        Uses ``ToolLoopRunner`` with full context and no subgraph/phase
        mechanism — each round creates an llm node in the execution graph.
        """
        from .tool_loop_runner import ToolLoopRunner
        from .prompt_interface import PromptBuilderProtocol

        prompt_builder = _NormalConversationPromptBuilder()

        runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy_client,
            tool_executor=tool_executor,
            prompt_builder=prompt_builder,
            stage_container_key=stage_container_key,
            stage_node_key_builder=lambda r: f"conversation_r{r}",
            stage_label_builder=lambda r: f"Conversation Round {r}",
            enable_complete_phase=False,
        )

        context: dict[str, Any] = {"graph_id": graph_id}
        try:
            gen = runner.run(
                recorder=recorder,
                user_id=actor,
                user_message=user_message,
                context=context,
            )
            result = yield from gen
        except Exception as exc:
            _persist_graph_status(
                graph_service, graph_id, "failed", actor,
            )
            return ExecutionResult(
                status="failed",
                graph_id=graph_id,
                error=f"对话执行异常: {exc}",
            )

        _persist_graph_status(
            graph_service, graph_id, "succeeded", actor,
        )
        return ExecutionResult(
            status="succeeded",
            graph_id=graph_id,
            final_output=result.tool_loop_reply,
        )

    def _drive_runner(
        self,
        *,
        skeleton: RuntimeGraphSkeleton,
        tool_executor: Any,
        ai_proxy_client: Any,
        graph_service: Any,
        recorder: Any,
        actor: str,
        user_message: str,
    ) -> Generator[dict[str, Any], None, ExecutionResult]:
        """Drive SubgraphRunner.run() and translate outcomes to ExecutionResult."""
        scratchpad_service = self._resolve_scratchpad_service(graph_service)
        scratchpad = scratchpad_service.load(skeleton.graph_id)
        try:
            gen = self._runner.run(
                skeleton=skeleton,
                tool_executor=tool_executor,
                ai_proxy_client=ai_proxy_client,
                recorder=recorder,
                actor=actor,
                user_message=user_message,
                scratchpad=scratchpad,
            )
            container_result: ContainerResult = yield from gen
        except SuspendSignal as sig:
            scratchpad_service.save(
                skeleton.graph_id,
                scratchpad,
                updated_by=actor,
            )
            latest_output = _latest_scratchpad_output(scratchpad)
            try:
                graph_service.patch_graph_meta(
                    skeleton.graph_id,
                    {"suspended_subgraph_id": sig.subgraph_id},
                    updated_by=actor,
                )
            except Exception:
                logger.warning("无法持久化 suspended_subgraph_id=%s", sig.subgraph_id, exc_info=True)
            _persist_graph_status(
                graph_service, skeleton.graph_id, "suspended", actor,
            )
            return ExecutionResult(
                status="suspended",
                graph_id=skeleton.graph_id,
                final_output=latest_output or None,
                suspended_subgraph_id=sig.subgraph_id,
            )
        except ContainerExecutionError as exc:
            scratchpad_service.save(
                skeleton.graph_id,
                scratchpad,
                updated_by=actor,
            )
            _persist_graph_status(
                graph_service, skeleton.graph_id, "failed", actor,
            )
            return ExecutionResult(
                status="failed",
                graph_id=skeleton.graph_id,
                error=str(exc),
            )
        except Exception as exc:
            scratchpad_service.save(
                skeleton.graph_id,
                scratchpad,
                updated_by=actor,
            )
            _persist_graph_status(
                graph_service, skeleton.graph_id, "failed", actor,
            )
            return ExecutionResult(
                status="failed",
                graph_id=skeleton.graph_id,
                error=f"执行异常: {exc}",
            )

        # Succeeded
        scratchpad_service.save_snapshot(
            skeleton.graph_id,
            container_result.scratchpad_snapshot,
            updated_by=actor,
        )
        _persist_graph_status(
            graph_service, skeleton.graph_id, "succeeded", actor,
        )
        return ExecutionResult(
            status="succeeded",
            graph_id=skeleton.graph_id,
            final_output=container_result.conclusion,
        )

    def _resolve_scratchpad_service(self, graph_service: Any) -> ScratchpadService:
        if self._scratchpad_service is not None:
            return self._scratchpad_service
        return ScratchpadService(execution_graph_service=graph_service)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


class _NormalConversationPromptBuilder:
    """Minimal prompt builder for the no-topology conversation path.

    Passes the user message through without injecting subgraph-specific
    context — the ToolLoopRunner sees the full, unmodified conversation.
    """

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        return ""

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
        return {"round": round_index, "mode": "normal_conversation"}


def _create_gate_runtime_graph(
    *,
    graph_service: Any,
    project_id: str,
    actor: str,
) -> dict[str, Any]:
    return graph_service.create_runtime_graph(
        project_id=project_id,
        name="agent_execution",
        description="Runtime execution graph",
        created_by=actor,
        status="running",
        meta_json={"phase": "intent_gate"},
    )


def _ensure_runtime_container(
    *,
    graph_service: Any,
    graph_id: str,
    container_key: str,
    label: str,
    role_type: str,
    actor: str,
) -> dict[str, Any]:
    try:
        detail = graph_service.get_graph_detail(graph_id)
    except Exception:
        detail = {}

    containers = detail.get("containers") or []
    for container in containers:
        if container.get("container_key") == container_key:
            return container

    next_order_index = max(
        (int(container.get("order_index") or 0) for container in containers),
        default=-1,
    ) + 1
    return graph_service.create_container(
        graph_id=graph_id,
        container_key=container_key,
        label=label,
        role_type=role_type,
        order_index=next_order_index,
        created_by=actor,
    )


def _ensure_start_node(
    *,
    graph_service: Any,
    graph_id: str,
    container_id: str,
    actor: str,
) -> dict[str, Any]:
    try:
        detail = graph_service.get_graph_detail(graph_id)
    except Exception:
        detail = {}

    nodes = detail.get("nodes") or []
    for node in nodes:
        if node.get("container_id") == container_id and node.get("node_key") == "start":
            return node

    start_order_index = max(
        (
            int(node.get("order_index") or 0)
            for node in nodes
            if node.get("container_id") == container_id
        ),
        default=-1,
    ) + 1
    return graph_service.create_node(
        graph_id=graph_id,
        node_key="start",
        label="Start",
        node_type="start",
        role_type="agent",
        container_id=container_id,
        order_index=start_order_index,
        created_by=actor,
    )


def _ensure_start_to_judge_edge(
    *,
    graph_service: Any,
    graph_id: str,
    container_id: str,
    start_node_id: str,
    actor: str,
) -> None:
    try:
        detail = graph_service.get_graph_detail(graph_id)
    except Exception:
        return

    nodes = detail.get("nodes") or []
    judge_nodes = sorted(
        (
            node
            for node in nodes
            if node.get("container_id") == container_id
            and str(node.get("node_key") or "").startswith("turn_")
            and "intent_judge_r" in str(node.get("node_key") or "")
        ),
        key=lambda node: (
            int(node.get("order_index") or 0),
            str(node.get("created_at") or ""),
            str(node.get("node_id") or ""),
        ),
    )
    if not judge_nodes:
        return

    first_judge_node = judge_nodes[0]
    edges = detail.get("edges") or []
    for edge in edges:
        if (
            edge.get("source_node_id") == start_node_id
            and edge.get("target_node_id") == first_judge_node.get("node_id")
        ):
            return

    next_order_index = max(
        (int(edge.get("order_index") or 0) for edge in edges),
        default=-1,
    ) + 1
    graph_service.create_edge(
        graph_id=graph_id,
        source_node_id=start_node_id,
        target_node_id=first_judge_node["node_id"],
        edge_type="seq",
        order_index=next_order_index,
        created_by=actor,
    )


def _persist_graph_status(
    graph_service: Any,
    graph_id: str,
    status: str,
    actor: str,
) -> None:
    """Best-effort persist graph status to DB via graph_service."""
    try:
        graph_service.patch_graph_meta(
            graph_id,
            {},
            status=status,
            updated_by=actor,
        )
    except Exception:
        logger.warning(
            "无法持久化 graph 状态 %s → %s",
            graph_id,
            status,
            exc_info=True,
        )


def _parse_judge_decision(
    *,
    result: ToolLoopResult,
    candidates: list[dict[str, Any]],
) -> JudgeDecision:
    """Validate and extract the judge's explicit topology decision."""
    if not result.phase_completed:
        raise ValueError("judge 未通过 complete_phase 返回显式决策")

    expand_topology = result.expand_topology
    if not isinstance(expand_topology, bool):
        raise ValueError("judge complete_phase 缺少 expand_topology 布尔字段")

    target_template_graph_id = result.target_template_graph_id
    if not expand_topology:
        if target_template_graph_id:
            raise ValueError(
                "judge 指定 expand_topology=false 时，不应再携带 target_template_graph_id",
            )
        return JudgeDecision(expand_topology=False)

    valid_ids = {c.get("graph_id") for c in candidates}
    if not target_template_graph_id:
        raise ValueError("judge 指定 expand_topology=true 时，必须提供 target_template_graph_id")
    if target_template_graph_id not in valid_ids:
        raise ValueError(
            f"judge 选择的 target_template_graph_id '{target_template_graph_id}' 不在候选列表中",
        )
    return JudgeDecision(
        expand_topology=True,
        selected_template_id=target_template_graph_id,
    )


def _latest_scratchpad_output(scratchpad: Any) -> str:
    read = getattr(scratchpad, "read", None)
    if not callable(read):
        return ""
    try:
        entries = read(filter_type="stage_output")
    except Exception:
        return ""
    if not entries:
        return ""
    return str(entries[-1].content or "").strip()
