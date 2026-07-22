"""Static definition for the conflict-detection agent."""

from __future__ import annotations

from backend_business.services.agent.runtime.agent_definition import (
    AgentDefinition,
    AgentDelegation,
)

def _create_delegated_prompt_builder():
    from backend_business.services.agent.agents.session_controller.graph_prompt_builders import (
        SessionControllerConflictDelegatePromptBuilder,
    )

    return SessionControllerConflictDelegatePromptBuilder()


def _resolve_application_service():
    from .service import conflict_detection_agent_service

    return conflict_detection_agent_service


def _resolve_service_tools(*, service=None, **_kwargs):
    return getattr(service, "tools", None)


def _build_runtime_context(*, context, invoke_request=None, **_kwargs):
    source = invoke_request or context
    return {
        "max_tool_call_rounds": source.get("max_tool_call_rounds")
        or context.get("max_tool_call_rounds")
    }


def _postprocess_result(*, result, **_kwargs):
    return {
        "status": "success",
        "tool_loop_reply": result.tool_loop_reply,
    }


CONFLICT_DETECTION_AGENT_DEFINITION = AgentDefinition(
    agent_type="conflict_detection",
    container_key="conflict_detection",
    label="Conflict Detection Agent",
    description="需求冲突检测与冲突解释",
    max_tool_call_rounds=6,
    prompt_builder_factory=_create_delegated_prompt_builder,
    tool_executor_factory=_resolve_service_tools,
    application_service_factory=_resolve_application_service,
    context_builder=_build_runtime_context,
    result_postprocessor=_postprocess_result,
    delegated_prompt_builder_factory=_create_delegated_prompt_builder,
    delegation=AgentDelegation(
        tool_name="invoke_conflict_detection",
        route_key="invoke_conflict",
        decision_mode="delegate_conflict",
        tool_description=(
            "将冲突检测任务委托给冲突检测 Agent 执行。"
            "适用于：检测两条或多条需求之间是否存在语义冲突。"
        ),
        tool_parameters={
            "type": "object",
            "properties": {
                "task_description": {
                    "type": "string",
                    "description": "具体的冲突检测任务描述，包含需要检测的需求 ID 或检测条件",
                },
            },
            "required": ["task_description"],
            "additionalProperties": False,
        },
        invoke_label="Invoke Conflict Detection",
        invoke_phase_label="委托冲突检测 Agent",
        invoke_task_prompt="将任务委托给冲突检测 Agent 执行。",
        runtime_label="Conflict Detection Runtime",
        runtime_phase_label="冲突检测 Agent 执行",
        runtime_task_prompt="执行冲突检测 Agent 的委托任务。",
        prompt_builder_kind="session_controller_conflict_delegate",
        runtime_node_key="conflict_detection_runtime",
        result_contract="conflict_detection",
        call_edge_label="call_conflict_detection",
        routing_keywords=(
            "检测冲突",
            "检查冲突",
            "是否冲突",
            "有没有冲突",
            "冲突吗",
            "conflict check",
        ),
    ),
    capability_policy={
        "policy_id": "session_controller::conflict_detection",
        "scope": "delegated_conflict",
    },
    quota_policy={
        "policy_id": "session_controller::conflict_detection::quota",
        "timeout_seconds": 180,
        "max_concurrent_runs": 4,
        "max_parallel_runs_per_scope": 1,
    },
    memory_policy={
        "scope": "container",
        "strict_memory_contract": True,
    },
    selectable_description="需求冲突检测与冲突解释",
    binding_scope="delegated_conflict",
)


STANDALONE_CONFLICT_DETECTION_AGENT_DEFINITION = AgentDefinition(
    agent_type="conflict_detection_agent",
    container_key="conflict_detection_agent",
    label="Conflict Detection Agent",
    description="冲突检测 Agent 独立 API runtime",
    max_tool_call_rounds=6,
    prompt_builder_factory=_create_delegated_prompt_builder,
    tool_executor_factory=_resolve_service_tools,
    context_builder=_build_runtime_context,
    result_postprocessor=_postprocess_result,
    capability_policy={
        "policy_id": "conflict_detection::runtime",
        "scope": "conflict_detection_agent",
    },
    quota_policy={
        "policy_id": "conflict_detection::runtime::quota",
        "max_rounds": 6,
        "timeout_seconds": 180,
        "max_concurrent_runs": 2,
        "max_parallel_runs_per_scope": 1,
    },
    memory_policy={
        "scope": "container",
        "strict_memory_contract": True,
    },
    selectable=False,
    binding_scope="conflict_detection_agent",
)
