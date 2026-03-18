"""Requirement agent chat orchestration service."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Generator
from typing import Any

import requests

from backend_business.config import settings
from backend_business.services.ai_chat_service import AiChatService, ai_chat_service
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.tools import RequirementAgentTools
from backend_business.services.requirements_manage_service import RequirementsManageService

from .actor_runtime import RequirementAgentActorRuntime
from .constants import DEFAULT_PROMPT_PAYLOAD_FORMAT
from .payload_codec import normalize_prompt_payload_format
from .prompt_builder import RequirementAgentPromptBuilder
from .runtime_graph_recorder import _RuntimeGraphRecorder
from .tool_loop_runner import RequirementAgentToolLoopRunner
from .utils import inference_url


class RequirementAgentChatService:
    MAX_TOOL_CALL_ROUNDS = 6
    AGENT_TYPE = "requirement_agent"

    def __init__(
        self,
        *,
        chat_storage: AiChatService | None,
        execution_graph_service: ExecutionGraphService | None = None,
        requirements_service: RequirementsManageService | None = None,
        tools: RequirementAgentTools | None = None,
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
        self.tools = tools or RequirementAgentTools(
            requirements_service=self.requirements_service,
            actor_query_fn=self._actor_query,
            actor_write_fn=self._actor_write,
        )

    def _hydrate_session_graph(self, session: dict[str, Any]) -> dict[str, Any]:
        hydrated = dict(session or {})
        active_graph_id = hydrated.get("active_graph_id")
        if active_graph_id:
            active_graph = self.execution_graph_service.get_execution_graph(active_graph_id)
            if active_graph:
                return hydrated

        latest_graph = self.execution_graph_service.get_latest_runtime_graph_by_session(
            hydrated.get("session_id") or "",
            project_id=hydrated.get("project_id"),
        )
        if latest_graph:
            hydrated["active_graph_id"] = latest_graph["graph_id"]
            if self.chat_storage:
                self.chat_storage.update_session(
                    session_id=hydrated["session_id"],
                    active_graph_id=latest_graph["graph_id"],
                )
        return hydrated

    def _resolve_session_graph_target(
        self,
        *,
        session: dict[str, Any],
        project_id: str | None,
    ) -> dict[str, str | None]:
        graph_id = session.get("active_graph_id")
        if graph_id:
            graph = self.execution_graph_service.get_execution_graph(graph_id)
            if graph:
                if graph.get("status") == "suspended":
                    return {"graph_id": graph_id, "prev_graph_id": None}
                return {"graph_id": None, "prev_graph_id": graph_id}

        latest_graph = self.execution_graph_service.get_latest_runtime_graph_by_session(
            session.get("session_id") or "",
            project_id=project_id,
        )
        if not latest_graph:
            return {"graph_id": None, "prev_graph_id": None}

        if self.chat_storage:
            self.chat_storage.update_session(
                session_id=session["session_id"],
                active_graph_id=latest_graph["graph_id"],
            )
        if latest_graph.get("status") == "suspended":
            return {"graph_id": latest_graph["graph_id"], "prev_graph_id": None}
        return {"graph_id": None, "prev_graph_id": latest_graph["graph_id"]}

    def create_or_get_session(
        self,
        user_id: str,
        project_id: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")
        session = self.chat_storage.get_or_create_session(user_id=user_id, project_id=project_id, agent_type=self.AGENT_TYPE)
        if prompt_payload_format:
            normalized_format = normalize_prompt_payload_format(prompt_payload_format)
            if session.get("prompt_payload_format") != normalized_format:
                self.chat_storage.update_session(
                    session_id=session["session_id"],
                    prompt_payload_format=normalized_format,
                )
                session["prompt_payload_format"] = normalized_format
        if context_mode and context_mode in ("full", "incremental"):
            if session.get("context_mode") != context_mode:
                self.chat_storage.update_session(
                    session_id=session["session_id"],
                    context_mode=context_mode,
                )
                session["context_mode"] = context_mode
        return self._hydrate_session_graph(session)

    def create_session(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        title: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")
        normalized_format = normalize_prompt_payload_format(prompt_payload_format)
        normalized_context_mode = context_mode if context_mode in ("full", "incremental") else "full"
        session = self.chat_storage.create_session(
            user_id=user_id,
            project_id=project_id,
            title=title,
            prompt_payload_format=normalized_format,
            context_mode=normalized_context_mode,
            agent_type=self.AGENT_TYPE,
        )
        return self._hydrate_session_graph(session)

    def update_session(
        self,
        *,
        session_id: str,
        user_id: str,
        title: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")
        self.chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
        normalized_format = None
        if prompt_payload_format is not None:
            normalized_format = normalize_prompt_payload_format(prompt_payload_format)
        normalized_context_mode = None
        if context_mode is not None:
            normalized_context_mode = context_mode if context_mode in ("full", "incremental") else "full"
        self.chat_storage.update_session(
            session_id=session_id,
            title=title,
            prompt_payload_format=normalized_format if prompt_payload_format is not None else ...,
            context_mode=normalized_context_mode if context_mode is not None else ...,
        )
        current = self.chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
        return self._hydrate_session_graph(current)

    def list_sessions(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")
        sessions = self.chat_storage.list_sessions(
            user_id=user_id,
            project_id=project_id,
            limit=limit,
            agent_type=self.AGENT_TYPE,
        )
        return [self._hydrate_session_graph(session) for session in sessions]

    @staticmethod
    def _sort_session_graphs_as_chain(graphs: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if len(graphs) <= 1:
            return list(graphs)

        by_id = {graph["graph_id"]: graph for graph in graphs if graph.get("graph_id")}
        children_by_prev: dict[str | None, list[dict[str, Any]]] = {}
        for graph in graphs:
            meta = graph.get("meta_json") or {}
            prev_graph_id = meta.get("prev_graph_id")
            if prev_graph_id not in by_id:
                prev_graph_id = None
            children_by_prev.setdefault(prev_graph_id, []).append(graph)

        def _graph_sort_key(item: dict[str, Any]) -> tuple[str, str]:
            return (
                str(item.get("created_at") or ""),
                str(item.get("graph_id") or ""),
            )

        for siblings in children_by_prev.values():
            siblings.sort(key=_graph_sort_key)

        ordered: list[dict[str, Any]] = []
        visited: set[str] = set()

        def _walk(graph: dict[str, Any]) -> None:
            graph_id = graph.get("graph_id")
            if not graph_id or graph_id in visited:
                return
            visited.add(graph_id)
            ordered.append(graph)
            for child in children_by_prev.get(graph_id, []):
                _walk(child)

        for root in children_by_prev.get(None, []):
            _walk(root)

        for graph in sorted(graphs, key=_graph_sort_key):
            _walk(graph)

        return ordered

    def list_session_graph_chain(
        self,
        *,
        session_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")

        session = self.chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
        hydrated_session = self._hydrate_session_graph(session)
        graphs = self.execution_graph_service.list_runtime_graphs_by_session(
            session_id=session_id,
            project_id=hydrated_session.get("project_id"),
        )
        ordered_graphs = self._sort_session_graphs_as_chain(graphs)
        chain = [
            self.execution_graph_service.get_graph_detail(graph["graph_id"])
            for graph in ordered_graphs
        ]
        return {
            "session_id": session_id,
            "active_graph_id": hydrated_session.get("active_graph_id"),
            "graphs": chain,
        }

    def delete_session(self, *, session_id: str, user_id: str) -> bool:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")

        session = self.chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
        session_graphs = self.execution_graph_service.list_runtime_graphs_by_session(
            session_id=session_id,
            project_id=session.get("project_id"),
        )

        deleted = self.chat_storage.delete_session(session_id)
        if not deleted:
            return False

        for graph in session_graphs:
            try:
                self.execution_graph_service.delete_execution_graph(
                    graph["graph_id"],
                    updated_by=user_id,
                )
            except Exception:
                continue
        return True

    def list_messages(self, *, session_id: str, user_id: str, limit: int = 100) -> list[dict[str, Any]]:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")
        return self.chat_storage.list_messages(session_id=session_id, user_id=user_id, limit=limit)

    def get_graph_detail(self, graph_id: str) -> dict[str, Any]:
        return self.execution_graph_service.get_graph_detail(graph_id)

    def get_graph(self, graph_id: str) -> dict[str, Any] | None:
        return self.execution_graph_service.get_execution_graph(graph_id)

    def _get_actor_manager(self):
        return self.actor_runtime.get_actor_manager()

    def _ensure_actor_loop(self) -> asyncio.AbstractEventLoop:
        return self.actor_runtime.ensure_actor_loop()

    def _run_actor_coro(self, coro):
        return self.actor_runtime.run_actor_coro(coro)

    def _stream_llm_reply(
        self,
        *,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 1200,
    ) -> Generator[dict[str, Any], None, str]:
        response = requests.post(
            f"{inference_url()}/chat/stream",
            json={
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_new_tokens": max_new_tokens,
                "use_thinking_mode": False,
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

    def _actor_write(self, actor_manager, requirement_id: str, command: dict[str, Any]) -> dict[str, Any]:
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
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        runner = RequirementAgentToolLoopRunner(
            ai_proxy_client=self.ai_proxy,
            tools=self.tools,
            execution_graph_service=self.execution_graph_service,
            actor_manager_getter=self._get_actor_manager,
            prompt_builder=self.prompt_builder,
            max_tool_call_rounds=self.MAX_TOOL_CALL_ROUNDS,
        )
        return runner.run(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            project_id=project_id,
            requirement_id=requirement_id,
            session_id=session_id,
            prompt_payload_format=prompt_payload_format,
            context_mode=context_mode,
        )

    def stream_requirement_agent_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
        requirement_id: str | None = None,
    ) -> Generator[dict[str, Any], None, None]:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")

        session = self.chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
        prompt_payload_format = normalize_prompt_payload_format(
            session.get("prompt_payload_format"),
            default=DEFAULT_PROMPT_PAYLOAD_FORMAT,
        )
        context_mode = session.get("context_mode") or "full"
        user_record = self.chat_storage.create_message(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=user_message,
            metadata={"requirement_id": requirement_id},
            is_read=True,
        )
        self.chat_storage.update_session(session_id=session_id)
        yield {"event": "user_message", "data": user_record}

        graph_target = self._resolve_session_graph_target(session=session, project_id=project_id)
        recorder = _RuntimeGraphRecorder(
            execution_graph_service=self.execution_graph_service,
            project_id=project_id,
            user_id=user_id,
            requirement_id=requirement_id,
            session_id=session_id,
            user_message=user_message,
            graph_id=graph_target["graph_id"],
            prev_graph_id=graph_target["prev_graph_id"],
        )
        self.chat_storage.update_session(
            session_id=session_id,
            active_graph_id=recorder.graph_id,
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
            )
            while True:
                try:
                    event = next(tool_loop)
                except StopIteration as stop:
                    loop_result = stop.value or {}
                    tool_loop_reply = loop_result.get("tool_loop_reply") or ""
                    context = loop_result.get("context") or {}
                    break
                yield event

            mode = self._normalize_mode(context)
            write_result = context.get("last_write_result")

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

            assistant_message = self.chat_storage.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=assistant_content,
                metadata={
                    "graph_id": recorder.graph_id,
                    "requested_requirement_id": requirement_id,
                    "resolved_requirement_id": context.get("resolved_requirement_id"),
                    "write_result": write_result,
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
                    "write_result": write_result,
                    "mode": mode,
                    "resolved_requirement_id": context.get("resolved_requirement_id"),
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
            error_message = self.chat_storage.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
                content=error_text,
                metadata={"error": True, "graph_id": recorder.graph_id},
                is_read=False,
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
