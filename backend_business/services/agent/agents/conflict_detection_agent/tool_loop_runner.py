"""Conflict-detection-agent adapter for generic tool-call loop execution."""

from __future__ import annotations

from collections.abc import Generator
from datetime import datetime, timezone
from typing import Any

from backend_business.services.agent.execution.tool_loop_runner import ToolLoopRunner
from backend_business.services.agent.experience import (
    ExperienceOrchestrator,
    ExperiencePolicyResolver,
    SkillLoader,
    SkillRegistry,
    SkillRetriever,
    resolve_experience_target,
)
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.tools import ConflictDetectionTools

from .prompt_builder import ConflictDetectionPromptBuilder
from .runtime_graph_recorder import ConflictDetectionGraphRecorder


class ConflictDetectionToolLoopRunner:
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
        self._ai_proxy_client = ai_proxy_client
        self._tools = tools
        self._execution_graph_service = execution_graph_service
        self._prompt_builder = prompt_builder
        self._max_tool_call_rounds = max_tool_call_rounds
        self._stage_container_key = stage_container_key
        self._node_key_prefix = node_key_prefix
        self._experience_retriever = experience_retriever or SkillRetriever()
        self._skill_loader = skill_loader or SkillLoader()
        self._experience_orchestrator = experience_orchestrator
        self._skill_registry = skill_registry or SkillRegistry(self._experience_retriever.root_path)
        self._policies = policies or ExperiencePolicyResolver()

    def run(
        self,
        *,
        recorder: ConflictDetectionGraphRecorder,
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
        }
        self._inject_experience_skill_context(
            context=context,
            user_message=user_message,
        )
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
            graph_meta_patch_builder=lambda context: {
                **(
                    {"injected_skill_id": context.get("_injected_skill_id")}
                    if str(context.get("_injected_skill_id") or "").strip()
                    else {}
                ),
                **(
                    {"injected_skill_ids": context.get("_injected_skill_ids")}
                    if context.get("_injected_skill_ids")
                    else {}
                ),
                **(
                    {"injected_skill_target_id": context.get("_injected_skill_target_id")}
                    if str(context.get("_injected_skill_target_id") or "").strip()
                    else {}
                ),
                **(
                    {"injected_shared_skill_ids": context.get("_injected_shared_skill_ids")}
                    if context.get("_injected_shared_skill_ids")
                    else {}
                ),
            },
        )
        result = None
        run_error: Exception | None = None
        gen = runner.run(
            recorder=recorder,
            user_id=user_id,
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
            self._record_injection_feedback(
                user_message=user_message,
                context=context,
                missed=run_error is not None,
            )
            self._maybe_writeback_experience(
                recorder=recorder,
                user_message=user_message,
                result=result,
                error=run_error,
            )
        return {
            "tool_loop_reply": result.tool_loop_reply,
            "context": result.context,
            "rounds": result.rounds,
            "phase_completed": result.phase_completed,
            "route_key": result.route_key,
            "conclusion": result.conclusion,
        }

    def _inject_experience_skill_context(
        self,
        *,
        context: dict[str, Any],
        user_message: str,
    ) -> None:
        target = resolve_experience_target(
            container_key=self._stage_container_key,
            agent_type="conflict_detection",
            node_type="llm",
        )
        if target is None:
            return
        retrieved_skills = self._experience_retriever.retrieve_for_injection(
            target=target,
            user_message=user_message,
            task_description="需求冲突检测 Agent 经典 tool-loop 执行阶段",
        )
        if not retrieved_skills:
            return
        loaded_prompt = self._skill_loader.render_prompt_bundle(
            retrieved_skills=retrieved_skills,
        )
        existing_context = str(context.get("_extra_system_context") or "").strip()
        context["_extra_system_context"] = (
            f"{existing_context}\n\n{loaded_prompt.prompt_text}"
            if existing_context
            else loaded_prompt.prompt_text
        )
        context["_injected_skill_id"] = loaded_prompt.skill_id
        context["_injected_skill_ids"] = list(loaded_prompt.skill_ids)
        context["_injected_skill_target_id"] = loaded_prompt.target_id
        if loaded_prompt.shared_skill_ids:
            context["_injected_shared_skill_ids"] = list(loaded_prompt.shared_skill_ids)

    def _record_injection_feedback(
        self,
        *,
        user_message: str,
        context: dict[str, Any],
        missed: bool,
    ) -> None:
        target = resolve_experience_target(
            container_key=self._stage_container_key,
            agent_type="conflict_detection",
            node_type="llm",
        )
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

    def _maybe_writeback_experience(
        self,
        *,
        recorder: ConflictDetectionGraphRecorder,
        user_message: str,
        result: Any,
        error: Exception | None,
    ) -> None:
        if self._experience_orchestrator is None:
            return
        target = resolve_experience_target(
            container_key=self._stage_container_key,
            agent_type="conflict_detection",
            node_type="llm",
        )
        self._experience_orchestrator.safe_process_outcome(
            target=target,
            graph_id=str(recorder.graph_id or ""),
            graph_service=self._execution_graph_service,
            recorder=recorder,
            scratchpad_snapshot=[],
            container_key=self._stage_container_key,
            user_message=user_message,
            task_description="需求冲突检测 Agent 经典 tool-loop 执行阶段",
            final_conclusion=(result.tool_loop_reply if result is not None else None),
            runtime_status="failed" if error is not None else "succeeded",
            final_error=str(error) if error is not None else None,
        )
