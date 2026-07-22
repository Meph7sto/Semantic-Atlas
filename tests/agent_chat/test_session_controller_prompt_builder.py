"""Catalog-driven SessionController prompt contract tests."""

from __future__ import annotations

from dataclasses import replace

from backend_business.services.agent.agents.session_controller.prompt_builder import (
    SessionControllerPromptBuilder,
    infer_routing_hint,
)
from backend_business.services.agent.runtime.agent_definition import (
    AgentDefinition,
    AgentDelegation,
)
from backend_business.services.agent.runtime.agent_registry import AgentRegistry


def _custom_definition() -> AgentDefinition:
    return AgentDefinition(
        agent_type="custom_agent",
        container_key="custom_agent",
        label="Custom Agent",
        delegation=AgentDelegation(
            tool_name="invoke_custom_agent",
            route_key="invoke_custom",
            decision_mode="delegate_custom",
            tool_description="将自定义任务委托给 Custom Agent。",
            tool_parameters={
                "type": "object",
                "properties": {"task_description": {"type": "string"}},
            },
            invoke_label="Invoke Custom Agent",
            invoke_phase_label="Delegate Custom Agent",
            invoke_task_prompt="Delegate the custom task.",
            runtime_label="Custom Agent Runtime",
            runtime_phase_label="Run Custom Agent",
            runtime_task_prompt="Execute the custom task.",
            prompt_builder_kind="custom_delegate",
            runtime_node_key="custom_agent_runtime",
            result_contract="custom_agent",
            call_edge_label="call_custom_agent",
        ),
    )


def test_prompt_protocol_comes_from_injected_catalog() -> None:
    builder = SessionControllerPromptBuilder(
        agent_registry=AgentRegistry([_custom_definition()]),
    )

    prompt = builder.build_system_prompt(context={})

    assert "`invoke_custom_agent`" in prompt
    assert "mode=`delegate_custom`" in prompt
    assert "delegated_agent=`custom_agent`" in prompt
    assert '"mode":"direct_reply|clarify|browse|delegate_custom|approval_pending|error"' in prompt
    assert '"delegated_agent":"custom_agent|null"' in prompt
    assert "invoke_requirement_agent" not in prompt
    assert "delegate_requirement" not in prompt


def test_default_prompt_preserves_builtin_delegation_contract() -> None:
    prompt = SessionControllerPromptBuilder().build_system_prompt(context={})

    assert "`invoke_requirement_agent`" in prompt
    assert "`invoke_conflict_detection`" in prompt
    assert "`invoke_requirement_classification_agent`" in prompt
    assert "mode=`delegate_requirement`" in prompt
    assert "mode=`delegate_conflict`" in prompt
    assert "mode=`delegate_classification`" in prompt
    assert "delegated_agent=`requirement_agent`" in prompt
    assert "delegated_agent=`conflict_detection`" in prompt
    assert "delegated_agent=`requirement_classification_agent`" in prompt


def test_routing_hint_resolves_tool_name_from_catalog_metadata() -> None:
    definition = _custom_definition()
    delegation = definition.delegation
    assert delegation is not None
    custom_writer = replace(
        definition,
        delegation=replace(
            delegation,
            accepts_requirement_id=True,
            include_prompt_preferences=True,
        ),
    )

    hint = infer_routing_hint(
        "把这个需求的优先级改成高",
        agent_registry=AgentRegistry([custom_writer]),
    )

    assert hint is not None
    assert hint["preferred_tool"] == "invoke_custom_agent"
