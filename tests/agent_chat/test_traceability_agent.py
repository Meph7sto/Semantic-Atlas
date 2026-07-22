"""Contracts for the shared traceability tool and its delegated agent."""

from __future__ import annotations

import os

import pytest

os.environ["SKIP_DB_INIT"] = "1"

from backend_business.services.agent.agents.session_controller.prompt_builder import (
    SessionControllerPromptBuilder,
    infer_routing_hint,
)
from backend_business.services.agent.agents.session_controller.tools import (
    SessionControllerTools,
)
from backend_business.services.agent.agents.traceability_agent.definition import (
    TRACEABILITY_AGENT_DEFINITION,
)
from backend_business.services.agent.agents.traceability_agent.service import (
    TRACEABILITY_AGENT_TOOL_NAMES,
    TraceabilityAgentService,
)
from backend_business.services.agent.execution.subgraph_runner import (
    _build_invoke_runtime_context,
)
from backend_business.services.agent.runtime.agent_registry import AgentRegistry
from backend_business.services.agent.runtime.tool_capability import ToolCapabilityError


class _SharedRequirementTools:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict, dict]] = []

    @staticmethod
    def get_tools_list(context=None):
        _ = context
        return [
            {"type": "function", "function": {"name": "search_requirements"}},
            {"type": "function", "function": {"name": "list_requirements"}},
            {"type": "function", "function": {"name": "get_requirement_state"}},
            {
                "type": "function",
                "function": {"name": "update_requirement_content"},
            },
            {
                "type": "function",
                "function": {"name": "trace_requirement_relation"},
            },
        ]

    def execute(self, tool_name, arguments, context):
        self.calls.append((tool_name, dict(arguments), dict(context)))
        return {"tool_name": tool_name}


def test_traceability_agent_reuses_read_tools_and_cannot_update_requirements():
    shared_tools = _SharedRequirementTools()
    service = TraceabilityAgentService(shared_tools=shared_tools)

    assert [
        item["function"]["name"] for item in service.tools.get_tools_list()
    ] == [
        "search_requirements",
        "list_requirements",
        "get_requirement_state",
        "trace_requirement_relation",
    ]
    assert service.tools.execute(
        "trace_requirement_relation",
        {
            "high_level_requirement_id": "REQ-1",
            "low_level_requirement_id": "REQ-2",
        },
        {"project_id": "project-1"},
    ) == {"tool_name": "trace_requirement_relation"}
    assert shared_tools.calls[0][0] == "trace_requirement_relation"

    with pytest.raises(ToolCapabilityError, match="update_requirement_content"):
        service.tools.execute(
            "update_requirement_content",
            {"requirement_id": "REQ-2", "updates": {"title": "不应执行"}},
            {"project_id": "project-1"},
        )


def test_traceability_delegation_forwards_ordered_requirement_ids_and_keeps_allowlist():
    registry = AgentRegistry([TRACEABILITY_AGENT_DEFINITION])
    traceability_service = TraceabilityAgentService(shared_tools=_SharedRequirementTools())
    controller_tools = SessionControllerTools(
        requirements_service=object(),
        agent_registry=registry,
        agent_services={"traceability_agent": traceability_service},
    )
    context = {"project_id": "project-1", "delegated_max_tool_call_rounds": 3}

    invoke_result = controller_tools.execute(
        "invoke_traceability_agent",
        {
            "task_description": "追溯 REQ-1 到 REQ-2 的实现关系",
            "high_level_requirement_id": "REQ-1",
            "low_level_requirement_id": "REQ-2",
        },
        context,
    )
    runtime_context = _build_invoke_runtime_context(
        invoke_request=invoke_result,
        agent_registry=registry,
    )
    binding_spec = registry.build_runtime_binding_specs(
        services={"traceability_agent": traceability_service}
    )[0]

    assert invoke_result["delegated_agent"] == "traceability_agent"
    assert invoke_result["invoke_route_key"] == "invoke_traceability"
    assert invoke_result["high_level_requirement_id"] == "REQ-1"
    assert invoke_result["low_level_requirement_id"] == "REQ-2"
    assert context["dispatched_agents"] == ["traceability_agent"]
    assert runtime_context["high_level_requirement_id"] == "REQ-1"
    assert runtime_context["low_level_requirement_id"] == "REQ-2"
    assert set(binding_spec["capability_policy_json"]["tool_names"]) == set(
        TRACEABILITY_AGENT_TOOL_NAMES
    )
    assert controller_tools.resolve_runtime_tool_executor(
        container_key="traceability_agent"
    ) is traceability_service.tools


def test_session_controller_exposes_and_routes_traceability_agent():
    registry = AgentRegistry([TRACEABILITY_AGENT_DEFINITION])
    controller_tools = SessionControllerTools(
        requirements_service=object(),
        agent_registry=registry,
    )

    tool_names = [
        item["function"]["name"] for item in controller_tools.get_tools_list()
    ]
    prompt = SessionControllerPromptBuilder(agent_registry=registry).build_system_prompt(
        context={}
    )
    hint = infer_routing_hint(
        "请做需求追溯，确认顶层需求 REQ-1 是否由底层需求 REQ-2 实现",
        agent_registry=registry,
    )

    assert "invoke_traceability_agent" in tool_names
    assert "`invoke_traceability_agent`" in prompt
    assert "mode=`delegate_traceability`" in prompt
    assert hint == {
        "preferred_tool": "invoke_traceability_agent",
        "reason": "用户明确表达了“需求追溯”意图。",
    }
