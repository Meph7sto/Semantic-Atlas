"""REST adapter that drives topology execution through ``GraphExecutor``."""

from __future__ import annotations

import json
from typing import Any

from backend_business.services.ai_proxy import ai_proxy
from backend_business.services.agent.experience import ExperienceOrchestrator
from backend_business.services.agent.runtime import (
    ContainerConfig,
    RuntimeGraphRecorder,
    with_runtime_state_contract,
)

from .graph_executor import ExecutionResult, GraphExecutor


class _NoopToolExecutor:
    """No-op tool executor for generic topology REST execution."""

    def get_tools_list(
        self,
        context: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        _ = context
        return []

    def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        _ = arguments, context
        raise ValueError(f"未知工具: {tool_name}")


class GraphExecutorTopologyRuntimeService:
    """Execute topology templates via ``GraphExecutor`` for the REST API."""

    def __init__(
        self,
        *,
        execution_graph_service: Any,
        graph_executor: GraphExecutor | Any | None = None,
        ai_proxy_client: Any = None,
        tool_executor: Any | None = None,
    ) -> None:
        self._service = execution_graph_service
        self._executor = graph_executor or GraphExecutor(
            experience_orchestrator=ExperienceOrchestrator(),
        )
        self._ai_proxy = ai_proxy_client or ai_proxy
        self._tool_executor = tool_executor or _NoopToolExecutor()

    def execute_template(
        self,
        *,
        template_graph_id: str,
        input_payload: dict[str, Any] | None,
        actor: str,
        max_steps: int = 100,
        runtime_graph_name: str | None = None,
        runtime_graph_description: str | None = None,
    ) -> dict[str, Any]:
        template_detail = self._service.get_graph_detail(template_graph_id)
        graph = (template_detail or {}).get("graph")
        if not graph:
            raise ValueError("拓扑模板不存在或已删除")
        if graph.get("graph_type") != "execution_topology_template":
            raise ValueError("仅支持执行拓扑模板图")
        template_containers = list(template_detail.get("containers") or [])
        if not template_containers:
            raise ValueError("拓扑模板不包含任何 container")

        normalized_payload = dict(input_payload or {})
        user_message = _build_user_message(normalized_payload)
        runtime_graph = self._service.create_runtime_graph(
            project_id=str(graph.get("project_id") or ""),
            name=runtime_graph_name or f"{graph.get('name') or 'Topology'} Runtime",
            description=runtime_graph_description
            or graph.get("description")
            or "拓扑模板运行时图",
            created_by=actor,
            meta_json=with_runtime_state_contract(
                {
                    "template_graph_id": template_graph_id,
                    "input_payload": normalized_payload,
                    "execution_mode": "graph_executor",
                    "max_steps": max_steps,
                }
            ),
            status="running",
        )
        recorder = RuntimeGraphRecorder(
            execution_graph_service=self._service,
            container_configs=[
                ContainerConfig(
                    container_key=str(container.get("container_key") or "container"),
                    label=str(
                        container.get("label")
                        or container.get("container_key")
                        or "Container"
                    ),
                    role_type=str(container.get("role_type") or "agent"),
                    config_json=dict(container.get("config_json") or {}),
                )
                for container in template_containers
            ],
            project_id=str(graph.get("project_id") or ""),
            user_id=actor,
            session_id=f"rest_execute::{template_graph_id}",
            user_message=user_message,
            graph_id=str(runtime_graph.get("graph_id") or ""),
            task_context={"max_tool_call_rounds": max_steps},
            attach_only=True,
        )

        events, result = _drain_execution(
            self._executor.execute(
                template_graph_id=template_graph_id,
                project_id=str(graph.get("project_id") or ""),
                user_message=user_message,
                tool_executor=self._tool_executor,
                ai_proxy_client=self._ai_proxy,
                graph_service=self._service,
                recorder=recorder,
                actor=actor,
                runtime_graph_id=recorder.graph_id,
            )
        )

        graph_id = result.graph_id or recorder.graph_id
        runtime_graph = _load_runtime_graph(self._service, graph_id)
        suspended_node = _resolve_suspended_node(
            self._service,
            graph_id=graph_id,
            suspended_subgraph_id=result.suspended_subgraph_id,
        )
        response: dict[str, Any] = {
            "status": result.status,
            "runtime_graph": runtime_graph,
            "final_output": result.final_output,
            "trace": events,
            "suspended_node": suspended_node,
        }
        if result.error:
            response["error"] = result.error
        if result.metadata is not None:
            response["metadata"] = result.metadata
        return response


def _build_user_message(input_payload: dict[str, Any]) -> str:
    message = str(input_payload.get("message") or "").strip()
    if not input_payload:
        return message

    if message and set(input_payload.keys()) == {"message"}:
        return message

    extra_payload = dict(input_payload)
    extra_payload.pop("message", None)
    payload_text = json.dumps(extra_payload or input_payload, ensure_ascii=False, indent=2)
    if message:
        return f"{message}\n\n附加输入:\n{payload_text}"
    return payload_text


def _drain_execution(gen: Any) -> tuple[list[dict[str, Any]], ExecutionResult]:
    events: list[dict[str, Any]] = []
    try:
        while True:
            events.append(next(gen))
    except StopIteration as stop:
        result = stop.value
        if isinstance(result, ExecutionResult):
            return events, result
        raise RuntimeError("GraphExecutor 未返回 ExecutionResult")


def _load_runtime_graph(service: Any, graph_id: str) -> dict[str, Any]:
    get_execution_graph = getattr(service, "get_execution_graph", None)
    if callable(get_execution_graph):
        graph = get_execution_graph(graph_id)
        if graph:
            return graph

    detail = service.get_graph_detail(graph_id)
    graph = (detail or {}).get("graph")
    if graph:
        return graph
    return {"graph_id": graph_id}


def _resolve_suspended_node(
    service: Any,
    *,
    graph_id: str,
    suspended_subgraph_id: str | None,
) -> dict[str, Any] | None:
    if not suspended_subgraph_id:
        return None

    try:
        detail = service.get_graph_detail(graph_id)
    except Exception:
        return {"subgraph_id": suspended_subgraph_id}

    for subgraph in detail.get("subgraphs") or []:
        if subgraph.get("subgraph_id") == suspended_subgraph_id:
            return subgraph
    return {"subgraph_id": suspended_subgraph_id}
