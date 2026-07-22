"""Requirement agent chat orchestration service."""

from __future__ import annotations

import asyncio
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
from backend_business.services.agent.tools import RequirementAgentTools
from backend_business.services.ai_chat_service import AiChatService, ai_chat_service
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.requirement_change_approval_service import (
    RequirementChangeApprovalService,
)
from backend_business.services.requirements_manage_service import RequirementsManageService

from .actor_runtime import RequirementAgentActorRuntime
from .constants import DEFAULT_PROMPT_PAYLOAD_FORMAT
from .definition import REQUIREMENT_AGENT_DEFINITION
from .payload_codec import normalize_prompt_payload_format
from .prompt_builder import RequirementAgentPromptBuilder
from .runtime_graph_recorder import _RuntimeGraphRecorder
from .tool_loop_runner import RequirementAgentToolLoopRunner
from .utils import inference_url


class RequirementAgentChatService:
    MAX_TOOL_CALL_ROUNDS = REQUIREMENT_AGENT_DEFINITION.max_tool_call_rounds
    AGENT_TYPE = REQUIREMENT_AGENT_DEFINITION.agent_type

    def __init__(
        self,
        *,
        chat_storage: AiChatService | None,
        execution_graph_service: ExecutionGraphService | None = None,
        requirements_service: RequirementsManageService | None = None,
        tools: RequirementAgentTools | None = None,
        approval_service: RequirementChangeApprovalService | None = None,
        ai_proxy_client: Any = None,
        actor_runtime: RequirementAgentActorRuntime | None = None,
        prompt_builder: RequirementAgentPromptBuilder | None = None,
    ) -> None:
        self.chat_storage = chat_storage
        self.execution_graph_service = execution_graph_service or ExecutionGraphService(
            settings.POSTGRES_DSN
        )
        self.requirements_service = requirements_service or RequirementsManageService(
            settings.POSTGRES_DSN
        )
        self.ai_proxy = ai_proxy_client or ai_proxy
        self.actor_runtime = actor_runtime or RequirementAgentActorRuntime()
        self.prompt_builder = prompt_builder or RequirementAgentPromptBuilder()
        self.approval_service = approval_service or RequirementChangeApprovalService(
            requirements_service=self.requirements_service,
            chat_storage=self.chat_storage,
            execution_graph_service=self.execution_graph_service,
            actor_runtime=self.actor_runtime,
        )
        self.tools = tools or RequirementAgentTools(
            requirements_service=self.requirements_service,
            actor_query_fn=self._actor_query,
            actor_write_fn=self._actor_write,
            approval_service=self.approval_service,
            ai_proxy_client=self.ai_proxy,
            actor_manager_getter=self._get_actor_manager,
        )
        self._session_graph_store = AgentSessionGraphStore(
            chat_storage=chat_storage,
            execution_graph_service=self.execution_graph_service,
            agent_type=self.AGENT_TYPE,
            prompt_payload_normalizer=normalize_prompt_payload_format,
            create_or_get_prompt_update_policy="truthy",
            create_or_get_context_update_policy="allowed",
        )
        self._execution_service = AgentExecutionService(
            definition=REQUIREMENT_AGENT_DEFINITION,
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

    def _get_actor_manager(self):
        return self.actor_runtime.get_actor_manager()

    def _ensure_actor_loop(self) -> asyncio.AbstractEventLoop:
        return self.actor_runtime.ensure_actor_loop()

    def _run_actor_coro(self, coro):
        return self.actor_runtime.run_actor_coro(coro)

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
            f"{inference_url()}/chat/stream",
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

    def _actor_query(self, actor_manager, requirement_id: str) -> dict[str, Any]:
        return self.actor_runtime.actor_query(actor_manager, requirement_id)

    def _actor_write(
        self, actor_manager, requirement_id: str, command: dict[str, Any]
    ) -> dict[str, Any]:
        return self.actor_runtime.actor_write(actor_manager, requirement_id, command)

    def _build_tool_loop_system_prompt(self) -> str:
        return self.prompt_builder.build_tool_loop_system_prompt()

    def _build_tool_loop_user_message(
        self,
        *,
        project_id: str,
        user_message: str,
        requirement_id: str | None,
        historical_node_context: list[dict[str, Any]] | None = None,
        prompt_payload_format: str = DEFAULT_PROMPT_PAYLOAD_FORMAT,
    ) -> str:
        return self.prompt_builder.build_tool_loop_user_message(
            project_id=project_id,
            user_message=user_message,
            requirement_id=requirement_id,
            historical_node_context=historical_node_context,
            prompt_payload_format=prompt_payload_format,
        )

    def _build_final_reply_prompt(
        self,
        *,
        user_message: str,
        tool_loop_reply: str,
        mode: str,
        context: dict[str, Any],
        prompt_payload_format: str = DEFAULT_PROMPT_PAYLOAD_FORMAT,
    ) -> tuple[str, str]:
        return self.prompt_builder.build_final_reply_prompt(
            user_message=user_message,
            tool_loop_reply=tool_loop_reply,
            mode=mode,
            context=context,
            prompt_payload_format=prompt_payload_format,
        )

    def _build_tool_loop_input_summary(
        self,
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return self.prompt_builder.build_tool_loop_input_summary(
            round_index=round_index,
            messages=messages,
            context=context,
        )

    def _normalize_mode(self, context: dict[str, Any]) -> str:
        return self.prompt_builder.normalize_mode(context)

    def _run_tool_call_loop(
        self,
        *,
        recorder: _RuntimeGraphRecorder,
        user_id: str,
        user_message: str,
        project_id: str,
        requirement_id: str | None,
        session_id: str,
        prompt_payload_format: str,
        context_mode: str,
        ai_proxy_client: Any | None = None,
        max_tool_call_rounds: int | None = None,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        runner = RequirementAgentToolLoopRunner(
            ai_proxy_client=ai_proxy_client or self.ai_proxy,
            tools=self.tools,
            execution_graph_service=self.execution_graph_service,
            actor_manager_getter=self._get_actor_manager,
            prompt_builder=self.prompt_builder,
            max_tool_call_rounds=max_tool_call_rounds or self.MAX_TOOL_CALL_ROUNDS,
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
                "prompt_payload_format": prompt_payload_format,
                "context_mode": context_mode,
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
        session_id: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
        max_tool_call_rounds: int | None = None,
        requirement_id: str | None = None,
        container_key: str = "requirement_agent",
        node_key_prefix: str = "requirement_agent",
    ) -> dict[str, Any]:
        """Run tool loop inline within an external recorder (no child graph).

        This allows the Session Controller to embed the requirement agent's
        tool-loop nodes directly into its own execution graph rather than
        creating a separate child graph.
        """
        gen = self.stream_inline_tool_loop(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            project_id=project_id,
            session_id=session_id,
            prompt_payload_format=prompt_payload_format,
            context_mode=context_mode,
            max_tool_call_rounds=max_tool_call_rounds,
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
        session_id: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
        max_tool_call_rounds: int | None = None,
        requirement_id: str | None = None,
        container_key: str = "requirement_agent",
        node_key_prefix: str = "requirement_agent",
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        """Stream inline tool-loop events within an external recorder."""
        normalized_prompt_payload_format = normalize_prompt_payload_format(
            prompt_payload_format,
            default="markdown",
        )
        normalized_context_mode = (
            context_mode if context_mode in ("full", "incremental", "scratchpad") else "full"
        )
        runner = RequirementAgentToolLoopRunner(
            ai_proxy_client=self.ai_proxy,
            tools=self.tools,
            execution_graph_service=self.execution_graph_service,
            actor_manager_getter=self._get_actor_manager,
            prompt_builder=self.prompt_builder,
            max_tool_call_rounds=max_tool_call_rounds or self.MAX_TOOL_CALL_ROUNDS,
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
            session_id=session_id or "",
            prompt_payload_format=normalized_prompt_payload_format,
            context_mode=normalized_context_mode,
        )
        context = result.get("context") or {}
        approval_result = context.get("last_approval_result")
        mode = self._normalize_mode(context)
        return {
            "status": "success",
            "tool_loop_reply": result.get("tool_loop_reply", ""),
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            "write_result": context.get("last_write_result"),
            "mode": mode,
            "clarification_required": mode == "clarification",
            "approval_pending": bool(context.get("approval_pending")),
            "approval_result": approval_result,
        }

    def stream_requirement_agent_reply(
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
        session = turn.session
        prompt_payload_format = normalize_prompt_payload_format(
            session.get("prompt_payload_format"),
            default=DEFAULT_PROMPT_PAYLOAD_FORMAT,
        )
        context_mode = session.get("context_mode") or "full"
        yield {"event": "user_message", "data": turn.user_record}

        recorder = self._execution_service.create_recorder(
            turn=turn,
            recorder_factory=_RuntimeGraphRecorder,
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
                "active_turn_index": recorder.turn_index,
            },
            status="running",
            updated_by=user_id,
        )
        yield {"event": "graph", "data": {"graph_id": recorder.graph_id}}

        assistant_content = ""
        tool_loop_reply = ""
        mode = "chat"
        context: dict[str, Any] = {}
        write_result: dict[str, Any] | None = None

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
                prompt_payload_format=prompt_payload_format,
                context_mode=context_mode,
                ai_proxy_client=self._graph_ai_proxy_client(
                    model=model,
                    use_thinking_mode=use_thinking_mode,
                ),
            )
            loop_result = yield from self._execution_service.stream_generator(tool_loop)
            loop_result = loop_result or {}
            tool_loop_reply = loop_result.get("tool_loop_reply") or ""
            context = loop_result.get("context") or {}

            mode = self._normalize_mode(context)
            write_result = context.get("last_write_result")
            approval_result = context.get("last_approval_result")

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
                    "resolved_requirement_id": context.get("resolved_requirement_id"),
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

            if context.get("approval_pending"):
                assistant_content = (
                    "我已把这次需求修改申请发送到移动端待审界面的变更通知。"
                    "在你同意之前，需求不会被修改；同意后会立即生效。"
                )
            else:
                final_system_prompt, final_prompt = self._build_final_reply_prompt(
                    user_message=user_message,
                    tool_loop_reply=tool_loop_reply,
                    mode=mode,
                    context=context,
                    prompt_payload_format=prompt_payload_format,
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
                    assistant_content = tool_loop_reply or "已处理。"

            recorder.complete_stage(
                recorder.stage_node_key("conductor_reply"),
                created_by=user_id,
                output_summary={
                    "reply": assistant_content,
                    "mode": mode,
                    "write_result": write_result,
                    "approval_result": approval_result,
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
                "resolved_requirement_id": context.get("resolved_requirement_id"),
                "turn_count": recorder.turn_index,
                "active_turn_index": recorder.turn_index,
            }
            if approval_result:
                meta_patch.update(
                    {
                        "approval_request_id": approval_result.get("approval_request_id"),
                        "approval_push_message_id": approval_result.get("push_message_id"),
                        "approval_status": "pending",
                    }
                )
            if mode in {"clarification", "approval_pending"}:
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
                    "resolved_requirement_id": context.get("resolved_requirement_id"),
                    "write_result": write_result,
                    "mode": mode,
                    "approval_result": approval_result,
                },
                is_read=False,
            )
            yield {"event": "assistant_message", "data": assistant_message}
            yield {
                "event": "result",
                "data": {
                    "graph_id": recorder.graph_id,
                    "reply_text": assistant_message["content"],
                    "write_result": write_result,
                    "mode": mode,
                    "resolved_requirement_id": context.get("resolved_requirement_id"),
                    "approval_result": approval_result,
                },
            }
        except Exception as exc:
            error_text = str(exc)
            if recorder.last_node_key:
                try:
                    recorder.complete_stage(
                        recorder.last_node_key,
                        created_by=user_id,
                        output_summary={"error": error_text},
                        success=False,
                        error=error_text,
                    )
                except Exception:
                    pass
            recorder.fail_graph(
                created_by=user_id,
                error=error_text,
                final_reply=error_text,
            )
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


requirement_agent_chat_service = RequirementAgentChatService(
    chat_storage=ai_chat_service,
)
