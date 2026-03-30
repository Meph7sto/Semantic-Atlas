"""Requirement-classification-agent adapter for generic tool-call loop execution."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any

from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.tools import RequirementClassificationTools

from .prompt_builder import RequirementClassificationPromptBuilder
from .runtime_graph_recorder import RequirementClassificationGraphRecorder


def extract_latest_classification_result(context: dict[str, Any]) -> tuple[str | None, dict[str, Any] | None]:
    tool_results = context.get("tool_results") or []
    for item in reversed(tool_results):
        if item.get("tool_name") != "classify_requirement":
            continue
        result = item.get("result") or {}
        if result.get("is_error"):
            continue
        return result.get("requirement_id"), result
    return context.get("resolved_requirement_id"), None


class RequirementClassificationToolLoopRunner:
    def __init__(
        self,
        *,
        ai_proxy_client: Any,
        tools: RequirementClassificationTools,
        execution_graph_service: ExecutionGraphService,
        prompt_builder: RequirementClassificationPromptBuilder,
        max_tool_call_rounds: int,
        stage_container_key: str = "requirement_classification_agent",
        node_key_prefix: str = "requirement_classification_agent",
    ) -> None:
        self._ai_proxy_client = ai_proxy_client
        self._tools = tools
        self._execution_graph_service = execution_graph_service
        self._prompt_builder = prompt_builder
        self._max_tool_call_rounds = max_tool_call_rounds
        self._stage_container_key = stage_container_key
        self._node_key_prefix = node_key_prefix

    def run(
        self,
        *,
        recorder: RequirementClassificationGraphRecorder | Any,
        user_id: str,
        user_message: str,
        project_id: str,
        requirement_id: str | None,
        session_id: str,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        context: dict[str, Any] = {
            "project_id": project_id,
            "user_id": user_id,
            "session_id": session_id,
            "graph_id": recorder.graph_id,
            "selected_requirement_id": requirement_id,
            "selected_requirement_locked": bool(requirement_id),
            "resolved_requirement_id": requirement_id,
            "classification_result": None,
            "tool_results": [],
        }
        node_key_prefix = self._node_key_prefix
        runner = ToolLoopRunner(
            ai_proxy_client=self._ai_proxy_client,
            tool_executor=self._tools,
            prompt_builder=self._prompt_builder,
            max_tool_call_rounds=self._max_tool_call_rounds,
            stage_container_key=self._stage_container_key,
            stage_node_key_builder=lambda round_index: f"{node_key_prefix}_tool_loop_round_{round_index}",
            stage_label_builder=lambda round_index: f"Tool Loop Round {round_index}",
            graph_meta_patcher=lambda graph_id, meta_patch, updated_by: self._execution_graph_service.patch_graph_meta(
                graph_id,
                meta_patch,
                updated_by=updated_by,
            ),
            graph_meta_patch_builder=lambda ctx: self._build_meta_patch(ctx),
        )
        result = yield from runner.run(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            context=context,
        )
        resolved_requirement_id, classification_result = extract_latest_classification_result(result.context)
        result.context["resolved_requirement_id"] = resolved_requirement_id
        result.context["classification_result"] = classification_result
        return {
            "tool_loop_reply": result.tool_loop_reply,
            "context": result.context,
            "rounds": result.rounds,
            "phase_completed": result.phase_completed,
            "route_key": result.route_key,
            "conclusion": result.conclusion,
        }

    @staticmethod
    def _build_meta_patch(context: dict[str, Any]) -> dict[str, Any]:
        resolved_requirement_id, classification_result = extract_latest_classification_result(context)
        patch: dict[str, Any] = {}
        if resolved_requirement_id:
            patch["resolved_requirement_id"] = resolved_requirement_id
        if classification_result:
            patch["classification_result"] = classification_result
        return patch
