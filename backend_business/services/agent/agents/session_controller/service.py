"""Session controller agent chat orchestration service."""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from typing import Any

import requests

from backend_business.config import settings
from backend_business.services.ai_chat_service import AiChatService, ai_chat_service
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.runtime.scratchpad import Scratchpad
from backend_business.services.requirements_manage_service import RequirementsManageService

from .prompt_builder import SessionControllerPromptBuilder
from .runtime_graph_recorder import SessionControllerGraphRecorder
from .tool_loop_runner import SessionControllerToolLoopRunner
from .tools import SessionControllerTools


logger = logging.getLogger(__name__)


class SessionControllerService:
    MAX_TOOL_CALL_ROUNDS = 8
    AGENT_TYPE = "session_controller"

    def __init__(
        self,
        *,
        chat_storage: AiChatService | None,
        execution_graph_service: ExecutionGraphService | None = None,
        requirements_service: RequirementsManageService | None = None,
        tools: SessionControllerTools | None = None,
        ai_proxy_client: Any = None,
        prompt_builder: SessionControllerPromptBuilder | None = None,
    ) -> None:
        self.chat_storage = chat_storage
        self.execution_graph_service = execution_graph_service or ExecutionGraphService(
            settings.POSTGRES_DSN
        )
        self.requirements_service = requirements_service or RequirementsManageService(
            settings.POSTGRES_DSN
        )
        self.ai_proxy = ai_proxy_client or ai_proxy
        self.prompt_builder = prompt_builder or SessionControllerPromptBuilder()
        self.tools = tools

    @staticmethod
    def _compact_write_result(write_result: dict[str, Any] | None) -> dict[str, Any] | None:
        if not isinstance(write_result, dict):
            return None
        compact = {
            "requirement_id": write_result.get("requirement_id"),
            "version": write_result.get("version"),
            "priority": write_result.get("priority"),
            "title": write_result.get("title"),
            "applied_updates": write_result.get("applied_updates"),
        }
        return {key: value for key, value in compact.items() if value is not None}

    def _inherit_session_scratchpad(
        self,
        *,
        graph_id: str,
        prev_graph_id: str | None,
        updated_by: str,
    ) -> None:
        if not prev_graph_id:
            return
        current_graph = self.execution_graph_service.get_execution_graph(graph_id)
        current_meta = (current_graph.get("meta_json") or {}) if current_graph else {}
        if current_meta.get("scratchpad_entries"):
            return

        previous_graph = self.execution_graph_service.get_execution_graph(prev_graph_id)
        previous_meta = (previous_graph.get("meta_json") or {}) if previous_graph else {}
        inherited_entries = previous_meta.get("scratchpad_entries") or []
        inherited_requirement_id = previous_meta.get("resolved_requirement_id")
        if not inherited_entries and not inherited_requirement_id:
            return

        meta_patch: dict[str, Any] = {}
        if inherited_entries:
            meta_patch["scratchpad_entries"] = inherited_entries
        if inherited_requirement_id:
            meta_patch["resolved_requirement_id"] = inherited_requirement_id
        self.execution_graph_service.patch_graph_meta(
            graph_id,
            meta_patch,
            updated_by=updated_by,
        )

    def _generate_turn_summary(
        self,
        *,
        user_message: str,
        tool_loop_reply: str,
        assistant_reply: str,
        context: dict[str, Any],
    ) -> str:
        write_result = self._compact_write_result(context.get("last_write_result"))
        payload = {
            "user_message": user_message,
            "tool_loop_reply": tool_loop_reply,
            "assistant_reply": assistant_reply,
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            "dispatched_agents": context.get("dispatched_agents") or [],
            "write_result": write_result,
        }
        fallback_parts = []
        resolved_requirement_id = payload.get("resolved_requirement_id")
        if resolved_requirement_id:
            fallback_parts.append(f"当前焦点需求是 {resolved_requirement_id}。")
        if write_result and write_result.get("applied_updates"):
            fallback_parts.append(
                f"本轮已执行更新：{json.dumps(write_result['applied_updates'], ensure_ascii=False)}。"
            )
        elif payload["dispatched_agents"]:
            fallback_parts.append(
                f"本轮调用了 {', '.join(payload['dispatched_agents'])}。"
            )
        if assistant_reply.strip():
            fallback_parts.append(f"结果：{assistant_reply.strip()}")
        elif tool_loop_reply.strip():
            fallback_parts.append(f"结果：{tool_loop_reply.strip()}")
        fallback_summary = " ".join(fallback_parts) or f"用户本轮请求：{user_message}"

        try:
            response = self.ai_proxy.chat_completion(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            "你负责维护需求工程会话的跨轮记事本。"
                            "请根据给定信息写一段 1 到 3 句的中文摘要，记录本轮做了什么、"
                            "当前聚焦对象是什么、结果或待澄清点是什么。"
                            "如果目标需求可确定，优先明确写出 requirement_id。"
                            "只输出摘要正文，不要 JSON，不要客套话。"
                        ),
                    },
                    {
                        "role": "user",
                        "content": json.dumps(payload, ensure_ascii=False),
                    },
                ],
                temperature=0.2,
                max_tokens=220,
            )
            summary = str(response.get("content") or "").strip()
            return summary or fallback_summary
        except Exception:
            logger.warning("生成会话记事本摘要失败，改用回退摘要", exc_info=True)
            return fallback_summary

    def _persist_turn_summary_to_scratchpad(
        self,
        *,
        graph_id: str,
        turn_index: int,
        user_id: str,
        user_message: str,
        tool_loop_reply: str,
        assistant_reply: str,
        context: dict[str, Any],
    ) -> None:
        scratchpad = context.get("_scratchpad")
        if not isinstance(scratchpad, Scratchpad):
            graph = self.execution_graph_service.get_execution_graph(graph_id)
            meta = (graph.get("meta_json") or {}) if graph else {}
            scratchpad = Scratchpad.from_snapshot(meta.get("scratchpad_entries") or [])

        summary = self._generate_turn_summary(
            user_message=user_message,
            tool_loop_reply=tool_loop_reply,
            assistant_reply=assistant_reply,
            context=context,
        )
        scratchpad.write(
            "note",
            {
                "turn": turn_index,
                "summary": summary,
                "resolved_requirement_id": context.get("resolved_requirement_id"),
                "dispatched_agents": context.get("dispatched_agents") or [],
                "write_result": self._compact_write_result(context.get("last_write_result")),
            },
            source_subgraph=f"session_turn_{turn_index}",
            readonly=True,
        )
        context["_scratchpad"] = scratchpad
        context["_scratchpad_prompt_text"] = scratchpad.format_for_prompt()
        self.execution_graph_service.patch_graph_meta(
            graph_id,
            {
                "scratchpad_entries": scratchpad.snapshot(),
                "resolved_requirement_id": context.get("resolved_requirement_id"),
            },
            updated_by=user_id,
        )

    # ---- session helpers ----

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
        session = self.chat_storage.get_or_create_session(
            user_id=user_id, project_id=project_id, agent_type=self.AGENT_TYPE
        )
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
        session = self.chat_storage.create_session(
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
        self.chat_storage.update_session(
            session_id=session_id,
            title=title,
            prompt_payload_format=prompt_payload_format if prompt_payload_format is not None else ...,
            context_mode=context_mode if context_mode is not None else ...,
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

    # ---- streaming reply ----

    def _stream_llm_reply(
        self,
        *,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 1200,
        use_thinking_mode: bool = True,
    ) -> Generator[dict[str, Any], None, str]:
        inference_base = settings.INFERENCE_BASE_URL.rstrip("/")
        response = requests.post(
            f"{inference_base}/chat/stream",
            json={
                "prompt": prompt,
                "system_prompt": system_prompt,
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

    def _run_tool_call_loop(
        self,
        *,
        recorder: SessionControllerGraphRecorder,
        user_id: str,
        user_message: str,
        project_id: str,
        session_id: str,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        runner = SessionControllerToolLoopRunner(
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
            session_id=session_id,
        )

    def stream_session_controller_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
        use_thinking_mode: bool = True,
    ) -> Generator[dict[str, Any], None, None]:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")

        session = self.chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
        user_record = self.chat_storage.create_message(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=user_message,
            metadata={},
            is_read=True,
        )
        self.chat_storage.update_session(session_id=session_id)
        yield {"event": "user_message", "data": user_record}

        graph_target = self._resolve_session_graph_target(session=session, project_id=project_id)
        recorder = SessionControllerGraphRecorder(
            execution_graph_service=self.execution_graph_service,
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            graph_id=graph_target["graph_id"],
            prev_graph_id=graph_target["prev_graph_id"],
        )
        self._inherit_session_scratchpad(
            graph_id=recorder.graph_id,
            prev_graph_id=graph_target["prev_graph_id"],
            updated_by=user_id,
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
                "active_turn_index": recorder.turn_index,
            },
            status="running",
            updated_by=user_id,
        )
        yield {"event": "graph", "data": {"graph_id": recorder.graph_id}}

        assistant_content = ""
        tool_loop_reply = ""
        context: dict[str, Any] = {}

        try:
            # Stage 1: Record user input
            recorder.start_stage(
                node_key=recorder.stage_node_key("user_input"),
                label=recorder.stage_label("User Input"),
                node_type="start",
                role_type="human",
                container_key="human_input",
                created_by=user_id,
                input_summary={"message": user_message},
                edge_type_from_previous="call" if recorder.turn_index > 1 else None,
            )
            recorder.complete_stage(
                recorder.stage_node_key("user_input"),
                created_by=user_id,
                output_summary={"accepted": True},
            )
            yield {
                "event": "stage",
                "data": recorder.build_stage_event_data(
                    recorder.stage_node_key("user_input"),
                    status="succeeded",
                ),
            }

            # Stage 2: Tool loop (intent + dispatch)
            tool_loop = self._run_tool_call_loop(
                recorder=recorder,
                user_id=user_id,
                user_message=user_message,
                project_id=project_id,
                session_id=session_id,
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

            dispatched_agents = context.get("dispatched_agents") or []

            # Stage 3: Conductor reply (streaming final answer)
            recorder.start_stage(
                node_key=recorder.stage_node_key("conductor_reply"),
                label=recorder.stage_label("Conductor Reply"),
                node_type="end",
                role_type="agent",
                container_key="conductor",
                created_by=user_id,
                input_summary={
                    "tool_loop_reply": tool_loop_reply,
                    "dispatched_agents": dispatched_agents,
                },
                edge_type_from_previous="return",
            )
            yield {
                "event": "stage",
                "data": recorder.build_stage_event_data(
                    recorder.stage_node_key("conductor_reply"),
                    status="running",
                ),
            }

            final_system_prompt = (
                "你是面向需求工程用户的中文助手。"
                "根据工具的执行结论，用自然、简洁的中文回复用户。"
                "直接给出结论，不要重复 JSON 内容，不要输出 JSON。"
                "如需澄清，只问最小必要问题。"
            )
            final_prompt = (
                f"用户原始请求：{user_message}\n\n"
                f"工具执行结论：\n{tool_loop_reply}\n\n"
                "请给出最终的中文总结回复。"
            )

            stream = self._stream_llm_reply(
                prompt=final_prompt,
                system_prompt=final_system_prompt,
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
                assistant_content = tool_loop_reply or "已完成处理。"

            self._persist_turn_summary_to_scratchpad(
                graph_id=recorder.graph_id,
                turn_index=recorder.turn_index,
                user_id=user_id,
                user_message=user_message,
                tool_loop_reply=tool_loop_reply,
                assistant_reply=assistant_content,
                context=context,
            )
            recorder.complete_stage(
                recorder.stage_node_key("conductor_reply"),
                created_by=user_id,
                output_summary={
                    "reply": assistant_content,
                    "dispatched_agents": dispatched_agents,
                },
            )
            yield {
                "event": "stage",
                "data": recorder.build_stage_event_data(
                    recorder.stage_node_key("conductor_reply"),
                    status="succeeded",
                ),
            }

            meta_patch = {
                "intent": "session_control",
                "dispatched_agents": dispatched_agents,
                "turn_count": recorder.turn_index,
                "active_turn_index": recorder.turn_index,
            }
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
                    "dispatched_agents": dispatched_agents,
                },
                is_read=False,
            )
            yield {"event": "assistant_message", "data": assistant_message}
            yield {
                "event": "result",
                "data": {
                    "graph_id": recorder.graph_id,
                    "reply_text": assistant_message["content"],
                    "dispatched_agents": dispatched_agents,
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


def _make_session_controller_service() -> SessionControllerService:
    """Deferred factory to avoid circular imports at module load time."""
    from backend_business.services.agent.agents.requirement_agent import (
        requirement_agent_chat_service,
    )
    from backend_business.services.agent.agents.conflict_detection_agent import (
        conflict_detection_agent_service,
    )

    tools = SessionControllerTools(
        requirements_service=RequirementsManageService(settings.POSTGRES_DSN),
        requirement_agent_service=requirement_agent_chat_service,
        conflict_agent_service=conflict_detection_agent_service,
    )
    return SessionControllerService(
        chat_storage=ai_chat_service,
        tools=tools,
    )


session_controller_service: SessionControllerService = _make_session_controller_service()
