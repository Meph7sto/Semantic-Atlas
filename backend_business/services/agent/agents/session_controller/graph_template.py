"""Builtin execution-topology template for SessionController graph mode."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from typing import Any

from backend_business.services.agent.runtime.agent_registry import (
    BUILTIN_AGENT_REGISTRY,
    AgentRegistry,
)

_TEMPLATE_KIND = "session_controller_graph_executor_phase2"
_TEMPLATE_NAME = "Session Controller GraphExecutor Template"
_TEMPLATE_VERSION = 5


def _agent_catalog_fingerprint(registry: AgentRegistry) -> str:
    """Hash the catalog fields that shape the generated delegation topology."""

    payload = [
        {
            "agent_type": definition.agent_type,
            "container_key": definition.container_key,
            "label": definition.label,
            "role_type": definition.role_type,
            "delegation": asdict(definition.delegation),
        }
        for definition in registry.delegated_definitions()
        if definition.delegation is not None
    ]
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def ensure_session_controller_template(
    *,
    execution_graph_service: Any,
    project_id: str,
    actor: str,
    agent_registry: AgentRegistry | None = None,
) -> str:
    """Ensure the built-in SessionController topology template exists."""
    registry = agent_registry or BUILTIN_AGENT_REGISTRY
    catalog_fingerprint = _agent_catalog_fingerprint(registry)
    existing_templates = execution_graph_service.list_execution_graphs(project_id=project_id)
    for graph in existing_templates:
        meta = graph.get("meta_json") or {}
        if (
            meta.get("system_template_kind") == _TEMPLATE_KIND
            and int(meta.get("template_version") or 0) >= _TEMPLATE_VERSION
            and meta.get("agent_catalog_fingerprint") == catalog_fingerprint
        ):
            return graph["graph_id"]

    graph = execution_graph_service.create_execution_graph(
        project_id=project_id,
        name=_TEMPLATE_NAME,
        description="Session Controller GraphExecutor builtin template",
        meta_json={
            "system_template_kind": _TEMPLATE_KIND,
            "template_version": _TEMPLATE_VERSION,
            "agent_catalog_fingerprint": catalog_fingerprint,
            "hidden": True,
        },
        created_by=actor,
    )
    graph_id = graph["graph_id"]

    container = execution_graph_service.create_container(
        graph_id=graph_id,
        container_key="conductor",
        label="Session Controller",
        role_type="agent",
        config_json={"system_template_kind": _TEMPLATE_KIND},
        order_index=0,
        created_by=actor,
    )
    container_id = container["container_id"]
    delegated_definitions = registry.delegated_definitions()
    delegated_containers: dict[str, dict[str, Any]] = {}
    for order_index, definition in enumerate(
        delegated_definitions,
        start=1,
    ):
        delegated_containers[definition.container_key] = execution_graph_service.create_container(
            graph_id=graph_id,
            container_key=definition.container_key,
            label=definition.label,
            role_type=definition.role_type,
            config_json={
                "system_template_kind": _TEMPLATE_KIND,
                "agent_type": definition.agent_type,
            },
            order_index=order_index,
            created_by=actor,
        )
    intake_node = execution_graph_service.create_node(
        graph_id=graph_id,
        container_id=container_id,
        node_key="controller_intake",
        label="Controller Intake",
        node_type="llm",
        role_type="agent",
        phase_label="总控决策",
        task_prompt="执行 Session Controller 的结构化决策与工具调度。",
        conditional_edges=[],
        config_json={
            "prompt_builder": "session_controller_decision",
            "native_invoke_enabled": True,
        },
        order_index=0,
        created_by=actor,
    )
    suspend_reply_node = execution_graph_service.create_node(
        graph_id=graph_id,
        container_id=container_id,
        node_key="suspend_reply",
        label="Suspend Reply",
        node_type="llm",
        role_type="agent",
        phase_label="挂起回复",
        task_prompt="向用户发送挂起前回复。",
        conditional_edges=[],
        config_json={"prompt_builder": "session_controller_suspend_reply"},
        order_index=1,
        created_by=actor,
    )
    await_user_node = execution_graph_service.create_node(
        graph_id=graph_id,
        container_id=container_id,
        node_key="await_user",
        label="Await User",
        node_type="handoff",
        role_type="agent",
        phase_label="等待用户",
        task_prompt="",
        config_json={"prompt_builder": "handoff"},
        order_index=2,
        created_by=actor,
    )
    resume_intake_node = execution_graph_service.create_node(
        graph_id=graph_id,
        container_id=container_id,
        node_key="controller_resume_intake",
        label="Controller Resume Intake",
        node_type="llm",
        role_type="agent",
        phase_label="恢复后总控决策",
        task_prompt="基于用户补充继续执行 Session Controller 的结构化决策。",
        conditional_edges=[],
        config_json={
            "prompt_builder": "session_controller_decision",
            "native_invoke_enabled": True,
        },
        order_index=3,
        created_by=actor,
    )
    invoke_nodes: dict[str, dict[str, Any]] = {}
    for order_index, definition in enumerate(delegated_definitions, start=4):
        delegation = definition.delegation
        if delegation is None:
            continue
        invoke_nodes[definition.container_key] = execution_graph_service.create_node(
            graph_id=graph_id,
            container_id=container_id,
            node_key=delegation.tool_name,
            label=delegation.invoke_label,
            node_type="invoke",
            role_type="agent",
            phase_label=delegation.invoke_phase_label,
            task_prompt=delegation.invoke_task_prompt,
            conditional_edges=[],
            config_json={
                "delegate_agent": definition.container_key,
                "agent_type": definition.agent_type,
                "result_contract": "session_controller_invoke",
            },
            order_index=order_index,
            created_by=actor,
        )
    final_reply_node = execution_graph_service.create_node(
        graph_id=graph_id,
        container_id=container_id,
        node_key="final_reply",
        label="Final Reply",
        node_type="llm",
        role_type="agent",
        phase_label="最终回复",
        task_prompt="生成最终用户回复。",
        config_json={"prompt_builder": "session_controller_final_reply"},
        order_index=4 + len(delegated_definitions),
        created_by=actor,
    )
    runtime_nodes: dict[str, dict[str, Any]] = {}
    for definition in delegated_definitions:
        delegation = definition.delegation
        if delegation is None:
            continue
        runtime_nodes[definition.container_key] = execution_graph_service.create_node(
            graph_id=graph_id,
            container_id=delegated_containers[definition.container_key]["container_id"],
            node_key=delegation.runtime_node_key,
            label=delegation.runtime_label,
            node_type="llm",
            role_type=definition.role_type,
            phase_label=delegation.runtime_phase_label,
            task_prompt=delegation.runtime_task_prompt,
            conditional_edges=[],
            config_json={
                "prompt_builder": delegation.prompt_builder_kind,
                "agent_type": definition.agent_type,
                "complete_phase_enabled": False,
                "result_contract": delegation.result_contract,
            },
            order_index=0,
            created_by=actor,
        )
    delegation_edges = [
        {
            "condition": definition.delegation.route_key,
            "target_node_id": invoke_nodes[definition.container_key]["node_id"],
        }
        for definition in delegated_definitions
        if definition.delegation is not None
    ]
    execution_graph_service.update_node(
        node_id=intake_node["node_id"],
        conditional_edges=[
            {
                "condition": "suspend",
                "target_node_id": suspend_reply_node["node_id"],
            },
            *delegation_edges,
            {
                "condition": "reply",
                "target_node_id": final_reply_node["node_id"],
            }
        ],
        updated_by=actor,
    )
    execution_graph_service.update_node(
        node_id=resume_intake_node["node_id"],
        conditional_edges=[
            {
                "condition": "suspend",
                "target_node_id": suspend_reply_node["node_id"],
            },
            *delegation_edges,
            {
                "condition": "reply",
                "target_node_id": final_reply_node["node_id"],
            },
        ],
        updated_by=actor,
    )
    for invoke_node in invoke_nodes.values():
        execution_graph_service.update_node(
            node_id=invoke_node["node_id"],
            conditional_edges=[
                {
                    "condition": "suspend",
                    "target_node_id": suspend_reply_node["node_id"],
                },
                {
                    "condition": "reply",
                    "target_node_id": final_reply_node["node_id"],
                },
            ],
            updated_by=actor,
        )

    execution_graph_service.create_edge(
        graph_id=graph_id,
        source_node_id=intake_node["node_id"],
        target_node_id=suspend_reply_node["node_id"],
        edge_type="seq",
        label="suspend",
        order_index=0,
        created_by=actor,
    )
    execution_graph_service.create_edge(
        graph_id=graph_id,
        source_node_id=suspend_reply_node["node_id"],
        target_node_id=await_user_node["node_id"],
        edge_type="seq",
        label="handoff",
        order_index=1,
        created_by=actor,
    )
    execution_graph_service.create_edge(
        graph_id=graph_id,
        source_node_id=await_user_node["node_id"],
        target_node_id=resume_intake_node["node_id"],
        edge_type="seq",
        label="resume",
        order_index=2,
        created_by=actor,
    )
    for order_index, definition in enumerate(delegated_definitions, start=3):
        delegation = definition.delegation
        if delegation is None:
            continue
        execution_graph_service.create_edge(
            graph_id=graph_id,
            source_node_id=invoke_nodes[definition.container_key]["node_id"],
            target_node_id=runtime_nodes[definition.container_key]["node_id"],
            edge_type="call",
            label=delegation.call_edge_label,
            order_index=order_index,
            created_by=actor,
        )

    return graph_id
