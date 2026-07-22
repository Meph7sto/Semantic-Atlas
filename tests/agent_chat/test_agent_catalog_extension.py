"""End-to-end contracts for adding a delegated agent through the catalog."""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

os.environ["SKIP_DB_INIT"] = "1"

import pytest
from backend_business.services.agent.agents.session_controller.contracts import (
    SessionControllerDecisionMode,
)
from backend_business.services.agent.agents.session_controller.prompt_factory import (
    create_session_controller_prompt_builder,
)
from backend_business.services.agent.agents.session_controller.service import (
    SessionControllerService,
)
from backend_business.services.agent.agents.session_controller.tools import (
    SessionControllerTools,
)
from backend_business.services.agent.execution.subgraph_runner import (
    _build_invoke_runtime_context,
    _build_session_controller_invoke_decision,
    _build_subgraph_output,
)
from backend_business.services.agent.execution.tool_loop_runner import (
    ToolLoopResult,
)
from backend_business.services.agent.runtime.agent_definition import (
    AgentDefinition,
    AgentDelegation,
)
from backend_business.services.agent.runtime.agent_registry import AgentRegistry


class _CustomPromptBuilder:
    def build_system_prompt(self, *, context):
        return "custom-system"

    def build_user_message(self, *, user_message, context):
        return user_message

    def build_round_input_summary(self, *, round_index, messages, context):
        return {"round": round_index}


class _CustomTools:
    def get_tools_list(self, context=None):
        return []


def _custom_definition(*, agent_type: str = "custom_agent") -> AgentDefinition:
    return AgentDefinition(
        agent_type=agent_type,
        container_key=agent_type,
        label="Custom Agent",
        tool_executor_factory=lambda service=None: getattr(service, "tools", None),
        application_service_factory=lambda: SimpleNamespace(tools=_CustomTools()),
        context_builder=lambda context, invoke_request=None: {
            "custom_context": (invoke_request or context).get("custom_context", "ready")
        },
        result_postprocessor=lambda result: {
            "status": "success",
            "custom_output": result.tool_loop_reply,
        },
        delegated_prompt_builder_factory=_CustomPromptBuilder,
        delegation=AgentDelegation(
            tool_name=f"invoke_{agent_type}",
            route_key=f"invoke_{agent_type}",
            decision_mode="delegate_custom",
            tool_description="Delegate custom work",
            tool_parameters={
                "type": "object",
                "properties": {"task_description": {"type": "string"}},
                "required": ["task_description"],
            },
            invoke_label="Invoke Custom Agent",
            invoke_phase_label="Delegate custom agent",
            invoke_task_prompt="Delegate the custom task.",
            runtime_label="Custom Agent Runtime",
            runtime_phase_label="Run custom agent",
            runtime_task_prompt="Execute the custom task.",
            prompt_builder_kind="custom_delegate",
            runtime_node_key="custom_agent_runtime",
            result_contract="custom_result",
            call_edge_label="call_custom_agent",
        ),
    )


def test_custom_agent_catalog_drives_tool_prompt_context_result_and_mode():
    definition = _custom_definition()
    registry = AgentRegistry([definition])
    services = registry.build_application_services()
    tools = SessionControllerTools(
        requirements_service=object(),
        agent_registry=registry,
        agent_services=services,
    )

    context = {"project_id": "project-1", "delegated_max_tool_call_rounds": 3}
    invoke_result = tools.execute(
        "invoke_custom_agent",
        {"task_description": "do custom work"},
        context,
    )
    runtime_context = _build_invoke_runtime_context(
        invoke_request={**invoke_result, "custom_context": "from-request"},
        agent_registry=registry,
    )
    output = _build_subgraph_output(
        sg=SimpleNamespace(config_json={"agent_type": "custom_agent"}),
        result=ToolLoopResult(tool_loop_reply="custom-done", context={}, rounds=1),
        definition=definition,
    )
    decision = _build_session_controller_invoke_decision(
        invoke_subgraph=SimpleNamespace(subgraph_key="invoke_custom"),
        invoke_request=invoke_result,
        target_result=output,
        agent_registry=registry,
    )
    prompt_builder = create_session_controller_prompt_builder(
        prompt_builder_kind="custom_delegate",
        subgraph=None,
        scratchpad=None,
        context={},
        agent_registry=registry,
    )

    assert (
        tools.resolve_runtime_tool_executor(container_key="custom_agent")
        is services["custom_agent"].tools
    )
    assert runtime_context["custom_context"] == "from-request"
    assert output == {"status": "success", "custom_output": "custom-done"}
    assert decision["mode"] == "delegate_custom"
    assert decision["context"]["delegated_result"] == output
    assert decision["context"]["delegated_result_contract"] == "custom_result"
    assert SessionControllerDecisionMode("delegate_custom").value == "delegate_custom"
    assert isinstance(prompt_builder, _CustomPromptBuilder)


def test_catalog_result_postprocessor_must_return_serializable_mapping():
    definition = AgentDefinition(
        agent_type="invalid_result_agent",
        container_key="invalid_result_agent",
        label="Invalid Result Agent",
        result_postprocessor=lambda result: "silently lost",
    )

    with pytest.raises(
        TypeError,
        match="result_postprocessor must return a mapping",
    ):
        _build_subgraph_output(
            sg=SimpleNamespace(config_json={"agent_type": "invalid_result_agent"}),
            result=ToolLoopResult(tool_loop_reply="done", context={}, rounds=1),
            definition=definition,
        )


def test_catalog_rejects_ambiguous_delegation_modes():
    first = _custom_definition(agent_type="first_agent")
    second = _custom_definition(agent_type="second_agent")

    with pytest.raises(ValueError, match="duplicate delegation decision mode"):
        AgentRegistry([first, second])


def test_graph_mode_state_loader_discovers_custom_delegation_output_from_catalog():
    definition = _custom_definition()
    registry = AgentRegistry([definition])
    services = registry.build_application_services()
    tools = SessionControllerTools(
        requirements_service=object(),
        agent_registry=registry,
        agent_services=services,
    )
    decision = {
        "mode": "delegate_custom",
        "delegated_agent": "custom_agent",
        "tool_loop_reply": "custom complete",
        "dispatched_agents": ["custom_agent"],
        "context": {
            "delegated_result": {
                "status": "success",
                "custom_output": {"value": 42},
            },
            "delegated_result_contract": "custom_result",
        },
    }

    class _GraphService:
        def get_execution_graph(self, graph_id):
            assert graph_id == "graph-custom"
            return {
                "graph_id": graph_id,
                "meta_json": {
                    "scratchpad_snapshot": [
                        {
                            "entry_type": "stage_output",
                            "source_subgraph": "sg_invoke_custom_agent",
                            "container_key": "conductor",
                            "content": json.dumps(decision),
                        }
                    ]
                },
            }

    service = SessionControllerService(
        chat_storage=None,
        execution_graph_service=_GraphService(),
        requirements_service=object(),
        tools=tools,
        ai_proxy_client=object(),
        agent_registry=registry,
    )

    result, context, _assistant_reply = service._load_graph_mode_state(graph_id="graph-custom")

    assert result.mode.value == "delegate_custom"
    assert result.delegated_agent == "custom_agent"
    assert result.tool_loop_reply == "custom complete"
    assert context["dispatched_agents"] == ["custom_agent"]
    assert context["delegated_result"]["custom_output"] == {"value": 42}
    assert context["delegated_result_contract"] == "custom_result"
