"""Builtin execution-topology template for SessionController graph mode."""

from __future__ import annotations

from typing import Any


_TEMPLATE_KIND = "session_controller_graph_executor_phase2"
_TEMPLATE_NAME = "Session Controller GraphExecutor Template"
_TEMPLATE_VERSION = 3


def ensure_session_controller_template(
    *,
    execution_graph_service: Any,
    project_id: str,
    actor: str,
) -> str:
    """Ensure the built-in SessionController topology template exists."""
    existing_templates = execution_graph_service.list_execution_graphs(project_id=project_id)
    for graph in existing_templates:
        meta = graph.get("meta_json") or {}
        if (
            meta.get("system_template_kind") == _TEMPLATE_KIND
            and int(meta.get("template_version") or 0) >= _TEMPLATE_VERSION
        ):
            return graph["graph_id"]

    graph = execution_graph_service.create_execution_graph(
        project_id=project_id,
        name=_TEMPLATE_NAME,
        description="Session Controller GraphExecutor builtin template",
        meta_json={
            "system_template_kind": _TEMPLATE_KIND,
            "template_version": _TEMPLATE_VERSION,
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
    requirement_container = execution_graph_service.create_container(
        graph_id=graph_id,
        container_key="requirement_agent",
        label="Requirement Agent",
        role_type="agent",
        config_json={"system_template_kind": _TEMPLATE_KIND},
        order_index=1,
        created_by=actor,
    )
    conflict_container = execution_graph_service.create_container(
        graph_id=graph_id,
        container_key="conflict_detection",
        label="Conflict Detection Agent",
        role_type="agent",
        config_json={"system_template_kind": _TEMPLATE_KIND},
        order_index=2,
        created_by=actor,
    )
    classification_container = execution_graph_service.create_container(
        graph_id=graph_id,
        container_key="requirement_classification_agent",
        label="Requirement Classification Agent",
        role_type="agent",
        config_json={"system_template_kind": _TEMPLATE_KIND},
        order_index=3,
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
    invoke_requirement_node = execution_graph_service.create_node(
        graph_id=graph_id,
        container_id=container_id,
        node_key="invoke_requirement_agent",
        label="Invoke Requirement Agent",
        node_type="invoke",
        role_type="agent",
        phase_label="委托需求 Agent",
        task_prompt="将任务委托给需求管理 Agent 执行。",
        conditional_edges=[],
        config_json={
            "delegate_agent": "requirement_agent",
            "result_contract": "session_controller_invoke",
        },
        order_index=4,
        created_by=actor,
    )
    invoke_conflict_node = execution_graph_service.create_node(
        graph_id=graph_id,
        container_id=container_id,
        node_key="invoke_conflict_detection",
        label="Invoke Conflict Detection",
        node_type="invoke",
        role_type="agent",
        phase_label="委托冲突检测 Agent",
        task_prompt="将任务委托给冲突检测 Agent 执行。",
        conditional_edges=[],
        config_json={
            "delegate_agent": "conflict_detection",
            "result_contract": "session_controller_invoke",
        },
        order_index=5,
        created_by=actor,
    )
    invoke_classification_node = execution_graph_service.create_node(
        graph_id=graph_id,
        container_id=container_id,
        node_key="invoke_requirement_classification_agent",
        label="Invoke Requirement Classification",
        node_type="invoke",
        role_type="agent",
        phase_label="委托需求分类 Agent",
        task_prompt="将任务委托给需求分类 Agent 执行。",
        conditional_edges=[],
        config_json={
            "delegate_agent": "requirement_classification_agent",
            "result_contract": "session_controller_invoke",
        },
        order_index=6,
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
        order_index=7,
        created_by=actor,
    )
    requirement_runtime_node = execution_graph_service.create_node(
        graph_id=graph_id,
        container_id=requirement_container["container_id"],
        node_key="requirement_agent_runtime",
        label="Requirement Agent Runtime",
        node_type="llm",
        role_type="agent",
        phase_label="需求 Agent 执行",
        task_prompt="执行需求管理 Agent 的委托任务。",
        conditional_edges=[],
        config_json={
            "prompt_builder": "session_controller_requirement_delegate",
            "complete_phase_enabled": False,
            "result_contract": "requirement_agent",
        },
        order_index=0,
        created_by=actor,
    )
    conflict_runtime_node = execution_graph_service.create_node(
        graph_id=graph_id,
        container_id=conflict_container["container_id"],
        node_key="conflict_detection_runtime",
        label="Conflict Detection Runtime",
        node_type="llm",
        role_type="agent",
        phase_label="冲突检测 Agent 执行",
        task_prompt="执行冲突检测 Agent 的委托任务。",
        conditional_edges=[],
        config_json={
            "prompt_builder": "session_controller_conflict_delegate",
            "complete_phase_enabled": False,
            "result_contract": "conflict_detection",
        },
        order_index=0,
        created_by=actor,
    )
    classification_runtime_node = execution_graph_service.create_node(
        graph_id=graph_id,
        container_id=classification_container["container_id"],
        node_key="requirement_classification_runtime",
        label="Requirement Classification Runtime",
        node_type="llm",
        role_type="agent",
        phase_label="需求分类 Agent 执行",
        task_prompt="执行需求分类 Agent 的委托任务。",
        conditional_edges=[],
        config_json={
            "prompt_builder": "session_controller_classification_delegate",
            "complete_phase_enabled": False,
            "result_contract": "requirement_classification",
        },
        order_index=0,
        created_by=actor,
    )
    execution_graph_service.update_node(
        node_id=intake_node["node_id"],
        conditional_edges=[
            {
                "condition": "suspend",
                "target_node_id": suspend_reply_node["node_id"],
            },
            {
                "condition": "invoke_requirement",
                "target_node_id": invoke_requirement_node["node_id"],
            },
            {
                "condition": "invoke_conflict",
                "target_node_id": invoke_conflict_node["node_id"],
            },
            {
                "condition": "invoke_classification",
                "target_node_id": invoke_classification_node["node_id"],
            },
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
            {
                "condition": "invoke_requirement",
                "target_node_id": invoke_requirement_node["node_id"],
            },
            {
                "condition": "invoke_conflict",
                "target_node_id": invoke_conflict_node["node_id"],
            },
            {
                "condition": "invoke_classification",
                "target_node_id": invoke_classification_node["node_id"],
            },
            {
                "condition": "reply",
                "target_node_id": final_reply_node["node_id"],
            },
        ],
        updated_by=actor,
    )
    for invoke_node in (
        invoke_requirement_node,
        invoke_conflict_node,
        invoke_classification_node,
    ):
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
    execution_graph_service.create_edge(
        graph_id=graph_id,
        source_node_id=invoke_requirement_node["node_id"],
        target_node_id=requirement_runtime_node["node_id"],
        edge_type="call",
        label="call_requirement_agent",
        order_index=3,
        created_by=actor,
    )
    execution_graph_service.create_edge(
        graph_id=graph_id,
        source_node_id=invoke_conflict_node["node_id"],
        target_node_id=conflict_runtime_node["node_id"],
        edge_type="call",
        label="call_conflict_detection",
        order_index=4,
        created_by=actor,
    )
    execution_graph_service.create_edge(
        graph_id=graph_id,
        source_node_id=invoke_classification_node["node_id"],
        target_node_id=classification_runtime_node["node_id"],
        edge_type="call",
        label="call_requirement_classification",
        order_index=5,
        created_by=actor,
    )

    return graph_id
