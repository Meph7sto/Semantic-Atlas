"""Requirement agent chat orchestration service."""

from __future__ import annotations

import asyncio
import json
import os
import re
import socket
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Generator

import requests

from backend_business.config import settings
from backend_business.services.ai_chat_service import AiChatService, ai_chat_service
from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.tools import RequirementAgentTools
from backend_business.services.requirements_manage_service import RequirementsManageService


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _inference_url() -> str:
    return settings.INFERENCE_BASE_URL.rstrip("/")


def _safe_json(value: Any) -> Any:
    if isinstance(value, (dict, list, str, int, float, bool)) or value is None:
        return value
    if isinstance(value, set):
        return sorted(value)
    return str(value)


def _actor_instance_id() -> str:
    configured = settings.ACTOR_INSTANCE_ID
    if configured:
        return configured
    host = os.environ.get("HOSTNAME") or socket.gethostname() or "unknown-host"
    return f"{host}:{os.getpid()}"


def _coerce_tool_arguments(raw_arguments: Any) -> dict[str, Any]:
    if raw_arguments is None:
        return {}
    if isinstance(raw_arguments, dict):
        return dict(raw_arguments)
    if isinstance(raw_arguments, str):
        text = raw_arguments.strip()
        if not text:
            return {}
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise ValueError("tool arguments 必须是对象")
        return parsed
    raise ValueError("tool arguments 格式无效")


@dataclass
class _StageNode:
    node_id: str
    node_key: str
    label: str
    node_type: str
    role_type: str
    container_id: str


class _RuntimeGraphRecorder:
    _CONTAINERS = (
        ("human_input", "Human Input", "human"),
        ("conductor", "Conductor", "agent"),
        ("requirements_agent", "Requirements Agent", "agent"),
        ("requirements_tools", "Requirement Tools", "system"),
    )

    def __init__(
        self,
        *,
        execution_graph_service: ExecutionGraphService,
        project_id: str,
        user_id: str,
        requirement_id: str | None,
        session_id: str,
        user_message: str,
        graph_id: str | None = None,
    ) -> None:
        self._service = execution_graph_service
        self._containers: dict[str, str] = {}
        self._nodes: dict[str, _StageNode] = {}
        self._seed_context_entries: list[dict[str, Any]] = []
        self._historical_node_context: list[dict[str, Any]] = []
        self._last_node_id: str | None = None
        self._last_node_key: str | None = None
        self._node_order = 0
        self._edge_order = 0
        self._graph = self._load_or_create_graph(
            graph_id=graph_id,
            project_id=project_id,
            user_id=user_id,
            requirement_id=requirement_id,
            session_id=session_id,
            user_message=user_message,
        )
        self.graph_id = self._graph["graph_id"]
        self.turn_index = self._resolve_turn_index()
        self._task_context = {
            "session_id": session_id,
            "project_id": project_id,
            "user_id": user_id,
            "requirement_id": requirement_id,
            "user_message": user_message,
            "turn_index": self.turn_index,
            "historical_node_count": len(self._historical_node_context),
        }
        self._context_entries: list[dict[str, Any]] = list(self._seed_context_entries)
        self._ensure_containers(user_id)

    def _load_or_create_graph(
        self,
        *,
        graph_id: str | None,
        project_id: str,
        user_id: str,
        requirement_id: str | None,
        session_id: str,
        user_message: str,
    ) -> dict[str, Any]:
        if graph_id:
            detail = self._service.get_graph_detail(graph_id)
            graph = detail.get("graph")
            if not graph:
                raise ValueError("会话绑定的执行图不存在或已删除")
            self._hydrate_existing_graph(detail)
            return graph

        return self._service.create_runtime_graph(
            project_id=project_id,
            name=f"Requirement Agent Run {datetime.now(timezone.utc).strftime('%H:%M:%S')}",
            description="需求管理 Agent 运行轨迹",
            created_by=user_id,
            meta_json={
                "session_id": session_id,
                "user_id": user_id,
                "project_id": project_id,
                "requirement_id": requirement_id,
                "resolved_requirement_id": requirement_id,
                "intent": "pending",
                "current_node_key": None,
                "final_reply": None,
                "user_message": user_message,
                "created_at": _utc_now_iso(),
                "turn_count": 0,
            },
            status="running",
        )

    def _hydrate_existing_graph(self, detail: dict[str, Any]) -> None:
        containers = sorted(
            detail.get("containers") or [],
            key=lambda item: (item.get("order_index") or 0, item.get("created_at") or ""),
        )
        for container in containers:
            container_key = container.get("container_key")
            container_id = container.get("container_id")
            if container_key and container_id:
                self._containers[container_key] = container_id

        nodes = sorted(
            detail.get("nodes") or [],
            key=lambda item: (item.get("order_index") or 0, item.get("created_at") or ""),
        )
        self._historical_node_context = self._summarize_existing_nodes(nodes)
        self._seed_context_entries = self._build_existing_context_entries(nodes)
        if nodes:
            last_node = nodes[-1]
            self._last_node_id = last_node.get("node_id")
            self._last_node_key = last_node.get("node_key")
            self._node_order = max((item.get("order_index") or 0) for item in nodes) + 1

        edges = detail.get("edges") or []
        if edges:
            self._edge_order = max((item.get("order_index") or 0) for item in edges) + 1

    def _resolve_turn_index(self) -> int:
        meta = self._graph.get("meta_json") or {}
        raw_turn_count = meta.get("turn_count")
        try:
            normalized_turn_count = int(raw_turn_count)
        except (TypeError, ValueError):
            normalized_turn_count = 0
        if normalized_turn_count > 0:
            return normalized_turn_count + 1
        return self._infer_turn_index_from_node_order()

    def _infer_turn_index_from_node_order(self) -> int:
        highest_turn = 0
        pattern = re.compile(r"^turn_(\d+)__")
        detail = self._service.get_graph_detail(self.graph_id)
        for node in detail.get("nodes") or []:
            node_key = str(node.get("node_key") or "")
            match = pattern.match(node_key)
            if not match:
                continue
            highest_turn = max(highest_turn, int(match.group(1)))
        return highest_turn + 1 if highest_turn else 1

    def stage_node_key(self, base_key: str) -> str:
        return f"turn_{self.turn_index}__{base_key}"

    def stage_label(self, base_label: str) -> str:
        return f"{base_label} (Turn {self.turn_index})"

    @property
    def historical_node_context(self) -> list[dict[str, Any]]:
        return list(self._historical_node_context)

    def _ensure_containers(self, user_id: str) -> None:
        for order_index, (container_key, label, role_type) in enumerate(self._CONTAINERS):
            if container_key in self._containers:
                continue
            container = self._service.create_container(
                graph_id=self.graph_id,
                container_key=container_key,
                label=label,
                role_type=role_type,
                config_json={"runtime": True},
                order_index=order_index,
                created_by=user_id,
            )
            self._containers[container_key] = container["container_id"]

    @staticmethod
    def _summarize_existing_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        summaries: list[dict[str, Any]] = []
        for node in nodes:
            config = node.get("config_json") or {}
            tool_results = config.get("tool_call_results") or []
            summaries.append(
                {
                    "node_key": node.get("node_key"),
                    "label": node.get("label"),
                    "node_type": node.get("node_type"),
                    "role_type": node.get("role_type"),
                    "run_status": config.get("run_status"),
                    "output_summary": config.get("output_summary"),
                    "tool_call_results": [
                        {
                            "tool_name": entry.get("tool_name"),
                            "request": entry.get("request"),
                            "result": entry.get("result"),
                        }
                        for entry in tool_results
                    ],
                }
            )
        return summaries

    @staticmethod
    def _build_existing_context_entries(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for node in nodes:
            config = node.get("config_json") or {}
            node_key = str(node.get("node_key") or "")
            if "output_summary" in config:
                entries.append(
                    {
                        "kind": "historical_stage_output",
                        "node_key": node_key,
                        "value": _safe_json(config.get("output_summary")),
                        "recorded_at": _utc_now_iso(),
                    }
                )
            for tool_result in config.get("tool_call_results") or []:
                entries.append(
                    {
                        "kind": "historical_tool_call_result",
                        "node_key": node_key,
                        "value": _safe_json(tool_result),
                        "recorded_at": _utc_now_iso(),
                    }
                )
        return entries

    def _build_stage_input(self, *, node_key: str, input_summary: Any) -> list[dict[str, Any]]:
        return [
            {"kind": "task", "value": _safe_json(self._task_context)},
            *self._context_entries,
            {
                "kind": "stage_input",
                "node_key": node_key,
                "value": _safe_json(input_summary),
            },
        ]

    def _append_context_entry(self, *, kind: str, node_key: str, value: Any) -> None:
        self._context_entries.append(
            {
                "kind": kind,
                "node_key": node_key,
                "value": _safe_json(value),
                "recorded_at": _utc_now_iso(),
            }
        )

    def _update_stage_config(
        self,
        *,
        stage_node: _StageNode,
        created_by: str,
        mutate: Any,
    ) -> dict[str, Any]:
        node = self._service.get_node(stage_node.node_id)
        config = dict(node.get("config_json") or {})
        mutate(config)
        self._service.update_node(
            node_id=stage_node.node_id,
            config_json=config,
            updated_by=created_by,
        )
        return config

    def start_stage(
        self,
        *,
        node_key: str,
        label: str,
        node_type: str,
        role_type: str,
        container_key: str,
        created_by: str,
        input_summary: Any,
        edge_type_from_previous: str | None = "call",
    ) -> _StageNode:
        stage_node = self._nodes.get(node_key)
        if stage_node is None:
            node = self._service.create_node(
                graph_id=self.graph_id,
                container_id=self._containers[container_key],
                node_key=node_key,
                label=label,
                node_type=node_type,
                role_type=role_type,
                config_json={
                    "runtime": True,
                    "run_status": "pending",
                    "input": self._build_stage_input(node_key=node_key, input_summary=input_summary),
                    "input_summary": _safe_json(input_summary),
                    "output": None,
                    "output_summary": None,
                    "tool_call_results": [],
                    "started_at": None,
                    "finished_at": None,
                    "error": None,
                },
                order_index=self._node_order,
                created_by=created_by,
            )
            self._node_order += 1
            stage_node = _StageNode(
                node_id=node["node_id"],
                node_key=node_key,
                label=label,
                node_type=node_type,
                role_type=role_type,
                container_id=self._containers[container_key],
            )
            self._nodes[node_key] = stage_node

            if self._last_node_id and edge_type_from_previous:
                self._service.create_edge(
                    graph_id=self.graph_id,
                    source_node_id=self._last_node_id,
                    target_node_id=stage_node.node_id,
                    edge_type=edge_type_from_previous,
                    label=edge_type_from_previous,
                    config_json={"runtime": True},
                    order_index=self._edge_order,
                    created_by=created_by,
                )
                self._edge_order += 1

        self._update_stage_config(
            stage_node=stage_node,
            created_by=created_by,
            mutate=lambda config: config.update(
                {
                    "run_status": "running",
                    "input": self._build_stage_input(node_key=node_key, input_summary=input_summary),
                    "input_summary": _safe_json(input_summary),
                    "tool_call_results": list(config.get("tool_call_results") or []),
                    "started_at": config.get("started_at") or _utc_now_iso(),
                    "error": None,
                }
            ),
        )
        self._service.patch_graph_meta(
            self.graph_id,
            {"current_node_key": node_key},
            status="running",
            updated_by=created_by,
        )
        self._last_node_id = stage_node.node_id
        self._last_node_key = node_key
        return stage_node

    def record_tool_call_result(
        self,
        node_key: str,
        *,
        created_by: str,
        tool_name: str,
        request_payload: Any,
        result_payload: Any,
    ) -> None:
        stage_node = self._nodes[node_key]
        tool_result_entry = {
            "tool_name": tool_name,
            "request": _safe_json(request_payload),
            "result": _safe_json(result_payload),
            "recorded_at": _utc_now_iso(),
        }
        self._update_stage_config(
            stage_node=stage_node,
            created_by=created_by,
            mutate=lambda config: config.update(
                {
                    "tool_call_results": [
                        *(config.get("tool_call_results") or []),
                        tool_result_entry,
                    ]
                }
            ),
        )
        self._append_context_entry(
            kind="tool_call_result",
            node_key=node_key,
            value=tool_result_entry,
        )

    def complete_stage(
        self,
        node_key: str,
        *,
        created_by: str,
        output_summary: Any,
        success: bool = True,
        error: str | None = None,
    ) -> None:
        stage_node = self._nodes[node_key]
        normalized_output = _safe_json(output_summary)
        self._update_stage_config(
            stage_node=stage_node,
            created_by=created_by,
            mutate=lambda config: config.update(
                {
                    "run_status": "succeeded" if success else "failed",
                    "output": normalized_output,
                    "output_summary": normalized_output,
                    "finished_at": _utc_now_iso(),
                    "error": error,
                }
            ),
        )
        self._append_context_entry(
            kind="stage_output",
            node_key=node_key,
            value={
                "success": success,
                "output": normalized_output,
                "error": error,
            },
        )

    def fail_graph(self, *, created_by: str, error: str, final_reply: str | None = None) -> None:
        self._service.patch_graph_meta(
            self.graph_id,
            {"error": error, "final_reply": final_reply},
            status="failed",
            updated_by=created_by,
        )

    def succeed_graph(self, *, created_by: str, final_reply: str, meta_patch: dict[str, Any] | None = None) -> None:
        patch = {"final_reply": final_reply, "error": None}
        patch.update(meta_patch or {})
        self._service.patch_graph_meta(
            self.graph_id,
            patch,
            status="succeeded",
            updated_by=created_by,
        )

    def suspend_graph(self, *, created_by: str, final_reply: str, meta_patch: dict[str, Any] | None = None) -> None:
        patch = {"final_reply": final_reply}
        patch.update(meta_patch or {})
        self._service.patch_graph_meta(
            self.graph_id,
            patch,
            status="suspended",
            updated_by=created_by,
        )


class RequirementAgentChatService:
    MAX_TOOL_CALL_ROUNDS = 6

    def __init__(
        self,
        *,
        chat_storage: AiChatService | None,
        execution_graph_service: ExecutionGraphService | None = None,
        requirements_service: RequirementsManageService | None = None,
        tools: RequirementAgentTools | None = None,
        ai_proxy_client: Any = None,
    ) -> None:
        self.chat_storage = chat_storage
        self.execution_graph_service = execution_graph_service or ExecutionGraphService(
            settings.POSTGRES_DSN
        )
        self.requirements_service = requirements_service or RequirementsManageService(
            settings.POSTGRES_DSN
        )
        self.ai_proxy = ai_proxy_client or ai_proxy
        self._actor_loop: asyncio.AbstractEventLoop | None = None
        self._actor_loop_thread: threading.Thread | None = None
        self.tools = tools or RequirementAgentTools(
            requirements_service=self.requirements_service,
            actor_query_fn=self._actor_query,
            actor_write_fn=self._actor_write,
        )

    def _hydrate_session_graph(self, session: dict[str, Any]) -> dict[str, Any]:
        hydrated = dict(session or {})
        if hydrated.get("active_graph_id"):
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

    def _resolve_session_graph_id(
        self,
        *,
        session: dict[str, Any],
        project_id: str | None,
    ) -> str | None:
        graph_id = session.get("active_graph_id")
        if graph_id:
            graph = self.execution_graph_service.get_execution_graph(graph_id)
            if graph:
                return graph_id

        latest_graph = self.execution_graph_service.get_latest_runtime_graph_by_session(
            session.get("session_id") or "",
            project_id=project_id,
        )
        if not latest_graph:
            return None

        if self.chat_storage:
            self.chat_storage.update_session(
                session_id=session["session_id"],
                active_graph_id=latest_graph["graph_id"],
            )
        return latest_graph["graph_id"]

    def create_or_get_session(self, user_id: str, project_id: str | None = None) -> dict[str, Any]:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")
        session = self.chat_storage.get_or_create_session(user_id=user_id, project_id=project_id)
        return self._hydrate_session_graph(session)

    def create_session(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        title: str | None = None,
    ) -> dict[str, Any]:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")
        session = self.chat_storage.create_session(
            user_id=user_id,
            project_id=project_id,
            title=title,
        )
        return self._hydrate_session_graph(session)

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
        )
        return [self._hydrate_session_graph(session) for session in sessions]

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
        from backend_business.services.actor.actor_manager import ActorManager
        from backend_business.services.agent.coordinator.distributed_coordinator import (
            DistributedActorCoordinator,
        )
        from backend_business.services.event_store.event_store import EventStore

        event_store = EventStore(settings.POSTGRES_DSN)
        coordinator = None
        if settings.REDIS_URL:
            coordinator = DistributedActorCoordinator(
                redis_url=settings.REDIS_URL,
                instance_id=_actor_instance_id(),
            )
        return ActorManager.get_instance(event_store, coordinator=coordinator)

    def _ensure_actor_loop(self) -> asyncio.AbstractEventLoop:
        if self._actor_loop and self._actor_loop_thread and self._actor_loop_thread.is_alive():
            return self._actor_loop

        loop = asyncio.new_event_loop()

        def _runner():
            asyncio.set_event_loop(loop)
            loop.run_forever()

        thread = threading.Thread(
            target=_runner,
            name="requirement-agent-actor-loop",
            daemon=True,
        )
        thread.start()
        self._actor_loop = loop
        self._actor_loop_thread = thread
        return loop

    def _run_actor_coro(self, coro):
        loop = self._ensure_actor_loop()
        future = asyncio.run_coroutine_threadsafe(coro, loop)
        return future.result(timeout=60)

    def _stream_llm_reply(
        self,
        *,
        prompt: str,
        system_prompt: str,
        max_new_tokens: int = 1200,
    ) -> Generator[dict[str, Any], None, str]:
        response = requests.post(
            f"{_inference_url()}/chat/stream",
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
        return self._run_actor_coro(
            actor_manager.send_command(
                requirement_id,
                {"type": "QueryState", "source": "requirement_agent_chat"},
            )
        )

    def _actor_write(self, actor_manager, requirement_id: str, command: dict[str, Any]) -> dict[str, Any]:
        return self._run_actor_coro(actor_manager.send_command(requirement_id, command))

    def _build_tool_loop_system_prompt(self) -> str:
        return (
            "你是需求管理 Agent。你运行在当前单个项目内，只能使用提供的工具查询或修改需求。"
            "必须优先依赖工具结果，不得编造需求内容或状态。"
            "如果用户要求修改需求，只有在 requirement_id 明确时才允许调用 update_requirement_content。"
            "若前端没有显式 requirement_id，必须先通过 list/search/get 明确定位到唯一需求；若仍不明确，则停止写入并转为中文澄清。"
            "search_requirements.keyword 不能为空白。"
            "工具返回是摘要结构；需要翻页时再继续调用列表或搜索工具。"
            "当工具足够回答用户时，直接给出简洁中文结论，不要输出 JSON。"
        )

    def _build_tool_loop_user_message(
        self,
        *,
        project_id: str,
        user_message: str,
        requirement_id: str | None,
        historical_node_context: list[dict[str, Any]] | None = None,
    ) -> str:
        payload = {
            "project_id": project_id,
            "selected_requirement_id": requirement_id,
            "user_message": user_message,
            "historical_node_context": historical_node_context or [],
            "scope": "当前轮对话，附带同一执行图的历史节点上下文摘要",
        }
        return json.dumps(payload, ensure_ascii=False)

    def _build_final_reply_prompt(
        self,
        *,
        user_message: str,
        tool_loop_reply: str,
        mode: str,
        context: dict[str, Any],
    ) -> tuple[str, str]:
        system_prompt = (
            "你是面向需求工程用户的中文助手。"
            "根据给定的工具执行结果和阶段结论，输出自然、简洁、直接的最终回复。"
            "如果需要澄清，就只问最小必要问题。"
            "如果已经成功更新需求，要明确说明修改内容与最新版本。"
            "不要输出 JSON。"
        )
        prompt = json.dumps(
            {
                "user_message": user_message,
                "mode": mode,
                "tool_loop_reply": tool_loop_reply,
                "resolved_requirement_id": context.get("resolved_requirement_id"),
                "resolved_requirement_summary": context.get("resolved_requirement_summary"),
                "last_write_result": context.get("last_write_result"),
                "tool_results": context.get("tool_results") or [],
            },
            ensure_ascii=False,
        )
        return system_prompt, prompt

    def _build_tool_loop_input_summary(
        self,
        *,
        round_index: int,
        messages: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        return {
            "round": round_index,
            "message_count": len(messages),
            "selected_requirement_id": context.get("selected_requirement_id"),
            "resolved_requirement_id": context.get("resolved_requirement_id"),
            "historical_node_count": len(context.get("historical_node_context") or []),
        }

    def _normalize_mode(self, context: dict[str, Any]) -> str:
        if context.get("write_performed"):
            return "requirement_update"
        if context.get("clarification_required"):
            return "clarification"
        return "chat"

    def _run_tool_call_loop(
        self,
        *,
        recorder: _RuntimeGraphRecorder,
        user_id: str,
        user_message: str,
        project_id: str,
        requirement_id: str | None,
        session_id: str,
    ) -> Generator[dict[str, Any], None, dict[str, Any]]:
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": self._build_tool_loop_system_prompt()},
            {
                "role": "user",
                "content": self._build_tool_loop_user_message(
                    project_id=project_id,
                    user_message=user_message,
                    requirement_id=requirement_id,
                    historical_node_context=recorder.historical_node_context,
                ),
            },
        ]
        context: dict[str, Any] = {
            "project_id": project_id,
            "user_id": user_id,
            "session_id": session_id,
            "graph_id": recorder.graph_id,
            "selected_requirement_id": requirement_id,
            "resolved_requirement_id": requirement_id,
            "resolved_requirement_ids": {requirement_id} if requirement_id else set(),
            "historical_node_context": recorder.historical_node_context,
            "tool_results": [],
            "write_performed": False,
            "clarification_required": False,
            "actor_manager": self._get_actor_manager(),
        }

        for round_index in range(1, self.MAX_TOOL_CALL_ROUNDS + 1):
            node_key = recorder.stage_node_key(f"requirements_agent_tool_loop_round_{round_index}")
            recorder.start_stage(
                node_key=node_key,
                label=recorder.stage_label(f"Tool Loop Round {round_index}"),
                node_type="llm",
                role_type="agent",
                container_key="requirements_agent",
                created_by=user_id,
                input_summary=self._build_tool_loop_input_summary(
                    round_index=round_index,
                    messages=messages,
                    context=context,
                ),
                edge_type_from_previous="call",
            )
            yield {
                "event": "stage",
                "data": {
                    "graph_id": recorder.graph_id,
                    "node_key": node_key,
                    "status": "running",
                },
            }

            response = self.ai_proxy.chat_completion_with_tools(
                messages=messages,
                tools=self.tools.get_tools_list(),
                temperature=0.2,
                tool_choice="auto",
            )
            tool_calls = response.get("tool_calls") or []
            assistant_content = str(response.get("content") or "").strip()
            finish_reason = response.get("finish_reason")

            assistant_message: dict[str, Any] = {
                "role": "assistant",
                "content": assistant_content,
            }
            if tool_calls:
                assistant_message["tool_calls"] = tool_calls
            messages.append(assistant_message)

            output_summary: dict[str, Any] = {
                "round": round_index,
                "finish_reason": finish_reason,
                "content": assistant_content or None,
                "tool_calls": tool_calls,
            }

            if tool_calls:
                for tool_index, tool_call in enumerate(tool_calls, start=1):
                    function_payload = tool_call.get("function") or {}
                    tool_name = function_payload.get("name") or ""
                    arguments = _coerce_tool_arguments(function_payload.get("arguments"))
                    tool_call_id = tool_call.get("id") or f"{node_key}-tool-{tool_index}"

                    yield {
                        "event": "tool_call",
                        "data": {
                            "graph_id": recorder.graph_id,
                            "node_key": node_key,
                            "tool": tool_name,
                            "tool_call_id": tool_call_id,
                            "arguments": arguments,
                        },
                    }

                    try:
                        tool_result = self.tools.execute(tool_name, arguments, context)
                    except Exception as exc:
                        tool_result = {
                            "error": str(exc),
                            "is_error": True,
                        }

                    recorder.record_tool_call_result(
                        node_key,
                        created_by=user_id,
                        tool_name=tool_name,
                        request_payload={
                            "tool_call_id": tool_call_id,
                            "arguments": arguments,
                        },
                        result_payload=tool_result,
                    )
                    context["tool_results"].append(
                        {
                            "tool_name": tool_name,
                            "arguments": arguments,
                            "result": tool_result,
                        }
                    )
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tool_call_id,
                            "content": json.dumps(tool_result, ensure_ascii=False),
                        }
                    )
                    yield {
                        "event": "tool_result",
                        "data": {
                            "graph_id": recorder.graph_id,
                            "node_key": node_key,
                            "tool": tool_name,
                            "tool_call_id": tool_call_id,
                            "result": tool_result,
                        },
                    }

                recorder.complete_stage(
                    node_key,
                    created_by=user_id,
                    output_summary=output_summary,
                )
                self.execution_graph_service.patch_graph_meta(
                    recorder.graph_id,
                    {"resolved_requirement_id": context.get("resolved_requirement_id")},
                    updated_by=user_id,
                )
                yield {
                    "event": "stage",
                    "data": {
                        "graph_id": recorder.graph_id,
                        "node_key": node_key,
                        "status": "succeeded",
                    },
                }
                continue

            if not assistant_content:
                raise ValueError("模型未返回文本或工具调用")

            recorder.complete_stage(
                node_key,
                created_by=user_id,
                output_summary=output_summary,
            )
            self.execution_graph_service.patch_graph_meta(
                recorder.graph_id,
                {"resolved_requirement_id": context.get("resolved_requirement_id")},
                updated_by=user_id,
            )
            yield {
                "event": "stage",
                "data": {
                    "graph_id": recorder.graph_id,
                    "node_key": node_key,
                    "status": "succeeded",
                },
            }
            return {
                "tool_loop_reply": assistant_content,
                "context": context,
                "rounds": round_index,
            }

        raise RuntimeError(f"工具调用轮数超过上限 {self.MAX_TOOL_CALL_ROUNDS}，已终止本次请求")

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

        recorder = _RuntimeGraphRecorder(
            execution_graph_service=self.execution_graph_service,
            project_id=project_id,
            user_id=user_id,
            requirement_id=requirement_id,
            session_id=session_id,
            user_message=user_message,
            graph_id=self._resolve_session_graph_id(session=session, project_id=project_id),
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
            if recorder._last_node_key:
                try:
                    recorder.complete_stage(
                        recorder._last_node_key,
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
