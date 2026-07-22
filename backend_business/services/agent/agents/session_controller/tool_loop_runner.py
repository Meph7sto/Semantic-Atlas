"""Session-controller-agent adapter for generic tool-call loop execution."""

from __future__ import annotations

import json
from collections.abc import Generator
from json import JSONDecodeError
from typing import Any

from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.runtime.agent_registry import BUILTIN_AGENT_REGISTRY
from backend_business.services.agent.runtime.scratchpad_service import ScratchpadService

from .contracts import (
    SessionControllerDecisionMode,
    SessionControllerLoopResult,
    SuspendReason,
)
from .prompt_builder import SessionControllerPromptBuilder, infer_routing_hint
from .runtime_graph_recorder import SessionControllerGraphRecorder
from .tools import SessionControllerTools

class SessionControllerToolLoopRunner:
    def __init__(
        self,
        *,
        ai_proxy_client: Any,
        tools: SessionControllerTools,
        execution_graph_service: ExecutionGraphService,
        prompt_builder: SessionControllerPromptBuilder,
        max_tool_call_rounds: int,
        delegated_max_tool_call_rounds: int = 15,
    ) -> None:
        self._ai_proxy_client = ai_proxy_client
        self._tools = tools
        self._execution_graph_service = execution_graph_service
        self._prompt_builder = prompt_builder
        self._max_tool_call_rounds = max_tool_call_rounds
        self._delegated_max_tool_call_rounds = delegated_max_tool_call_rounds
        agent_registry = getattr(tools, "agent_registry", BUILTIN_AGENT_REGISTRY)
        self._tool_to_mode = {
            "list_requirements": SessionControllerDecisionMode.BROWSE,
            "search_requirements": SessionControllerDecisionMode.BROWSE,
            **{
                tool_name: SessionControllerDecisionMode(mode)
                for tool_name, mode in agent_registry.delegation_tool_to_mode().items()
            },
        }
        self._tool_to_agent = agent_registry.delegation_tool_to_agent()

    def run(
        self,
        *,
        recorder: SessionControllerGraphRecorder,
        user_id: str,
        user_message: str,
        project_id: str,
        session_id: str,
    ) -> Generator[dict[str, Any], None, SessionControllerLoopResult]:
        scratchpad = ScratchpadService(
            execution_graph_service=self._execution_graph_service,
        ).load(recorder.graph_id, container_key="conductor")
        graph = self._execution_graph_service.get_execution_graph(recorder.graph_id)
        meta = (graph.get("meta_json") or {}) if graph else {}
        resolved_requirement_id = meta.get("resolved_requirement_id")
        compilation = scratchpad.compile_for_prompt(
            task="\n".join(
                str(part)
                for part in (resolved_requirement_id, user_message)
                if part
            ),
            observation_key="tool_loop:conductor",
        )
        context: dict[str, Any] = {
            "project_id": project_id,
            "user_id": user_id,
            "session_id": session_id,
            "graph_id": recorder.graph_id,
            "resolved_requirement_id": resolved_requirement_id,
            "resolved_requirement_ids": {resolved_requirement_id} if resolved_requirement_id else set(),
            "historical_node_context": recorder.historical_node_context,
            "tool_results": [],
            "dispatched_agents": [],
            "approval_pending": False,
            "routing_hint": infer_routing_hint(user_message),
            "delegated_prompt_payload_format": "markdown",
            "delegated_context_mode": "full",
            "delegated_max_tool_call_rounds": self._delegated_max_tool_call_rounds,
            "_scratchpad": scratchpad,
            "_scratchpad_prompt_text": compilation.text,
            "_scratchpad_compilation": compilation.to_metrics(),
            "_graph_recorder": recorder,
        }
        runner = ToolLoopRunner(
            ai_proxy_client=self._ai_proxy_client,
            tool_executor=self._tools,
            prompt_builder=self._prompt_builder,
            max_tool_call_rounds=self._max_tool_call_rounds,
            stage_container_key="conductor",
            stage_node_key_builder=lambda round_index: f"session_controller_tool_loop_round_{round_index}",
            stage_label_builder=lambda round_index: f"Tool Loop Round {round_index}",
            graph_meta_patcher=lambda graph_id, meta_patch, updated_by: self._execution_graph_service.patch_graph_meta(
                graph_id,
                meta_patch,
                updated_by=updated_by,
            ),
            graph_meta_patch_builder=lambda runtime_context: {
                "dispatched_agents": runtime_context.get("dispatched_agents", []),
                "resolved_requirement_id": runtime_context.get("resolved_requirement_id"),
            },
            scratchpad=scratchpad,
        )
        result = yield from runner.run(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            context=context,
        )
        return self._build_loop_result(result=result)

    def _build_loop_result(self, *, result: Any) -> SessionControllerLoopResult:
        context = dict(result.context)
        assistant_payload = self._parse_structured_payload(result.tool_loop_reply)
        if assistant_payload is not None:
            return self._build_structured_result(
                payload=assistant_payload,
                context=context,
                raw_reply=result.tool_loop_reply,
                rounds=result.rounds,
                phase_completed=result.phase_completed,
                route_key=result.route_key,
                conclusion=result.conclusion,
            )

        return self._build_fallback_result(
            raw_reply=result.tool_loop_reply,
            context=context,
            rounds=result.rounds,
            phase_completed=result.phase_completed,
            route_key=result.route_key,
            conclusion=result.conclusion,
        )

    @staticmethod
    def _parse_structured_payload(raw_reply: str) -> dict[str, Any] | None:
        text = str(raw_reply or "").strip()
        if not text:
            return None
        try:
            payload = json.loads(text)
        except JSONDecodeError:
            return None
        return payload if isinstance(payload, dict) else None

    def _build_structured_result(
        self,
        *,
        payload: dict[str, Any],
        context: dict[str, Any],
        raw_reply: str,
        rounds: int,
        phase_completed: bool,
        route_key: str | None,
        conclusion: str | None,
    ) -> SessionControllerLoopResult:
        mode = self._normalize_mode(payload.get("mode"))
        delegated_agent = str(payload.get("delegated_agent") or "").strip() or None
        tool_loop_reply = str(payload.get("tool_loop_reply") or "").strip()
        assistant_reply_seed = str(payload.get("assistant_reply_seed") or "").strip() or None
        clarification_question = str(payload.get("clarification_question") or "").strip() or None
        approval_pending = bool(payload.get("approval_pending"))
        should_suspend = bool(payload.get("should_suspend"))
        suspend_reason = self._normalize_suspend_reason(payload.get("suspend_reason"))

        if mode == SessionControllerDecisionMode.CLARIFY:
            should_suspend = True
            suspend_reason = SuspendReason.CLARIFICATION
            if not clarification_question:
                clarification_question = assistant_reply_seed or tool_loop_reply or None
        elif mode == SessionControllerDecisionMode.APPROVAL_PENDING:
            approval_pending = True
            should_suspend = True
            suspend_reason = SuspendReason.APPROVAL_PENDING
        elif mode == SessionControllerDecisionMode.ERROR:
            assistant_reply_seed = assistant_reply_seed or tool_loop_reply or "当前请求未能完成。"

        if not tool_loop_reply:
            tool_loop_reply = clarification_question or assistant_reply_seed or str(raw_reply or "").strip()
        if delegated_agent is None:
            delegated_agent = self._infer_delegated_agent_from_mode(mode)

        return SessionControllerLoopResult(
            mode=mode,
            tool_loop_reply=tool_loop_reply,
            assistant_reply_seed=assistant_reply_seed,
            clarification_question=clarification_question,
            delegated_agent=delegated_agent,
            resolved_requirement_id=(
                str(payload.get("resolved_requirement_id") or "").strip()
                or str(context.get("resolved_requirement_id") or "").strip()
                or None
            ),
            dispatched_agents=self._resolve_dispatched_agents(
                payload_dispatched=payload.get("dispatched_agents"),
                context=context,
                delegated_agent=delegated_agent,
            ),
            approval_pending=approval_pending,
            approval_result=payload.get("approval_result") or context.get("last_approval_result"),
            should_suspend=should_suspend,
            suspend_reason=suspend_reason,
            context=context,
            rounds=rounds,
            phase_completed=phase_completed,
            route_key=route_key,
            conclusion=conclusion,
        )

    def _build_fallback_result(
        self,
        *,
        raw_reply: str,
        context: dict[str, Any],
        rounds: int,
        phase_completed: bool,
        route_key: str | None,
        conclusion: str | None,
    ) -> SessionControllerLoopResult:
        tool_results = context.get("tool_results") or []
        last_tool_entry = tool_results[-1] if tool_results else {}
        last_tool_name = str(last_tool_entry.get("tool_name") or "").strip()
        last_tool_result = last_tool_entry.get("result") or {}
        mode = self._tool_to_mode.get(
            last_tool_name,
            SessionControllerDecisionMode.DIRECT_REPLY,
        )
        delegated_agent = self._tool_to_agent.get(last_tool_name)
        approval_pending = bool(
            isinstance(last_tool_result, dict) and last_tool_result.get("approval_pending")
        )
        status = str(last_tool_result.get("status") or "").strip().lower() if isinstance(last_tool_result, dict) else ""
        tool_loop_reply = str(
            raw_reply
            or (last_tool_result.get("tool_loop_reply") if isinstance(last_tool_result, dict) else "")
            or (last_tool_result.get("reply") if isinstance(last_tool_result, dict) else "")
            or ""
        ).strip()
        clarification_required = bool(
            isinstance(last_tool_result, dict)
            and (
                last_tool_result.get("clarification_required")
                or self._normalize_mode(last_tool_result.get("mode"))
                == SessionControllerDecisionMode.CLARIFY
            )
        )
        clarification_question = tool_loop_reply if clarification_required else None
        should_suspend = False
        suspend_reason: SuspendReason | None = None

        if status == "error":
            mode = SessionControllerDecisionMode.ERROR
        elif approval_pending:
            mode = SessionControllerDecisionMode.APPROVAL_PENDING
            should_suspend = True
            suspend_reason = SuspendReason.APPROVAL_PENDING
        elif clarification_required:
            mode = SessionControllerDecisionMode.CLARIFY
            should_suspend = True
            suspend_reason = SuspendReason.CLARIFICATION

        return SessionControllerLoopResult(
            mode=mode,
            tool_loop_reply=tool_loop_reply,
            assistant_reply_seed=tool_loop_reply or None,
            clarification_question=clarification_question,
            delegated_agent=delegated_agent,
            resolved_requirement_id=(
                str(context.get("resolved_requirement_id") or "").strip() or None
            ),
            dispatched_agents=self._resolve_dispatched_agents(
                payload_dispatched=None,
                context=context,
                delegated_agent=delegated_agent,
            ),
            approval_pending=approval_pending,
            approval_result=context.get("last_approval_result"),
            should_suspend=should_suspend,
            suspend_reason=suspend_reason,
            context=context,
            rounds=rounds,
            phase_completed=phase_completed,
            route_key=route_key,
            conclusion=conclusion,
        )

    @staticmethod
    def _normalize_mode(
        raw_mode: Any,
        fallback: SessionControllerDecisionMode = SessionControllerDecisionMode.DIRECT_REPLY,
    ) -> SessionControllerDecisionMode:
        text = str(raw_mode or "").strip().lower()
        if text == "clarification":
            text = SessionControllerDecisionMode.CLARIFY.value
        try:
            return SessionControllerDecisionMode(text)
        except ValueError:
            return fallback

    @staticmethod
    def _normalize_suspend_reason(raw_reason: Any) -> SuspendReason | None:
        text = str(raw_reason or "").strip().lower()
        for reason in SuspendReason:
            if reason.value == text:
                return reason
        return None

    def _infer_delegated_agent_from_mode(
        self,
        mode: SessionControllerDecisionMode,
    ) -> str | None:
        for tool_name, mapped_mode in self._tool_to_mode.items():
            if mapped_mode == mode and tool_name in self._tool_to_agent:
                return self._tool_to_agent[tool_name]
        return None

    @staticmethod
    def _resolve_dispatched_agents(
        *,
        payload_dispatched: Any,
        context: dict[str, Any],
        delegated_agent: str | None,
    ) -> list[str]:
        if isinstance(payload_dispatched, list):
            normalized = [str(item).strip() for item in payload_dispatched if str(item).strip()]
            if normalized:
                return normalized
        context_agents = [
            str(item).strip() for item in (context.get("dispatched_agents") or []) if str(item).strip()
        ]
        if context_agents:
            return context_agents
        return [delegated_agent] if delegated_agent else []
