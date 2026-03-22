"""Conflict detection agent chat orchestration service."""

from __future__ import annotations

import json
from collections.abc import Generator
import logging
from typing import Any

import requests

from backend_business.config import settings
from backend_business.services.ai_chat_service import AiChatService, ai_chat_service
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.execution.graph_executor import (
    ExecutionResult,
    GraphExecutor,
)
from backend_business.services.agent.tools import ConflictDetectionTools
from backend_business.services.requirements_manage_service import RequirementsManageService

from .prompt_builder import ConflictDetectionPromptBuilder
from .runtime_graph_recorder import ConflictDetectionGraphRecorder
from .tool_loop_runner import ConflictDetectionToolLoopRunner


logger = logging.getLogger(__name__)


class ConflictDetectionAgentService:
    MAX_TOOL_CALL_ROUNDS = 6
    AGENT_TYPE = "conflict_detection_agent"

    def __init__(
        self,
        *,
        chat_storage: AiChatService | None,
        execution_graph_service: ExecutionGraphService | None = None,
        requirements_service: RequirementsManageService | None = None,
        tools: ConflictDetectionTools | None = None,
        ai_proxy_client: Any = None,
        prompt_builder: ConflictDetectionPromptBuilder | None = None,
    ) -> None:
        self.chat_storage = chat_storage
        self.execution_graph_service = execution_graph_service or ExecutionGraphService(
            settings.POSTGRES_DSN
        )
        self.requirements_service = requirements_service or RequirementsManageService(
            settings.POSTGRES_DSN
        )
        self.ai_proxy = ai_proxy_client or ai_proxy
        self.prompt_builder = prompt_builder or ConflictDetectionPromptBuilder()
        self.tools = tools or ConflictDetectionTools(
            requirements_service=self.requirements_service,
            conflict_check_fn=self.ai_proxy.conflict_check,
        )

    # ---- session helpers (modeled after RequirementAgentChatService) ----

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
            if session.get("prompt_payload_format") != prompt_payload_format:
                self.chat_storage.update_session(
                    session_id=session["session_id"],
                    prompt_payload_format=prompt_payload_format,
                )
                session["prompt_payload_format"] = prompt_payload_format
        if context_mode and context_mode in ("full", "incremental", "scratchpad"):
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
        normalized_context_mode = context_mode if context_mode in ("full", "incremental", "scratchpad") else "full"
        session = self.chat_storage.create_session(
            user_id=user_id,
            project_id=project_id,
            title=title,
            prompt_payload_format=prompt_payload_format,
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
        normalized_context_mode = None
        if context_mode is not None:
            normalized_context_mode = context_mode if context_mode in ("full", "incremental", "scratchpad") else "full"
        self.chat_storage.update_session(
            session_id=session_id,
            title=title,
            prompt_payload_format=prompt_payload_format if prompt_payload_format is not None else ...,
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

    # ---- candidate template loading ----

    def _load_candidate_templates(self, project_id: str) -> list[dict[str, Any]]:
        """Load all topology templates for the given project.

        Returns a lightweight list of dicts (graph_id, name, description)
        suitable for passing to ``GraphExecutor.execute()``.
        """
        try:
            graphs = self.execution_graph_service.list_execution_graphs(
                project_id=project_id,
                graph_types=["execution_topology_template"],
            )
            return [
                {
                    "graph_id": g.get("graph_id", ""),
                    "name": g.get("name", ""),
                    "description": g.get("description", ""),
                }
                for g in graphs
                if g.get("status") != "deleted"
            ]
        except Exception:
            logger.warning(
                "加载候选拓扑模板失败 (project_id=%s)", project_id,
                exc_info=True,
            )
            return []

    # ---- streaming reply ----

    def _stream_llm_reply(
        self,
        *,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 1200,
    ) -> Generator[dict[str, Any], None, str]:
        inference_base = settings.INFERENCE_BASE_URL.rstrip("/")
        response = requests.post(
            f"{inference_base}/chat/stream",
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

    def _run_tool_call_loop(
        self,
        *,
        recorder: ConflictDetectionGraphRecorder,
        user_id: str,
        user_message: str,
        project_id: str,
        session_id: str,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        runner = ConflictDetectionToolLoopRunner(
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

    def stream_conflict_agent_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
        execution_mode: str = "classic",
    ) -> Generator[dict[str, Any], None, None]:
        if execution_mode == "graph":
            yield from self.stream_graph_executor_reply(
                session_id=session_id,
                user_id=user_id,
                project_id=project_id,
                user_message=user_message,
            )
            return

        yield from self._stream_classic_reply(
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            user_message=user_message,
        )

    def stream_graph_executor_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
    ) -> Generator[dict[str, Any], None, None]:
        """Drive the new execution-graph engine (GraphExecutor internal judge).

        SSE events emitted are compatible with the classic mode contract so
        the frontend can consume them with the same ``consumeSSEStream``.
        """
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")

        session = self.chat_storage._ensure_session_access(
            session_id=session_id, user_id=user_id,
        )
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

        candidate_templates = self._load_candidate_templates(project_id)

        # --- GraphExecutor pipeline ------------------------------------------
        graph_target = self._resolve_session_graph_target(
            session=session, project_id=project_id,
        )
        recorder = ConflictDetectionGraphRecorder(
            execution_graph_service=self.execution_graph_service,
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            graph_id=graph_target["graph_id"],
            prev_graph_id=graph_target["prev_graph_id"],
        )
        self.chat_storage.update_session(
            session_id=session_id,
            active_graph_id=recorder.graph_id,
        )
        yield {"event": "graph", "data": {"graph_id": recorder.graph_id}}

        executor = GraphExecutor()
        assistant_content = ""

        try:
            gen = executor.execute(
                candidate_templates=candidate_templates,
                project_id=project_id,
                user_message=user_message,
                tool_executor=self.tools,
                ai_proxy_client=self.ai_proxy,
                graph_service=self.execution_graph_service,
                recorder=recorder,
                actor=user_id,
                runtime_graph_id=recorder.graph_id,
                runtime_container_key="conflict_detection_agent",
                runtime_container_label="Conflict Detection Agent",
                runtime_container_role_type="agent",
            )
            result: ExecutionResult | None = None
            try:
                while True:
                    event = next(gen)
                    yield event
            except StopIteration as stop:
                result = stop.value

            if result is None:
                result = ExecutionResult(
                    status="failed", graph_id=recorder.graph_id,
                    error="GraphExecutor 未返回结果",
                )

            if result.status == "succeeded":
                assistant_content = result.final_output or "执行图模式执行完成。"
            elif result.status == "suspended":
                assistant_content = "执行已挂起，等待用户输入后继续。"
            else:
                assistant_content = f"执行失败: {result.error or '未知错误'}"

            yield {
                "event": "result",
                "data": {
                    "graph_id": result.graph_id,
                    "status": result.status,
                    "reply_text": assistant_content,
                },
            }
        except Exception as exc:
            logger.error("stream_graph_executor_reply 异常: %s", exc, exc_info=True)
            assistant_content = f"执行图模式执行失败: {exc}"
            yield {
                "event": "error",
                "data": {"error": assistant_content, "graph_id": recorder.graph_id},
            }

        assistant_message = self.chat_storage.create_message(
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content=assistant_content,
            metadata={"graph_id": recorder.graph_id, "execution_mode": "graph"},
            is_read=False,
        )
        yield {"event": "assistant_message", "data": assistant_message}

    def _stream_irrelevant_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        user_message: str,
    ) -> Generator[dict[str, Any], None, None]:
        """Lightweight LLM reply when IntentJudge says not relevant."""
        system_prompt = (
            "你是需求冲突检测助手。用户的消息与冲突检测无关，"
            "请礼貌地告知用户你的功能范围，并引导他们提供具体的需求 ID。"
        )
        stream = self._stream_llm_reply(
            prompt=user_message,
            system_prompt=system_prompt,
        )
        assistant_content = ""
        while True:
            try:
                event = next(stream)
            except StopIteration as stop:
                assistant_content = (stop.value or "").strip()
                break
            yield event

        if not assistant_content:
            assistant_content = "您的消息似乎与需求冲突检测无关。请提供具体的需求 ID 进行检测。"

        assistant_message = self.chat_storage.create_message(
            session_id=session_id,
            user_id=user_id,
            role="assistant",
            content=assistant_content,
            metadata={"intent": "irrelevant", "execution_mode": "graph"},
            is_read=False,
        )
        yield {"event": "assistant_message", "data": assistant_message}

    def _stream_classic_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
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
        recorder = ConflictDetectionGraphRecorder(
            execution_graph_service=self.execution_graph_service,
            project_id=project_id,
            user_id=user_id,
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
                "data": {
                    "graph_id": recorder.graph_id,
                    "node_key": recorder.stage_node_key("user_input"),
                    "status": "succeeded",
                },
            }

            # Stage 2: Tool loop
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

            final_system_prompt = (
                "你是需求冲突检测助手。根据工具的执行结果，用简洁的中文回复用户，"
                "说明是否存在冲突以及具体原因。不要编造内容。"
            )
            final_prompt = (
                f"用户原始请求：{user_message}\n\n"
                f"工具执行结论：\n{tool_loop_reply}\n\n"
                "请给出最终的中文总结回复。"
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
                assistant_content = tool_loop_reply or "已完成冲突检测。"

            recorder.complete_stage(
                recorder.stage_node_key("conductor_reply"),
                created_by=user_id,
                output_summary={
                    "reply": assistant_content,
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
                "intent": "conflict_detection",
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
                },
                is_read=False,
            )
            yield {"event": "assistant_message", "data": assistant_message}
            yield {
                "event": "result",
                "data": {
                    "graph_id": recorder.graph_id,
                    "reply_text": assistant_message["content"],
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


conflict_detection_agent_service = ConflictDetectionAgentService(
    chat_storage=ai_chat_service,
)
