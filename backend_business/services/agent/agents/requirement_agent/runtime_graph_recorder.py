"""Requirement-agent adapter for the generic runtime graph recorder."""

from __future__ import annotations

from datetime import datetime, timezone

from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.runtime.graph_recorder import (
    ContainerConfig,
    RuntimeGraphRecorder,
    StageNode,
)

_StageNode = StageNode


class _RuntimeGraphRecorder(RuntimeGraphRecorder):
    """Backward-compatible recorder preserving requirement-agent defaults."""

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
        super().__init__(
            execution_graph_service=execution_graph_service,
            container_configs=[
                ContainerConfig(container_key=key, label=label, role_type=role_type)
                for key, label, role_type in self._CONTAINERS
            ],
            project_id=project_id,
            user_id=user_id,
            session_id=session_id,
            user_message=user_message,
            graph_id=graph_id,
            graph_name=f"Requirement Agent Run {datetime.now(timezone.utc).strftime('%H:%M:%S')}",
            graph_description="需求管理 Agent 运行轨迹",
            initial_graph_meta={
                "requirement_id": requirement_id,
                "resolved_requirement_id": requirement_id,
                "intent": "pending",
            },
            task_context={
                "requirement_id": requirement_id,
            },
        )

