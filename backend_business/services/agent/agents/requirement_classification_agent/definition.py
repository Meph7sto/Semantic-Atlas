"""Static definition for the requirement-classification agent."""

from __future__ import annotations

from backend_business.services.agent.runtime.agent_definition import (
    AgentDefinition,
    AgentDelegation,
)

def _create_delegated_prompt_builder():
    from backend_business.services.agent.agents.session_controller.graph_prompt_builders import (
        SessionControllerClassificationDelegatePromptBuilder,
    )

    return SessionControllerClassificationDelegatePromptBuilder()


def _resolve_application_service():
    from .service import requirement_classification_agent_service

    return requirement_classification_agent_service


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
        "selected_requirement_locked": bool(requirement_id),
        "max_tool_call_rounds": source.get("max_tool_call_rounds")
        or context.get("max_tool_call_rounds"),
    }
    if requirement_id:
        patch["resolved_requirement_id"] = requirement_id
    return patch


def _postprocess_result(*, result, **_kwargs):
    context = dict(result.context or {})
    return {
        "status": "success",
        "tool_loop_reply": result.tool_loop_reply,
        "resolved_requirement_id": context.get("resolved_requirement_id"),
        "classification_result": context.get("classification_result"),
    }


REQUIREMENT_CLASSIFICATION_AGENT_DEFINITION = AgentDefinition(
    agent_type="requirement_classification_agent",
    container_key="requirement_classification_agent",
    label="Requirement Classification Agent",
    description="需求分类、标签归类、类别判断",
    max_tool_call_rounds=6,
    prompt_builder_factory=_create_delegated_prompt_builder,
    tool_executor_factory=_resolve_service_tools,
    application_service_factory=_resolve_application_service,
    context_builder=_build_runtime_context,
    result_postprocessor=_postprocess_result,
    delegated_prompt_builder_factory=_create_delegated_prompt_builder,
    delegation=AgentDelegation(
        tool_name="invoke_requirement_classification_agent",
        route_key="invoke_classification",
        decision_mode="delegate_classification",
        tool_description=(
            "将需求分类任务委托给需求分类 Agent 执行。"
            "适用于：L1/L2/L3/L4、功能/非功能、领域标签、优先级初判。"
        ),
        tool_parameters={
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": "具体的需求分类任务描述，包含目标需求或上下文",
                },
                "requirement_id": {
                    "type": "string",
                    "description": "如已知目标需求 ID，可选传入",
                },
            },
            "required": ["task_description"],
            "additionalProperties": False,
        },
        invoke_label="Invoke Requirement Classification",
        invoke_phase_label="委托需求分类 Agent",
        invoke_task_prompt="将任务委托给需求分类 Agent 执行。",
        runtime_label="Requirement Classification Runtime",
        runtime_phase_label="需求分类 Agent 执行",
        runtime_task_prompt="执行需求分类 Agent 的委托任务。",
        prompt_builder_kind="session_controller_classification_delegate",
        runtime_node_key="requirement_classification_runtime",
        result_contract="requirement_classification",
        call_edge_label="call_requirement_classification",
        accepts_requirement_id=True,
    ),
    capability_policy={
        "policy_id": "session_controller::requirement_classification_agent",
        "scope": "delegated_classification",
    },
    quota_policy={
        "policy_id": "session_controller::requirement_classification_agent::quota",
        "timeout_seconds": 180,
        "max_concurrent_runs": 4,
        "max_parallel_runs_per_scope": 1,
    },
    memory_policy={
        "scope": "container",
        "strict_memory_contract": True,
    },
    selectable_description="需求分类、标签归类、类别判断",
    binding_scope="delegated_classification",
)
