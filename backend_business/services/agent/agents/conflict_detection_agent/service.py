"""Conflict detection agent chat orchestration service."""

from __future__ import annotations

import json
import logging
from collections.abc import Generator
from typing import Any

import requests
from backend_business.config import settings
from backend_business.services.agent.execution.graph_executor import (
    ExecutionResult,
    GraphExecutor,
)
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.experience import ExperienceOrchestrator
from backend_business.services.agent.runtime.agent_registry import BUILTIN_AGENT_REGISTRY
from backend_business.services.agent.runtime.agent_execution_service import (
    AgentExecutionService,
)
from backend_business.services.agent.runtime.binding_bootstrap import (
    ensure_runtime_bindings,
)
from backend_business.services.agent.runtime.session_graph_store import AgentSessionGraphStore
from backend_business.services.agent.tools import ConflictDetectionTools
from backend_business.services.ai_chat_service import AiChatService, ai_chat_service
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.requirements_manage_service import RequirementsManageService

from .prompt_builder import ConflictDetectionPromptBuilder
from .definition import STANDALONE_CONFLICT_DETECTION_AGENT_DEFINITION
from .runtime_graph_recorder import ConflictDetectionGraphRecorder
from .tool_loop_runner import ConflictDetectionToolLoopRunner

logger = logging.getLogger(__name__)


class ConflictDetectionAgentService:
    MAX_TOOL_CALL_ROUNDS = STANDALONE_CONFLICT_DETECTION_AGENT_DEFINITION.max_tool_call_rounds
    AGENT_TYPE = STANDALONE_CONFLICT_DETECTION_AGENT_DEFINITION.agent_type

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
        self._session_graph_store = AgentSessionGraphStore(
            chat_storage=chat_storage,
            execution_graph_service=self.execution_graph_service,
            agent_type=self.AGENT_TYPE,
            create_or_get_prompt_update_policy="truthy",
            create_or_get_context_update_policy="allowed",
        )
        self._execution_service = AgentExecutionService(
            definition=STANDALONE_CONFLICT_DETECTION_AGENT_DEFINITION,
            chat_storage=chat_storage,
            session_graph_store=self._session_graph_store,
        )

    def _ensure_graph_runtime_bindings(self) -> None:
        binding_specs = BUILTIN_AGENT_REGISTRY.build_runtime_binding_specs(
            definitions=[STANDALONE_CONFLICT_DETECTION_AGENT_DEFINITION],
            tool_executor_resolver=lambda _definition: self.tools,
        )
        ensure_runtime_bindings(self.execution_graph_service, binding_specs)

    # ---- session helpers (modeled after RequirementAgentChatService) ----

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
                "加载候选拓扑模板失败 (project_id=%s)",
                project_id,
                exc_info=True,
            )
            return []

    # ---- streaming reply ----

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
        inference_base = settings.INFERENCE_BASE_URL.rstrip("/")
        response = requests.post(
            f"{inference_base}/chat/stream",
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
        model: str = "deepseek-v4-pro",
        use_thinking_mode: bool = True,
    ) -> Generator[dict[str, Any], None, None]:
        if str(execution_mode or "").strip().lower() != "graph":
            raise ValueError("execution_mode 仅支持 graph")
        yield from self.stream_graph_executor_reply(
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            user_message=user_message,
            model=model,
            use_thinking_mode=use_thinking_mode,
        )

    def stream_graph_executor_reply(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
        model: str = "deepseek-v4-pro",
        use_thinking_mode: bool = True,
    ) -> Generator[dict[str, Any], None, None]:
        """Drive the execution-graph engine (GraphExecutor internal judge)."""
        turn = self._execution_service.begin_turn(
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            user_message=user_message,
            user_metadata={
                "model": model,
                "use_thinking_mode": use_thinking_mode,
            },
        )
        yield {"event": "user_message", "data": turn.user_record}

        candidate_templates = self._load_candidate_templates(project_id)

        # --- GraphExecutor pipeline ------------------------------------------
        recorder = self._execution_service.create_recorder(
            turn=turn,
            recorder_factory=ConflictDetectionGraphRecorder,
            execution_graph_service=self.execution_graph_service,
        )
        self._ensure_graph_runtime_bindings()
        yield {"event": "graph", "data": {"graph_id": recorder.graph_id}}

        executor = GraphExecutor(
            experience_orchestrator=ExperienceOrchestrator(),
        )
        assistant_content = ""
        assistant_message: dict[str, Any] | None = None

        try:
            gen = executor.execute(
                candidate_templates=candidate_templates,
                project_id=project_id,
                user_message=user_message,
                tool_executor=self.tools,
                ai_proxy_client=self._graph_ai_proxy_client(
                    model=model,
                    use_thinking_mode=use_thinking_mode,
                ),
                graph_service=self.execution_graph_service,
                recorder=recorder,
                actor=user_id,
                runtime_graph_id=recorder.graph_id,
                runtime_container_key="conflict_detection_agent",
                runtime_container_label="Conflict Detection Agent",
                runtime_container_role_type="agent",
            )
            result: ExecutionResult | None = yield from self._execution_service.stream_generator(
                gen
            )

            if result is None:
                result = ExecutionResult(
                    status="failed",
                    graph_id=recorder.graph_id,
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
            assistant_message = self._execution_service.persist_assistant(
                turn=turn,
                content=assistant_content,
                metadata={"graph_id": recorder.graph_id, "execution_mode": "graph"},
            )
        except Exception as exc:
            logger.error("stream_graph_executor_reply 异常: %s", exc, exc_info=True)
            assistant_content = f"执行图模式执行失败: {exc}"
            assistant_message = self._execution_service.persist_error(
                turn=turn,
                graph_id=recorder.graph_id,
                error=assistant_content,
                metadata={"execution_mode": "graph"},
            )
            yield {
                "event": "error",
                "data": {"error": assistant_content, "graph_id": recorder.graph_id},
            }

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
