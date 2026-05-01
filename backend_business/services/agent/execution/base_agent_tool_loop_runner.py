"""Template runner for standalone agent tool-loop paths."""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from backend_business.services.agent.experience import (
    ExperienceOrchestrator,
    ExperiencePolicyResolver,
    SkillLoader,
    SkillRegistry,
    SkillRetriever,
    resolve_experience_target,
)
from backend_business.services.agent.execution.tool_loop_runner import (
    ToolLoopResult,
    ToolLoopRunner,
)
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.runtime.scratchpad import Scratchpad


@dataclass(frozen=True)
class AgentToolLoopSetup:
    """Agent-specific setup needed by the generic ToolLoopRunner."""

    context: dict[str, Any]
    prompt_builder: Any
    scratchpad: Scratchpad | None = None
    enable_complete_phase: bool = False


class BaseAgentToolLoopRunner:
    """Shared template for business-agent standalone tool-loop adapters."""

    agent_type: str = ""
    task_description: str = "Agent 经典 tool-loop 执行阶段"

    def __init__(
        self,
        *,
        ai_proxy_client: Any,
        tools: Any,
        execution_graph_service: ExecutionGraphService,
        prompt_builder: Any,
        max_tool_call_rounds: int,
        stage_container_key: str,
        node_key_prefix: str,
        actor_manager_getter: Callable[[], Any] | None = None,
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
        self._actor_manager_getter = actor_manager_getter
        self._experience_retriever = experience_retriever or SkillRetriever()
        self._skill_loader = skill_loader or SkillLoader()
        self._experience_orchestrator = experience_orchestrator
        self._skill_registry = skill_registry or SkillRegistry(
            self._experience_retriever.root_path
        )
        self._policies = policies or ExperiencePolicyResolver()

    def run(
        self,
        *,
        recorder: Any,
        user_id: str,
        user_message: str,
        **kwargs: Any,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        setup = self.build_tool_loop_setup(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            **kwargs,
        )
        context = setup.context
        self._inject_experience_skill_context(
            context=context,
            user_message=user_message,
        )

        node_key_prefix = self._node_key_prefix
        runner = ToolLoopRunner(
            ai_proxy_client=self._ai_proxy_client,
            tool_executor=self._tools,
            prompt_builder=setup.prompt_builder,
            max_tool_call_rounds=self._max_tool_call_rounds,
            stage_container_key=self._stage_container_key,
            stage_node_key_builder=lambda round_index: (
                f"{node_key_prefix}_tool_loop_round_{round_index}"
            ),
            stage_label_builder=lambda round_index: f"Tool Loop Round {round_index}",
            actor_manager_getter=self._actor_manager_getter,
            graph_meta_patcher=(
                lambda graph_id, meta_patch, updated_by: self._execution_graph_service.patch_graph_meta(
                    graph_id,
                    meta_patch,
                    updated_by=updated_by,
                )
            ),
            graph_meta_patch_builder=lambda ctx: self.build_meta_patch(ctx),
            scratchpad=setup.scratchpad,
            enable_complete_phase=setup.enable_complete_phase,
        )

        result: ToolLoopResult | None = None
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
                context=context,
                missed=run_error is not None,
            )
            self._maybe_writeback_experience(
                recorder=recorder,
                user_message=user_message,
                result=result,
                error=run_error,
            )

        if result is None:
            raise RuntimeError("ToolLoopRunner completed without a result")
        payload = self.postprocess_result(
            result=result,
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            setup=setup,
            **kwargs,
        )
        self.after_tool_loop(
            result=result,
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            setup=setup,
            payload=payload,
            **kwargs,
        )
        return payload

    def build_tool_loop_setup(
        self,
        *,
        recorder: Any,
        user_id: str,
        user_message: str,
        **kwargs: Any,
    ) -> AgentToolLoopSetup:
        raise NotImplementedError

    def build_meta_patch(self, context: dict[str, Any]) -> dict[str, Any]:
        return self._build_injected_skill_meta_patch(context)

    def postprocess_result(
        self,
        *,
        result: ToolLoopResult,
        recorder: Any,
        user_id: str,
        user_message: str,
        setup: AgentToolLoopSetup,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.normalize_result_payload(result)

    def after_tool_loop(
        self,
        *,
        result: ToolLoopResult,
        recorder: Any,
        user_id: str,
        user_message: str,
        setup: AgentToolLoopSetup,
        payload: dict[str, Any],
        **kwargs: Any,
    ) -> None:
        return None

    @staticmethod
    def normalize_result_payload(result: ToolLoopResult) -> dict[str, Any]:
        return {
            "tool_loop_reply": result.tool_loop_reply,
            "context": result.context,
            "rounds": result.rounds,
            "phase_completed": result.phase_completed,
            "route_key": result.route_key,
            "conclusion": result.conclusion,
        }

    @staticmethod
    def _build_injected_skill_meta_patch(context: dict[str, Any]) -> dict[str, Any]:
        patch: dict[str, Any] = {}
        injected_skill_id = str(context.get("_injected_skill_id") or "").strip()
        if injected_skill_id:
            patch["injected_skill_id"] = injected_skill_id
        injected_skill_ids = [
            str(item).strip()
            for item in (context.get("_injected_skill_ids") or [])
            if str(item).strip()
        ]
        if injected_skill_ids:
            patch["injected_skill_ids"] = injected_skill_ids
        injected_skill_target_id = str(
            context.get("_injected_skill_target_id") or ""
        ).strip()
        if injected_skill_target_id:
            patch["injected_skill_target_id"] = injected_skill_target_id
        injected_shared_skill_ids = [
            str(item).strip()
            for item in (context.get("_injected_shared_skill_ids") or [])
            if str(item).strip()
        ]
        if injected_shared_skill_ids:
            patch["injected_shared_skill_ids"] = injected_shared_skill_ids
        return patch

    def _resolve_experience_target(self) -> Any:
        return resolve_experience_target(
            container_key=self._stage_container_key,
            agent_type=self.agent_type,
            node_type="llm",
        )

    def _inject_experience_skill_context(
        self,
        *,
        context: dict[str, Any],
        user_message: str,
    ) -> None:
        target = self._resolve_experience_target()
        if target is None:
            return
        retrieved_skills = self._experience_retriever.retrieve_for_injection(
            target=target,
            user_message=user_message,
            task_description=self.task_description,
        )
        if not retrieved_skills:
            return
        loaded_prompt = self._skill_loader.render_prompt_bundle(
            retrieved_skills=retrieved_skills,
            relevance_text=self.task_description,
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
            context["_injected_shared_skill_ids"] = list(
                loaded_prompt.shared_skill_ids
            )

    def _record_injection_feedback(
        self,
        *,
        context: dict[str, Any],
        missed: bool,
    ) -> None:
        target = self._resolve_experience_target()
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
        recorder: Any,
        user_message: str,
        result: ToolLoopResult | None,
        error: Exception | None,
    ) -> None:
        if self._experience_orchestrator is None:
            return
        target = self._resolve_experience_target()
        self._experience_orchestrator.safe_process_outcome(
            target=target,
            graph_id=str(recorder.graph_id or ""),
            graph_service=self._execution_graph_service,
            recorder=recorder,
            scratchpad_snapshot=[],
            container_key=self._stage_container_key,
            user_message=user_message,
            task_description=self.task_description,
            final_conclusion=(result.tool_loop_reply if result is not None else None),
            runtime_status="failed" if error is not None else "succeeded",
            final_error=str(error) if error is not None else None,
        )
