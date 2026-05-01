"""Reusable session and runtime-graph persistence helpers for agents."""

from __future__ import annotations

import inspect
from collections.abc import Callable
from typing import Any

from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.ai_chat_service import AiChatService

_CONTEXT_MODES = {"full", "incremental", "scratchpad"}


def normalize_context_mode(value: Any, *, default: str = "full") -> str:
    """Normalize the chat context mode used by agent sessions."""

    return value if value in _CONTEXT_MODES else default


class AgentSessionGraphStore:
    """Own session CRUD, active graph hydration, and graph-chain lookup."""

    def __init__(
        self,
        *,
        chat_storage: AiChatService | None,
        execution_graph_service: ExecutionGraphService,
        agent_type: str,
        prompt_payload_normalizer: Callable[[Any], Any] | None = None,
        context_mode_normalizer: Callable[[Any], Any] | None = normalize_context_mode,
        create_or_get_prompt_update_policy: str = "provided",
        create_or_get_context_update_policy: str = "provided",
        create_or_get_updates_unchanged: bool = False,
    ) -> None:
        self.chat_storage = chat_storage
        self.execution_graph_service = execution_graph_service
        self.agent_type = agent_type
        self.prompt_payload_normalizer = prompt_payload_normalizer
        self.context_mode_normalizer = context_mode_normalizer
        self.create_or_get_prompt_update_policy = create_or_get_prompt_update_policy
        self.create_or_get_context_update_policy = create_or_get_context_update_policy
        self.create_or_get_updates_unchanged = create_or_get_updates_unchanged

    @staticmethod
    def _call_storage_method(method: Any, /, **kwargs: Any) -> Any:
        """Call storage methods while tolerating narrow test doubles."""

        signature = inspect.signature(method)
        if any(
            param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values()
        ):
            return method(**kwargs)
        accepted_kwargs = {
            key: value for key, value in kwargs.items() if key in signature.parameters
        }
        return method(**accepted_kwargs)

    def hydrate_session_graph(self, session: dict[str, Any]) -> dict[str, Any]:
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
                self._call_storage_method(
                    self.chat_storage.update_session,
                    session_id=hydrated["session_id"],
                    active_graph_id=latest_graph["graph_id"],
                )
        return hydrated

    def resolve_session_graph_target(
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
            self._call_storage_method(
                self.chat_storage.update_session,
                session_id=session["session_id"],
                active_graph_id=latest_graph["graph_id"],
            )
        if latest_graph.get("status") == "suspended":
            return {"graph_id": latest_graph["graph_id"], "prev_graph_id": None}
        return {"graph_id": None, "prev_graph_id": latest_graph["graph_id"]}

    def create_or_get_session(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        chat_storage = self._require_chat_storage()
        session = self._call_storage_method(
            chat_storage.get_or_create_session,
            user_id=user_id,
            project_id=project_id,
            agent_type=self.agent_type,
        )
        if self._should_update_create_or_get_prompt(prompt_payload_format):
            normalized_format = self._normalize_prompt_payload_format(prompt_payload_format)
            if (
                self.create_or_get_updates_unchanged
                or session.get("prompt_payload_format") != normalized_format
            ):
                self._call_storage_method(
                    chat_storage.update_session,
                    session_id=session["session_id"],
                    prompt_payload_format=normalized_format,
                )
                session["prompt_payload_format"] = normalized_format
        if self._should_update_create_or_get_context(context_mode):
            normalized_context_mode = self._normalize_context_mode(context_mode)
            if (
                self.create_or_get_updates_unchanged
                or session.get("context_mode") != normalized_context_mode
            ):
                self._call_storage_method(
                    chat_storage.update_session,
                    session_id=session["session_id"],
                    context_mode=normalized_context_mode,
                )
                session["context_mode"] = normalized_context_mode
        return self.hydrate_session_graph(session)

    def create_session(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        title: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        chat_storage = self._require_chat_storage()
        session = self._call_storage_method(
            chat_storage.create_session,
            user_id=user_id,
            project_id=project_id,
            title=title,
            prompt_payload_format=self._normalize_prompt_payload_format(prompt_payload_format),
            context_mode=self._normalize_context_mode(context_mode),
            agent_type=self.agent_type,
        )
        return self.hydrate_session_graph(session)

    def update_session(
        self,
        *,
        session_id: str,
        user_id: str,
        title: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
    ) -> dict[str, Any]:
        chat_storage = self._require_chat_storage()
        chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
        update_kwargs: dict[str, Any] = {
            "session_id": session_id,
            "title": title,
        }
        if prompt_payload_format is not None:
            update_kwargs["prompt_payload_format"] = self._normalize_prompt_payload_format(
                prompt_payload_format
            )
        if context_mode is not None:
            update_kwargs["context_mode"] = self._normalize_context_mode(context_mode)
        self._call_storage_method(chat_storage.update_session, **update_kwargs)
        current = chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
        return self.hydrate_session_graph(current)

    def list_sessions(
        self,
        *,
        user_id: str,
        project_id: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        chat_storage = self._require_chat_storage()
        sessions = self._call_storage_method(
            chat_storage.list_sessions,
            user_id=user_id,
            project_id=project_id,
            limit=limit,
            agent_type=self.agent_type,
        )
        return [self.hydrate_session_graph(session) for session in sessions]

    def list_session_graph_chain(
        self,
        *,
        session_id: str,
        user_id: str,
    ) -> dict[str, Any]:
        chat_storage = self._require_chat_storage()
        session = chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
        hydrated_session = self.hydrate_session_graph(session)
        graphs = self.execution_graph_service.list_runtime_graphs_by_session(
            session_id=session_id,
            project_id=hydrated_session.get("project_id"),
        )
        ordered_graphs = self.sort_session_graphs_as_chain(graphs)
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
        chat_storage = self._require_chat_storage()
        session = chat_storage._ensure_session_access(session_id=session_id, user_id=user_id)
        session_graphs = self.execution_graph_service.list_runtime_graphs_by_session(
            session_id=session_id,
            project_id=session.get("project_id"),
        )

        deleted = chat_storage.delete_session(session_id)
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

    def list_messages(
        self,
        *,
        session_id: str,
        user_id: str,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        chat_storage = self._require_chat_storage()
        return chat_storage.list_messages(
            session_id=session_id,
            user_id=user_id,
            limit=limit,
        )

    def get_graph_detail(self, graph_id: str) -> dict[str, Any]:
        return self.execution_graph_service.get_graph_detail(graph_id)

    def get_graph(self, graph_id: str) -> dict[str, Any] | None:
        return self.execution_graph_service.get_execution_graph(graph_id)

    @staticmethod
    def sort_session_graphs_as_chain(
        graphs: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
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

    def _require_chat_storage(self) -> AiChatService:
        if not self.chat_storage:
            raise RuntimeError("AI chat storage not initialized")
        return self.chat_storage

    def _normalize_prompt_payload_format(self, value: Any) -> Any:
        if self.prompt_payload_normalizer is None:
            return value
        return self.prompt_payload_normalizer(value)

    def _normalize_context_mode(self, value: Any) -> Any:
        if self.context_mode_normalizer is None:
            return value
        return self.context_mode_normalizer(value)

    def _should_update_create_or_get_prompt(self, value: Any) -> bool:
        if self.create_or_get_prompt_update_policy == "never":
            return False
        if self.create_or_get_prompt_update_policy == "truthy":
            return bool(value)
        return value is not None

    def _should_update_create_or_get_context(self, value: Any) -> bool:
        if self.create_or_get_context_update_policy == "never":
            return False
        if self.create_or_get_context_update_policy == "allowed":
            return value in _CONTEXT_MODES
        if self.create_or_get_context_update_policy == "truthy":
            return bool(value)
        return value is not None
