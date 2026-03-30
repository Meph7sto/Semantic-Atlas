"""Session-controller-agent adapter for generic tool-call loop execution."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.runtime.scratchpad import Scratchpad

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

    def run(
        self,
        *,
        recorder: SessionControllerGraphRecorder,
        user_id: str,
        user_message: str,
        project_id: str,
        session_id: str,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        graph = self._execution_graph_service.get_execution_graph(recorder.graph_id)
        meta = (graph.get("meta_json") or {}) if graph else {}
        scratchpad = Scratchpad.from_snapshot(meta.get("scratchpad_entries") or [])
        resolved_requirement_id = meta.get("resolved_requirement_id")
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
            "_scratchpad_prompt_text": scratchpad.format_for_prompt(),
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
        return {
            "tool_loop_reply": result.tool_loop_reply,
            "context": result.context,
            "rounds": result.rounds,
            "phase_completed": result.phase_completed,
            "route_key": result.route_key,
            "conclusion": result.conclusion,
        }
