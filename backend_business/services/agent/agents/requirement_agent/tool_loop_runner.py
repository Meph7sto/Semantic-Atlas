"""Requirement-agent adapter for generic tool-call loop execution."""

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
from backend_business.services.agent.runtime.scratchpad import Scratchpad
from backend_business.services.agent.runtime.scratchpad_service import ScratchpadService
from backend_business.services.agent.tools import RequirementAgentTools

from .constants import DEFAULT_PROMPT_PAYLOAD_FORMAT
from .prompt_builder import RequirementAgentPromptBuilder
from .runtime_graph_recorder import _RuntimeGraphRecorder


class _RequirementToolLoopPromptAdapter:
    def __init__(self, prompt_builder: RequirementAgentPromptBuilder) -> None:
        self._prompt_builder = prompt_builder

    def build_system_prompt(self, *, context: dict[str, Any]) -> str:
        base = self._prompt_builder.build_tool_loop_system_prompt(context=context)
        # In scratchpad mode, append scratchpad contents and tool instruction
        scratchpad_text = context.get("_scratchpad_prompt_text") or ""
        if scratchpad_text:
            base += (
                "\n\n" + scratchpad_text
                + "\n\n你可以随时调用 scratchpad_write 工具，将重要发现、判断或工具结果摘录写入 Scratchpad 工作记忆，"
                "这些内容会在后续阶段中作为上下文保留。"
            )
        return base

    def build_user_message(self, *, user_message: str, context: dict[str, Any]) -> str:
        return self._prompt_builder.build_tool_loop_user_message(
            project_id=context["project_id"],
            user_message=user_message,
            requirement_id=context.get("selected_requirement_id"),
            historical_node_context=context.get("historical_node_context"),
            prompt_payload_format=context.get("prompt_payload_format", DEFAULT_PROMPT_PAYLOAD_FORMAT),
        )

    def build_round_input_summary(
        self,
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self._prompt_builder.build_tool_loop_input_summary(
            round_index=round_index,
            messages=messages,
            context=context,
        )


class RequirementAgentToolLoopRunner(BaseAgentToolLoopRunner):
    agent_type = "requirement_agent"
    task_description = "需求管理 Agent 经典 tool-loop 执行阶段"

    def __init__(
        self,
        *,
        ai_proxy_client: Any,
        tools: RequirementAgentTools,
        execution_graph_service: ExecutionGraphService,
        actor_manager_getter: Any,
        prompt_builder: RequirementAgentPromptBuilder,
        max_tool_call_rounds: int,
        stage_container_key: str = "requirements_agent",
        node_key_prefix: str = "requirements_agent",
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
            actor_manager_getter=actor_manager_getter,
            experience_retriever=experience_retriever,
            skill_loader=skill_loader,
            experience_orchestrator=experience_orchestrator,
            skill_registry=skill_registry,
            policies=policies,
        )

    def build_tool_loop_setup(
        self,
        *,
        recorder: _RuntimeGraphRecorder,
        user_id: str,
        user_message: str,
        project_id: str,
        requirement_id: str | None,
        session_id: str,
        prompt_payload_format: str,
        context_mode: str = "full",
    ) -> AgentToolLoopSetup:
        # 根据上下文模式决定注入 LLM 的历史节点上下文
        scratchpad: Scratchpad | None = None
        scratchpad_prompt_text = ""

        if context_mode == "scratchpad":
            # Scratchpad 蒸馏模式：不传递全量历史，从 graph meta 恢复 Scratchpad
            effective_historical_context: list[dict[str, Any]] = []
            scratchpad = ScratchpadService(
                execution_graph_service=self._execution_graph_service,
            ).load(recorder.graph_id, container_key=self._stage_container_key)
            scratchpad_prompt_text = scratchpad.format_for_prompt()
        elif context_mode == "incremental":
            # 增量模式：仅保留架构和文件上下文，不传递具体执行结果
            effective_historical_context = []
        else:
            # full: 传入完整历史节点上下文
            effective_historical_context = recorder.historical_node_context

        context: dict[str, Any] = {
            "project_id": project_id,
            "user_id": user_id,
            "session_id": session_id,
            "graph_id": recorder.graph_id,
            "selected_requirement_id": requirement_id,
            "resolved_requirement_id": requirement_id,
            "resolved_requirement_ids": {requirement_id} if requirement_id else set(),
            "historical_node_context": effective_historical_context,
            "context_mode": context_mode,
            "prompt_payload_format": prompt_payload_format,
            "tool_results": [],
            "write_performed": False,
            "clarification_required": False,
            "approval_pending": False,
            "_scratchpad_prompt_text": scratchpad_prompt_text,
        }
        return AgentToolLoopSetup(
            context=context,
            prompt_builder=_RequirementToolLoopPromptAdapter(self._prompt_builder),
            scratchpad=scratchpad,
            enable_complete_phase=(scratchpad is not None),
        )

    def build_meta_patch(self, context: dict[str, Any]) -> dict[str, Any]:
        return {
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            **self._build_injected_skill_meta_patch(context),
        }

    def after_tool_loop(
        self,
        *,
        result: ToolLoopResult,
        recorder: _RuntimeGraphRecorder,
        user_id: str,
        user_message: str,
        setup: AgentToolLoopSetup,
        payload: dict[str, Any],
        prompt_payload_format: str,
        context_mode: str = "full",
        **kwargs: Any,
    ) -> None:
        # Persist scratchpad state back to graph meta after tool loop completes.
        if setup.scratchpad and context_mode == "scratchpad":
            ScratchpadService(
                execution_graph_service=self._execution_graph_service,
            ).save(
                recorder.graph_id,
                setup.scratchpad,
                updated_by=user_id,
            )
