"""Session-controller-agent adapter for generic tool-call loop execution."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
from backend_business.services.agent.execution_graph_service import ExecutionGraphService

from .prompt_builder import SessionControllerPromptBuilder
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
    ) -> None:
        self._runner = ToolLoopRunner(
            ai_proxy_client=ai_proxy_client,
            tool_executor=tools,
            prompt_builder=prompt_builder,
            max_tool_call_rounds=max_tool_call_rounds,
            stage_container_key="conductor",
            stage_node_key_builder=lambda round_index: f"session_controller_tool_loop_round_{round_index}",
            stage_label_builder=lambda round_index: f"Tool Loop Round {round_index}",
            graph_meta_patcher=lambda graph_id, meta_patch, updated_by: execution_graph_service.patch_graph_meta(
                graph_id,
                meta_patch,
                updated_by=updated_by,
            ),
            graph_meta_patch_builder=lambda context: {
                "dispatched_agents": context.get("dispatched_agents", []),
            },
        )

    def run(
        self,
        *,
        recorder: SessionControllerGraphRecorder,
        user_id: str,
        user_message: str,
        project_id: str,
        session_id: str,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        context: dict[str, Any] = {
            "project_id": project_id,
            "user_id": user_id,
            "session_id": session_id,
            "graph_id": recorder.graph_id,
            "tool_results": [],
            "dispatched_agents": [],
            "_graph_recorder": recorder,
        }
        result = yield from self._runner.run(
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
