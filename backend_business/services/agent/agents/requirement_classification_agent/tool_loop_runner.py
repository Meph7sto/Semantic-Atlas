"""Requirement-classification-agent adapter for generic tool-call loop execution."""

from __future__ import annotations

from typing import Any

from backend_business.services.agent.execution.base_agent_tool_loop_runner import (
    AgentToolLoopSetup,
    BaseAgentToolLoopRunner,
)
from backend_business.services.agent.execution.tool_loop_runner import ToolLoopResult
from backend_business.services.agent.experience import (
    ExperienceOrchestrator,
    ExperiencePolicyResolver,
    SkillLoader,
    SkillRegistry,
    SkillRetriever,
)
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


class RequirementClassificationToolLoopRunner(BaseAgentToolLoopRunner):
    agent_type = "requirement_classification_agent"
    task_description = "需求分类 Agent 经典 tool-loop 执行阶段"

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
        experience_retriever: SkillRetriever | None = None,
        skill_loader: SkillLoader | None = None,
        experience_orchestrator: ExperienceOrchestrator | None = None,
        skill_registry: SkillRegistry | None = None,
        policies: ExperiencePolicyResolver | None = None,
    ) -> None:
        super().__init__(
            ai_proxy_client=ai_proxy_client,
            tools=tools,
            execution_graph_service=execution_graph_service,
            prompt_builder=prompt_builder,
            max_tool_call_rounds=max_tool_call_rounds,
            stage_container_key=stage_container_key,
            node_key_prefix=node_key_prefix,
            experience_retriever=experience_retriever,
            skill_loader=skill_loader,
            experience_orchestrator=experience_orchestrator,
            skill_registry=skill_registry,
            policies=policies,
        )

    def build_tool_loop_setup(
        self,
        *,
        recorder: RequirementClassificationGraphRecorder | Any,
        user_id: str,
        user_message: str,
        project_id: str,
        requirement_id: str | None,
        session_id: str,
    ) -> AgentToolLoopSetup:
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
        return AgentToolLoopSetup(
            context=context,
            prompt_builder=self._prompt_builder,
        )

    def build_meta_patch(self, context: dict[str, Any]) -> dict[str, Any]:
        resolved_requirement_id, classification_result = extract_latest_classification_result(context)
        patch: dict[str, Any] = {}
        if resolved_requirement_id:
            patch["resolved_requirement_id"] = resolved_requirement_id
        if classification_result:
            patch["classification_result"] = classification_result
        patch.update(self._build_injected_skill_meta_patch(context))
        return patch

    def postprocess_result(
        self,
        *,
        result: ToolLoopResult,
        recorder: RequirementClassificationGraphRecorder | Any,
        user_id: str,
        user_message: str,
        setup: AgentToolLoopSetup,
        **kwargs: Any,
    ) -> dict[str, Any]:
        resolved_requirement_id, classification_result = extract_latest_classification_result(
            result.context
        )
        result.context["resolved_requirement_id"] = resolved_requirement_id
        result.context["classification_result"] = classification_result
        return self.normalize_result_payload(result)
