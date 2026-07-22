"""Shared application service for agent conversation execution."""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from typing import Any

from .agent_definition import AgentDefinition
from .session_graph_store import AgentSessionGraphStore


@dataclass(frozen=True)
class AgentExecutionTurn:
    definition: AgentDefinition
    session_id: str
    user_id: str
    project_id: str
    user_message: str
    session: dict[str, Any]
    graph_target: dict[str, Any]
    user_record: dict[str, Any] | None = None


class AgentExecutionService:
    """Own common session, recorder, stream, and message lifecycle work.

    Business services retain their domain-specific result adaptation while all
    public graph paths share this application boundary.
    """

    def __init__(
        self,
        *,
        definition: AgentDefinition,
        chat_storage: Any,
        session_graph_store: AgentSessionGraphStore,
    ) -> None:
        self.definition = definition
        self.chat_storage = chat_storage
        self.session_graph_store = session_graph_store

    def begin_turn(
        self,
        *,
        session_id: str,
        user_id: str,
        project_id: str,
        user_message: str,
        user_metadata: dict[str, Any] | None = None,
        create_user_message: bool = True,
    ) -> AgentExecutionTurn:
        storage = self._require_chat_storage()
        session = storage._ensure_session_access(
            session_id=session_id,
            user_id=user_id,
        )
        user_record = None
        if create_user_message:
            user_record = self.persist_user(
                session_id=session_id,
                user_id=user_id,
                content=user_message,
                metadata=user_metadata,
            )
        graph_target = self.session_graph_store.resolve_session_graph_target(
            session=session,
            project_id=project_id,
        )
        return AgentExecutionTurn(
            definition=self.definition,
            session_id=session_id,
            user_id=user_id,
            project_id=project_id,
            user_message=user_message,
            session=session,
            graph_target=graph_target,
            user_record=user_record,
        )

    def persist_user(
        self,
        *,
        session_id: str,
        user_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        storage = self._require_chat_storage()
        user_record = storage.create_message(
            session_id=session_id,
            user_id=user_id,
            role="user",
            content=content,
            metadata=dict(metadata or {}),
            is_read=True,
        )
        storage.update_session(session_id=session_id)
        return user_record

    def create_recorder(
        self,
        *,
        turn: AgentExecutionTurn,
        recorder_factory: Any,
        **recorder_kwargs: Any,
    ) -> Any:
        recorder = recorder_factory(
            project_id=turn.project_id,
            user_id=turn.user_id,
            session_id=turn.session_id,
            user_message=turn.user_message,
            graph_id=turn.graph_target["graph_id"],
            prev_graph_id=turn.graph_target["prev_graph_id"],
            **recorder_kwargs,
        )
        self.activate_graph(turn=turn, graph_id=recorder.graph_id)
        return recorder

    def activate_graph(self, *, turn: AgentExecutionTurn, graph_id: str) -> None:
        self._require_chat_storage().update_session(
            session_id=turn.session_id,
            active_graph_id=graph_id,
        )

    def stream_generator(
        self,
        generator: Generator[dict[str, Any], None, Any],
    ) -> Generator[dict[str, Any], None, Any]:
        """Relay events without losing the generator's typed return value."""
        try:
            while True:
                yield next(generator)
        except StopIteration as stop:
            return stop.value

    def persist_assistant(
        self,
        *,
        turn: AgentExecutionTurn,
        content: str,
        metadata: dict[str, Any] | None = None,
        is_read: bool = False,
    ) -> dict[str, Any]:
        return self._require_chat_storage().create_message(
            session_id=turn.session_id,
            user_id=turn.user_id,
            role="assistant",
            content=content,
            metadata=dict(metadata or {}),
            is_read=is_read,
        )

    def persist_error(
        self,
        *,
        turn: AgentExecutionTurn,
        graph_id: str,
        error: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        error_metadata = {"error": True, "graph_id": graph_id}
        error_metadata.update(metadata or {})
        return self.persist_assistant(
            turn=turn,
            content=error,
            metadata=error_metadata,
        )

    def _require_chat_storage(self) -> Any:
        if self.chat_storage is None:
            raise RuntimeError("AI chat storage not initialized")
        return self.chat_storage
