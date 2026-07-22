"""Static definition for the requirement-management agent."""

from __future__ import annotations

from backend_business.services.agent.runtime.agent_definition import (
    AgentDefinition,
    AgentDelegation,
)

def _create_delegated_prompt_builder():
    from backend_business.services.agent.agents.session_controller.graph_prompt_builders import (
        SessionControllerRequirementDelegatePromptBuilder,
    )

    return SessionControllerRequirementDelegatePromptBuilder()


def _resolve_application_service():
    from .service import requirement_agent_chat_service

    return requirement_agent_chat_service


def _resolve_service_tools(*, service=None, **_kwargs):
    return getattr(service, "tools", None)


def _build_runtime_context(*, context, invoke_request=None, **_kwargs):
    source = invoke_request or context
    requirement_id = str(
        source.get("requirement_id")
        or context.get("selected_requirement_id")
        or context.get("resolved_requirement_id")
        or ""
    ).strip() or None
    patch = {
        "selected_requirement_id": requirement_id,
        "prompt_payload_format": source.get("prompt_payload_format")
        or context.get("prompt_payload_format")
        or "markdown",
        "historical_node_context": context.get("historical_node_context") or [],
        "max_tool_call_rounds": source.get("max_tool_call_rounds")
        or context.get("max_tool_call_rounds"),
    }
    if requirement_id:
        patch["resolved_requirement_id"] = requirement_id
    return patch


def _postprocess_result(*, result, **_kwargs):
    context = dict(result.context or {})
    raw_mode = str(
        context.get("mode")
        or (
            "approval_pending"
            if context.get("approval_pending")
            else "clarification"
            if context.get("clarification_required")
            else "chat"
        )
    ).strip().lower()
    return {
        "status": "success",
        "tool_loop_reply": result.tool_loop_reply,
        "resolved_requirement_id": context.get("resolved_requirement_id"),
        "write_result": context.get("last_write_result"),
        "mode": raw_mode,
        "clarification_required": raw_mode == "clarification",
        "approval_pending": bool(context.get("approval_pending")),
        "approval_result": context.get("last_approval_result"),
    }


REQUIREMENT_AGENT_DEFINITION = AgentDefinition(
    agent_type="requirement_agent",
    container_key="requirement_agent",
    label="Requirement Agent",
    description="需求检索、需求分析、需求修改",
    max_tool_call_rounds=6,
    prompt_builder_factory=_create_delegated_prompt_builder,
    tool_executor_factory=_resolve_service_tools,
    application_service_factory=_resolve_application_service,
    context_builder=_build_runtime_context,
    result_postprocessor=_postprocess_result,
    delegated_prompt_builder_factory=_create_delegated_prompt_builder,
    delegation=AgentDelegation(
        tool_name="invoke_requirement_agent",
        route_key="invoke_requirement",
        decision_mode="delegate_requirement",
        tool_description=(
            "将需求管理任务委托给需求管理 Agent 执行。"
            "适用于：读取需求详情、修改需求内容、需求状态查询等。"
            "task_description 必须是具体的任务描述，包含用户原始意图和上下文。"
        ),
        tool_parameters={
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": "详细的任务描述，包含用户意图和必要上下文",
                },
                "requirement_id": {
                    "type": "string",
                    "description": "如已知目标需求 ID，可选传入",
                },
            },
            "required": ["task_description"],
            "additionalProperties": False,
        },
        invoke_label="Invoke Requirement Agent",
        invoke_phase_label="委托需求 Agent",
        invoke_task_prompt="将任务委托给需求管理 Agent 执行。",
        runtime_label="Requirement Agent Runtime",
        runtime_phase_label="需求 Agent 执行",
        runtime_task_prompt="执行需求管理 Agent 的委托任务。",
        prompt_builder_kind="session_controller_requirement_delegate",
        runtime_node_key="requirement_agent_runtime",
        result_contract="requirement_agent",
        call_edge_label="call_requirement_agent",
        accepts_requirement_id=True,
        include_prompt_preferences=True,
    ),
    capability_policy={
        "policy_id": "session_controller::requirement_agent",
        "scope": "delegated_requirement",
    },
    quota_policy={
        "policy_id": "session_controller::requirement_agent::quota",
        "timeout_seconds": 180,
        "max_concurrent_runs": 4,
        "max_parallel_runs_per_scope": 1,
    },
    memory_policy={
        "scope": "container",
        "strict_memory_contract": True,
    },
    selectable_description="需求检索、需求分析、需求修改",
    binding_scope="delegated_requirement",
)
