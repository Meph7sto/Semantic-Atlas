"""Requirement classification agent chat orchestration service."""

from __future__ import annotations

import inspect
import json
from collections.abc import Generator
from typing import Any

import requests

from backend_business.config import settings
from backend_business.services.ai_chat_service import AiChatService, ai_chat_service
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.tools import RequirementClassificationTools
from backend_business.services.requirements_manage_service import RequirementsManageService

from .prompt_builder import RequirementClassificationPromptBuilder
from .runtime_graph_recorder import RequirementClassificationGraphRecorder
from .tool_loop_runner import (
    RequirementClassificationToolLoopRunner,
    extract_latest_classification_result,
)


class RequirementClassificationAgentService:
    MAX_TOOL_CALL_ROUNDS = 6
    AGENT_TYPE = "requirement_classification_agent"

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

    @staticmethod
    def _call_compatible(method: Any, /, **kwargs: Any) -> Any:
        signature = inspect.signature(method)
        if any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()):
            return method(**kwargs)
        compatible_kwargs = {
            key: value for key, value in kwargs.items() if key in signature.parameters
        }
        return method(**compatible_kwargs)

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
                self._call_compatible(
                    self.chat_storage.update_session,
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
            self._call_compatible(
                self.chat_storage.update_session,
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
        session = self._call_compatible(
            self.chat_storage.get_or_create_session,
            user_id=user_id,
            project_id=project_id,
            agent_type=self.AGENT_TYPE,
        )
        if prompt_payload_format is not None:
            self._call_compatible(
                self.chat_storage.update_session,
                session_id=session["session_id"],
                prompt_payload_format=prompt_payload_format,
            )
            session["prompt_payload_format"] = prompt_payload_format
        if context_mode is not None:
            self._call_compatible(
                self.chat_storage.update_session,
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
        session = self._call_compatible(
            self.chat_storage.create_session,
            user_id=user_id,
            project_id=project_id,
            title=title,
            prompt_payload_format=prompt_payload_format,
            context_mode=context_mode or "full",
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
        update_kwargs: dict[str, Any] = {
            "session_id": session_id,
            "title": title,
        }
        if prompt_payload_format is not None:
            update_kwargs["prompt_payload_format"] = prompt_payload_format
        if context_mode is not None:
            update_kwargs["context_mode"] = context_mode
        self._call_compatible(self.chat_storage.update_session, **update_kwargs)
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
        sessions = self._call_compatible(
            self.chat_storage.list_sessions,
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

    def _stream_llm_reply(
        self,
        *,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 1200,
    ) -> Generator[dict[str, Any], None, str]:
        response = requests.post(
            f"{settings.INFERENCE_BASE_URL.rstrip('/')}/chat/stream",
            json={
                "prompt": prompt,
                "system_prompt": system_prompt,
                "max_new_tokens": max_new_tokens,
                "use_thinking_mode": True,
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
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        runner = RequirementClassificationToolLoopRunner(
            ai_proxy_client=self.ai_proxy,
            tools=self.tools,
            execution_graph_service=self.execution_graph_service,
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
        )

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
    ) -> Generator[dict[str, Any], None, None]:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")

        session = self.chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
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
        recorder = RequirementClassificationGraphRecorder(
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
            )
            context: dict[str, Any] = {}
            while True:
                try:
                    event = next(tool_loop)
                except StopIteration as stop:
                    loop_result = stop.value or {}
                    tool_loop_reply = loop_result.get("tool_loop_reply") or ""
                    context = loop_result.get("context") or {}
                    break
                yield event

            resolved_requirement_id, classification_result = extract_latest_classification_result(context)
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

            assistant_message = self.chat_storage.create_message(
                session_id=session_id,
                user_id=user_id,
                role="assistant",
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
            yield {
                "event": "error",
                "data": {"error": error_text, "graph_id": recorder.graph_id},
            }


requirement_classification_agent_service = RequirementClassificationAgentService(
    chat_storage=ai_chat_service,
)
