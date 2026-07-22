"""Requirement classification agent chat orchestration service."""

from __future__ import annotations

import json
from collections.abc import Generator
from typing import Any

import requests
from backend_business.config import settings
from backend_business.services.agent.execution.graph_executor import GraphExecutor
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.experience import ExperienceOrchestrator
from backend_business.services.agent.runtime.agent_execution_service import (
    AgentExecutionService,
)
from backend_business.services.agent.runtime.session_graph_store import AgentSessionGraphStore
from backend_business.services.agent.tools import RequirementClassificationTools
from backend_business.services.ai_chat_service import AiChatService, ai_chat_service
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.requirements_manage_service import RequirementsManageService

from .definition import REQUIREMENT_CLASSIFICATION_AGENT_DEFINITION
from .prompt_builder import RequirementClassificationPromptBuilder
from .runtime_graph_recorder import RequirementClassificationGraphRecorder
from .tool_loop_runner import (
    RequirementClassificationToolLoopRunner,
    extract_latest_classification_result,
)


class RequirementClassificationAgentService:
    MAX_TOOL_CALL_ROUNDS = REQUIREMENT_CLASSIFICATION_AGENT_DEFINITION.max_tool_call_rounds
    AGENT_TYPE = REQUIREMENT_CLASSIFICATION_AGENT_DEFINITION.agent_type

    def __init__(
        self,
        *,
        chat_storage: AiChatService | None,
        execution_graph_service: ExecutionGraphService | None = None,
        requirements_service: RequirementsManageService | None = None,
        tools: RequirementClassificationTools | None = None,
        ai_proxy_client: Any = None,
        prompt_builder: RequirementClassificationPromptBuilder | None = None,
    ) -> None:
        self.chat_storage = chat_storage
        self.execution_graph_service = execution_graph_service or ExecutionGraphService(
            settings.POSTGRES_DSN
        )
        self.requirements_service = requirements_service or RequirementsManageService(
            settings.POSTGRES_DSN
        )
        self.ai_proxy = ai_proxy_client or ai_proxy
        self.prompt_builder = prompt_builder or RequirementClassificationPromptBuilder()
        self.tools = tools or RequirementClassificationTools(
            requirements_service=self.requirements_service,
            chat_completion_fn=self.ai_proxy.chat_completion,
        )
        self._session_graph_store = AgentSessionGraphStore(
            chat_storage=chat_storage,
            execution_graph_service=self.execution_graph_service,
            agent_type=self.AGENT_TYPE,
            context_mode_normalizer=lambda value: value or "full",
            create_or_get_updates_unchanged=True,
        )
        self._execution_service = AgentExecutionService(
            definition=REQUIREMENT_CLASSIFICATION_AGENT_DEFINITION,
            chat_storage=chat_storage,
            session_graph_store=self._session_graph_store,
        )

    def _hydrate_session_graph(self, session: dict[str, Any]) -> dict[str, Any]:
        return self._session_graph_store.hydrate_session_graph(session)

    def _resolve_session_graph_target(
        self,
        *,
        session: dict[str, Any],
        project_id: str | None,
    ) -> dict[str, str | None]:
        return self._session_graph_store.resolve_session_graph_target(
            session=session,
            project_id=project_id,
        )

    def create_or_get_session(
        self,
        user_id: str,
        project_id: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        return self._session_graph_store.create_or_get_session(
            user_id=user_id,
            project_id=project_id,
            prompt_payload_format=prompt_payload_format,
            context_mode=context_mode,
        )

    def create_session(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        title: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        return self._session_graph_store.create_session(
            user_id=user_id,
            project_id=project_id,
            title=title,
            prompt_payload_format=prompt_payload_format,
            context_mode=context_mode,
        )

    def update_session(
        self,
        *,
        session_id: str,
        user_id: str,
        title: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        return self._session_graph_store.update_session(
            session_id=session_id,
            user_id=user_id,
            title=title,
            prompt_payload_format=prompt_payload_format,
            context_mode=context_mode,
        )

    def list_sessions(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self._session_graph_store.list_sessions(
            user_id=user_id,
            project_id=project_id,
            limit=limit,
        )

    @staticmethod
    def _sort_session_graphs_as_chain(graphs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        return AgentSessionGraphStore.sort_session_graphs_as_chain(graphs)

    def list_session_graph_chain(
        self,
        *,
        session_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        return self._session_graph_store.list_session_graph_chain(
            session_id=session_id,
            user_id=user_id,
        )

    def delete_session(self, *, session_id: str, user_id: str) -> bool:
        return self._session_graph_store.delete_session(
            session_id=session_id,
            user_id=user_id,
        )

    def list_messages(
        self, *, session_id: str, user_id: str, limit: int = 100
    ) -> list[dict[str, Any]]:
        return self._session_graph_store.list_messages(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
        )

    def get_graph_detail(self, graph_id: str) -> dict[str, Any]:
        return self._session_graph_store.get_graph_detail(graph_id)

    def get_graph(self, graph_id: str) -> dict[str, Any] | None:
        return self._session_graph_store.get_graph(graph_id)

    def _graph_ai_proxy_client(self, *, model: str, use_thinking_mode: bool) -> Any:
        with_defaults = getattr(self.ai_proxy, "with_defaults", None)
        if callable(with_defaults):
            return with_defaults(model=model, thinking_enabled=use_thinking_mode)
        return self.ai_proxy

    def _stream_llm_reply(
        self,
        *,
        prompt: str,
        system_prompt: str,
        model: str = "deepseek-v4-pro",
        use_thinking_mode: bool = True,
        max_new_tokens: int = 1200,
    ) -> Generator[dict[str, Any], None, str]:
        response = requests.post(
            f"{settings.INFERENCE_BASE_URL.rstrip('/')}/chat/stream",
            json={
                "prompt": prompt,
                "system_prompt": system_prompt,
                "model": model,
                "max_new_tokens": max_new_tokens,
                "use_thinking_mode": use_thinking_mode,
                "use_async_client": False,
            },
            stream=True,
            timeout=180,
        )
        response.raise_for_status()

        full_content = ""
        for raw_line in response.iter_lines():
            if not raw_line:
                continue
            try:
                payload = json.loads(raw_line.decode("utf-8"))
            except json.JSONDecodeError:
                continue
            if payload.get("type") == "token":
                token = payload.get("content", "")
                full_content += token
                yield {"event": "token", "data": {"content": token}}
            elif payload.get("type") == "result":
                answer = payload.get("data", {}).get("answer")
                if isinstance(answer, str) and answer.strip():
                    full_content = answer
        return full_content.strip()

    def _build_final_reply_prompt(
        self,
        *,
        user_message: str,
        tool_loop_reply: str,
        mode: str,
        context: dict[str, Any],
    ) -> tuple[str, str]:
        return self.prompt_builder.build_final_reply_prompt(
            user_message=user_message,
            tool_loop_reply=tool_loop_reply,
            mode=mode,
            context=context,
        )

    def _normalize_mode(self, context: dict[str, Any]) -> str:
        return self.prompt_builder.normalize_mode(context)

    def _run_tool_call_loop(
        self,
        *,
        recorder: RequirementClassificationGraphRecorder | Any,
        user_id: str,
        user_message: str,
        project_id: str,
        requirement_id: str | None,
        session_id: str,
        ai_proxy_client: Any | None = None,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        runner = RequirementClassificationToolLoopRunner(
            ai_proxy_client=ai_proxy_client or self.ai_proxy,
            tools=self.tools,
            execution_graph_service=self.execution_graph_service,
            prompt_builder=self.prompt_builder,
            max_tool_call_rounds=self.MAX_TOOL_CALL_ROUNDS,
            experience_orchestrator=ExperienceOrchestrator(),
        )
        executor = GraphExecutor(experience_orchestrator=ExperienceOrchestrator())
        result = yield from executor.execute_agent_tool_loop(
            agent_runner=runner,
            graph_service=self.execution_graph_service,
            recorder=recorder,
            actor=user_id,
            user_message=user_message,
            runner_kwargs={
                "project_id": project_id,
                "requirement_id": requirement_id,
                "session_id": session_id,
            },
        )
        if result.status == "failed":
            raise RuntimeError(result.error or "GraphExecutor 执行失败")
        return (result.metadata or {}).get("payload") or {}

    def run_inline_tool_loop(
        self,
        *,
        recorder: Any,
        user_id: str,
        user_message: str,
        project_id: str,
        requirement_id: str | None = None,
        container_key: str = "requirement_classification_agent",
        node_key_prefix: str = "requirement_classification_agent",
    ) -> dict[str, Any]:
        gen = self.stream_inline_tool_loop(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            project_id=project_id,
            requirement_id=requirement_id,
            container_key=container_key,
            node_key_prefix=node_key_prefix,
        )
        result: dict[str, Any] | None = None
        try:
            while True:
                next(gen)
        except StopIteration as stop:
            result = stop.value or {}
        return result

    def stream_inline_tool_loop(
        self,
        *,
        recorder: Any,
        user_id: str,
        user_message: str,
        project_id: str,
        requirement_id: str | None = None,
        container_key: str = "requirement_classification_agent",
        node_key_prefix: str = "requirement_classification_agent",
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        runner = RequirementClassificationToolLoopRunner(
            ai_proxy_client=self.ai_proxy,
            tools=self.tools,
            execution_graph_service=self.execution_graph_service,
            prompt_builder=self.prompt_builder,
            max_tool_call_rounds=self.MAX_TOOL_CALL_ROUNDS,
            stage_container_key=container_key,
            node_key_prefix=node_key_prefix,
            experience_orchestrator=ExperienceOrchestrator(),
        )
        result = yield from runner.run(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            project_id=project_id,
            requirement_id=requirement_id,
            session_id="",
        )
        context = result.get("context") or {}
        return {
            "status": "success",
            "tool_loop_reply": result.get("tool_loop_reply", ""),
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            "classification_result": context.get("classification_result"),
        }

    def stream_requirement_classification_agent_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
        requirement_id: str | None = None,
        model: str = "deepseek-v4-pro",
        use_thinking_mode: bool = True,
    ) -> Generator[dict[str, Any], None, None]:
        turn = self._execution_service.begin_turn(
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            user_message=user_message,
            user_metadata={
                "requirement_id": requirement_id,
                "model": model,
                "use_thinking_mode": use_thinking_mode,
            },
        )
        yield {"event": "user_message", "data": turn.user_record}

        recorder = self._execution_service.create_recorder(
            turn=turn,
            recorder_factory=RequirementClassificationGraphRecorder,
            execution_graph_service=self.execution_graph_service,
            requirement_id=requirement_id,
        )
        self.execution_graph_service.patch_graph_meta(
            recorder.graph_id,
            {
                "current_node_key": None,
                "intent": "pending",
                "final_reply": None,
                "user_message": user_message,
                "requirement_id": requirement_id,
                "resolved_requirement_id": requirement_id,
                "classification_result": None,
                "active_turn_index": recorder.turn_index,
            },
            status="running",
            updated_by=user_id,
        )
        yield {"event": "graph", "data": {"graph_id": recorder.graph_id}}

        assistant_content = ""
        tool_loop_reply = ""
        classification_result: dict[str, Any] | None = None
        resolved_requirement_id = requirement_id
        mode = "clarification"

        try:
            recorder.start_stage(
                node_key=recorder.stage_node_key("user_input"),
                label=recorder.stage_label("User Input"),
                node_type="start",
                role_type="human",
                container_key="human_input",
                created_by=user_id,
                input_summary={"message": user_message, "requirement_id": requirement_id},
                edge_type_from_previous="call" if recorder.turn_index > 1 else None,
            )
            recorder.complete_stage(
                recorder.stage_node_key("user_input"),
                created_by=user_id,
                output_summary={"accepted": True},
            )
            yield {
                "event": "stage",
                "data": {
                    "graph_id": recorder.graph_id,
                    "node_key": recorder.stage_node_key("user_input"),
                    "status": "succeeded",
                },
            }

            tool_loop = self._run_tool_call_loop(
                recorder=recorder,
                user_id=user_id,
                user_message=user_message,
                project_id=project_id,
                requirement_id=requirement_id,
                session_id=session_id,
                ai_proxy_client=self._graph_ai_proxy_client(
                    model=model,
                    use_thinking_mode=use_thinking_mode,
                ),
            )
            loop_result = yield from self._execution_service.stream_generator(tool_loop)
            loop_result = loop_result or {}
            tool_loop_reply = loop_result.get("tool_loop_reply") or ""
            context: dict[str, Any] = loop_result.get("context") or {}

            resolved_requirement_id, classification_result = extract_latest_classification_result(
                context
            )
            context["resolved_requirement_id"] = resolved_requirement_id
            context["classification_result"] = classification_result
            mode = self._normalize_mode(context)

            recorder.start_stage(
                node_key=recorder.stage_node_key("conductor_reply"),
                label=recorder.stage_label("Conductor Reply"),
                node_type="end",
                role_type="agent",
                container_key="conductor",
                created_by=user_id,
                input_summary={
                    "mode": mode,
                    "tool_loop_reply": tool_loop_reply,
                    "resolved_requirement_id": resolved_requirement_id,
                },
                edge_type_from_previous="return",
            )
            yield {
                "event": "stage",
                "data": {
                    "graph_id": recorder.graph_id,
                    "node_key": recorder.stage_node_key("conductor_reply"),
                    "status": "running",
                },
            }

            final_system_prompt, final_prompt = self._build_final_reply_prompt(
                user_message=user_message,
                tool_loop_reply=tool_loop_reply,
                mode=mode,
                context=context,
            )
            stream = self._stream_llm_reply(
                prompt=final_prompt,
                system_prompt=final_system_prompt,
                model=model,
                use_thinking_mode=use_thinking_mode,
            )
            while True:
                try:
                    event = next(stream)
                except StopIteration as stop:
                    assistant_content = (stop.value or "").strip()
                    break
                yield event

            if not assistant_content:
                assistant_content = tool_loop_reply or "已完成需求分类。"

            recorder.complete_stage(
                recorder.stage_node_key("conductor_reply"),
                created_by=user_id,
                output_summary={
                    "reply": assistant_content,
                    "mode": mode,
                    "classification_result": classification_result,
                },
            )
            yield {
                "event": "stage",
                "data": {
                    "graph_id": recorder.graph_id,
                    "node_key": recorder.stage_node_key("conductor_reply"),
                    "status": "succeeded",
                },
            }

            meta_patch = {
                "intent": mode,
                "resolved_requirement_id": resolved_requirement_id,
                "classification_result": classification_result,
                "turn_count": recorder.turn_index,
                "active_turn_index": recorder.turn_index,
            }
            if mode == "clarification":
                recorder.suspend_graph(
                    created_by=user_id,
                    final_reply=assistant_content,
                    meta_patch=meta_patch,
                )
            else:
                recorder.succeed_graph(
                    created_by=user_id,
                    final_reply=assistant_content,
                    meta_patch=meta_patch,
                )

            assistant_message = self._execution_service.persist_assistant(
                turn=turn,
                content=assistant_content,
                metadata={
                    "graph_id": recorder.graph_id,
                    "requested_requirement_id": requirement_id,
                    "resolved_requirement_id": resolved_requirement_id,
                    "classification_result": classification_result,
                    "mode": mode,
                },
                is_read=False,
            )
            yield {"event": "assistant_message", "data": assistant_message}
            yield {
                "event": "result",
                "data": {
                    "graph_id": recorder.graph_id,
                    "reply_text": assistant_message["content"],
                    "classification_result": classification_result,
                    "resolved_requirement_id": resolved_requirement_id,
                    "mode": mode,
                },
            }
        except Exception as exc:
            error_text = f"需求分类 Agent 执行失败: {exc}"
            try:
                recorder.fail_graph(
                    created_by=user_id,
                    error=error_text,
                    meta_patch={"intent": "failed"},
                )
            except Exception:
                pass
            error_message = self._execution_service.persist_error(
                turn=turn,
                graph_id=recorder.graph_id,
                error=error_text,
            )
            yield {
                "event": "error",
                "data": {
                    "error": error_text,
                    "message": error_message,
                    "graph_id": recorder.graph_id,
                },
            }


requirement_classification_agent_service = RequirementClassificationAgentService(
    chat_storage=ai_chat_service,
)
