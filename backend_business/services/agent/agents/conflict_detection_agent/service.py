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
from backend_business.services.agent.experience import ExperienceOrchestrator
from backend_business.services.agent.runtime.binding_bootstrap import (
    ensure_runtime_bindings,
    extract_tool_names,
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

    def _ensure_graph_runtime_bindings(self) -> None:
        binding_specs = [
            {
                "container_key": "conflict_detection_agent",
                "agent_type": "conflict_detection_agent",
                "runtime_profile": "default",
                "implementation_type": "local",
                "capability_policy_json": {
                    "policy_id": "conflict_detection::runtime",
                    "scope": "conflict_detection_agent",
                    "tool_names": extract_tool_names(self.tools),
                },
                "quota_policy_json": {
                    "policy_id": "conflict_detection::runtime::quota",
                    "max_rounds": self.MAX_TOOL_CALL_ROUNDS,
                    "timeout_seconds": 180,
                    "max_concurrent_runs": 2,
                    "max_parallel_runs_per_scope": 1,
                },
                "memory_policy_json": {
                    "scope": "container",
                    "strict_memory_contract": True,
                },
            }
        ]
        ensure_runtime_bindings(self.execution_graph_service, binding_specs)

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

    def run_inline_tool_loop(
        self,
        *,
        recorder: Any,
        user_id: str,
        user_message: str,
        project_id: str,
        max_tool_call_rounds: int | None = None,
        container_key: str = "conflict_detection",
        node_key_prefix: str = "conflict_agent",
    ) -> dict[str, Any]:
        """Run tool loop inline within an external recorder (no child graph).

        This allows the Session Controller to embed the conflict detection
        agent's tool-loop nodes directly into its own execution graph rather
        than creating a separate child graph.
        """
        gen = self.stream_inline_tool_loop(
            recorder=recorder,
            user_id=user_id,
            user_message=user_message,
            project_id=project_id,
            max_tool_call_rounds=max_tool_call_rounds,
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
        max_tool_call_rounds: int | None = None,
        container_key: str = "conflict_detection",
        node_key_prefix: str = "conflict_agent",
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        """Stream inline tool-loop events within an external recorder."""
        runner = ConflictDetectionToolLoopRunner(
            ai_proxy_client=self.ai_proxy,
            tools=self.tools,
            execution_graph_service=self.execution_graph_service,
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
            session_id="",
        )
        return {
            "status": "success",
            "tool_loop_reply": result.get("tool_loop_reply", ""),
        }

    def stream_conflict_agent_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
        execution_mode: str = "graph",
    ) -> Generator[dict[str, Any], None, None]:
        if str(execution_mode or "").strip().lower() != "graph":
            raise ValueError("execution_mode 仅支持 graph")
        yield from self.stream_graph_executor_reply(
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
        """Drive the execution-graph engine (GraphExecutor internal judge)."""
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
        self._ensure_graph_runtime_bindings()
        yield {"event": "graph", "data": {"graph_id": recorder.graph_id}}

        executor = GraphExecutor(
            experience_orchestrator=ExperienceOrchestrator(),
        )
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

conflict_detection_agent_service = ConflictDetectionAgentService(
    chat_storage=ai_chat_service,
)
