"""Static definition for the requirement traceability agent."""

from __future__ import annotations

from backend_business.services.agent.runtime.agent_definition import (
    AgentDefinition,
    AgentDelegation,
)


def _create_prompt_builder():
    from .prompt_builder import TraceabilityAgentPromptBuilder

    return TraceabilityAgentPromptBuilder()


def _resolve_application_service():
    from .service import traceability_agent_service

    return traceability_agent_service


def _resolve_service_tools(*, service=None, **_kwargs):
    return getattr(service, "tools", None)


def _build_runtime_context(*, context, invoke_request=None, **_kwargs):
    source = invoke_request or context
    high_level_requirement_id = str(
        source.get("high_level_requirement_id")
        or context.get("high_level_requirement_id")
        or ""
    ).strip() or None
    low_level_requirement_id = str(
        source.get("low_level_requirement_id")
        or context.get("low_level_requirement_id")
        or ""
    ).strip() or None
    return {
        "high_level_requirement_id": high_level_requirement_id,
        "low_level_requirement_id": low_level_requirement_id,
        "max_tool_call_rounds": source.get("max_tool_call_rounds")
        or context.get("max_tool_call_rounds"),
        "traceability_result": context.get("traceability_result"),
    }


def _postprocess_result(*, result, **_kwargs):
    context = dict(result.context or {})
    return {
        "status": "success",
        "tool_loop_reply": result.tool_loop_reply,
        "high_level_requirement_id": context.get("high_level_requirement_id"),
        "low_level_requirement_id": context.get("low_level_requirement_id"),
        "traceability_result": context.get("traceability_result"),
    }


TRACEABILITY_AGENT_DEFINITION = AgentDefinition(
    agent_type="traceability_agent",
    container_key="traceability_agent",
    label="Traceability Agent",
    description="顶层需求与底层需求的追溯关系分析",
    max_tool_call_rounds=6,
    prompt_builder_factory=_create_prompt_builder,
    tool_executor_factory=_resolve_service_tools,
    application_service_factory=_resolve_application_service,
    context_builder=_build_runtime_context,
    result_postprocessor=_postprocess_result,
    delegated_prompt_builder_factory=_create_prompt_builder,
    delegation=AgentDelegation(
        tool_name="invoke_traceability_agent",
        route_key="invoke_traceability",
        decision_mode="delegate_traceability",
        tool_description=(
            "将顶层需求与底层需求之间的追溯任务委托给需求追溯 Agent。"
            "适用于：确认低层需求是否细化、实现或支撑顶层需求。"
        ),
        tool_parameters={
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": "具体的追溯任务描述，包含用户原始意图和必要上下文",
                },
                "high_level_requirement_id": {
                    "type": "string",
                    "description": "已知时传入顶层需求 ID",
                },
                "low_level_requirement_id": {
                    "type": "string",
                    "description": "已知时传入底层需求 ID",
                },
            },
            "required": ["task_description"],
            "additionalProperties": False,
        },
        invoke_label="Invoke Traceability Agent",
        invoke_phase_label="委托需求追溯 Agent",
        invoke_task_prompt="将顶层到低层需求的追溯任务委托给需求追溯 Agent 执行。",
        runtime_label="Traceability Agent Runtime",
        runtime_phase_label="需求追溯 Agent 执行",
        runtime_task_prompt="执行需求追溯 Agent 的委托任务。",
        prompt_builder_kind="session_controller_traceability_delegate",
        runtime_node_key="traceability_agent_runtime",
        result_contract="traceability_agent",
        call_edge_label="call_traceability_agent",
        forwarded_argument_names=(
            "high_level_requirement_id",
            "low_level_requirement_id",
        ),
        routing_keywords=(
            "需求追溯",
            "追溯关系",
            "顶层需求",
            "底层需求",
            "上下级需求",
            "高层需求",
            "低层需求",
            "traceability",
        ),
    ),
    capability_policy={
        "policy_id": "session_controller::traceability_agent",
        "scope": "delegated_traceability",
    },
    quota_policy={
        "policy_id": "session_controller::traceability_agent::quota",
        "timeout_seconds": 180,
        "max_concurrent_runs": 4,
        "max_parallel_runs_per_scope": 1,
    },
    memory_policy={
        "scope": "container",
        "strict_memory_contract": True,
    },
    selectable_description="顶层需求与底层需求的追溯关系分析",
    binding_scope="delegated_traceability",
)
