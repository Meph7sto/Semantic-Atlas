"""Conflict-detection-agent adapter for generic tool-call loop execution."""

from __future__ import annotations

from typing import Any

from backend_business.services.agent.execution.base_agent_tool_loop_runner import (
    AgentToolLoopSetup,
    BaseAgentToolLoopRunner,
)
from backend_business.services.agent.experience import (
    ExperienceOrchestrator,
    ExperiencePolicyResolver,
    SkillLoader,
    SkillRegistry,
    SkillRetriever,
)
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.tools import ConflictDetectionTools

from .prompt_builder import ConflictDetectionPromptBuilder
from .runtime_graph_recorder import ConflictDetectionGraphRecorder


class ConflictDetectionToolLoopRunner(BaseAgentToolLoopRunner):
    agent_type = "conflict_detection"
    task_description = "需求冲突检测 Agent 经典 tool-loop 执行阶段"

    def __init__(
        self,
        *,
        ai_proxy_client: Any,
        tools: ConflictDetectionTools,
        execution_graph_service: ExecutionGraphService,
        prompt_builder: ConflictDetectionPromptBuilder,
        max_tool_call_rounds: int,
        stage_container_key: str = "conflict_detection_agent",
        node_key_prefix: str = "conflict_agent",
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
        recorder: ConflictDetectionGraphRecorder,
        user_id: str,
        user_message: str,
        project_id: str,
        session_id: str,
    ) -> AgentToolLoopSetup:
        context: dict[str, Any] = {
            "project_id": project_id,
            "user_id": user_id,
            "session_id": session_id,
            "graph_id": recorder.graph_id,
            "tool_results": [],
        }
        return AgentToolLoopSetup(
            context=context,
            prompt_builder=self._prompt_builder,
        )
