"""Contract tests for the shared agent session graph store."""

from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import pytest  # noqa: E402
from backend_business.services.agent.agents.requirement_agent.definition import (  # noqa: E402
    REQUIREMENT_AGENT_DEFINITION,
)
from backend_business.services.agent.runtime.agent_definition import (  # noqa: E402
    AgentDefinition,
    AgentDelegation,
)
from backend_business.services.agent.runtime.agent_registry import (  # noqa: E402
    SESSION_CONTROLLER_DEFINITION,
    AgentRegistry,
    create_builtin_agent_registry,
)
from backend_business.services.agent.runtime.session_graph_store import (  # noqa: E402
    AgentSessionGraphStore,
)


class _FakeExecutionGraphService:
    def __init__(self) -> None:
        self.graphs: dict[str, dict] = {}
        self.deleted_graphs: list[str] = []

    def get_execution_graph(self, graph_id: str):
        graph = self.graphs.get(graph_id)
        return dict(graph) if graph else None

    def get_latest_runtime_graph_by_session(
        self,
        session_id: str,
        project_id: str | None = None,
        include_deleted: bool = False,
    ):
        graphs = [
            graph
            for graph in self.graphs.values()
            if graph.get("meta_json", {}).get("session_id") == session_id
            and (project_id is None or graph.get("project_id") == project_id)
        ]
        if not include_deleted:
            graphs = [graph for graph in graphs if graph.get("status") != "deleted"]
        graphs.sort(key=lambda graph: str(graph.get("created_at") or graph["graph_id"]))
        return dict(graphs[-1]) if graphs else None

    def list_runtime_graphs_by_session(
        self,
        session_id: str,
        project_id: str | None = None,
        include_deleted: bool = False,
    ):
        graphs = [
            graph
            for graph in self.graphs.values()
            if graph.get("meta_json", {}).get("session_id") == session_id
            and (project_id is None or graph.get("project_id") == project_id)
        ]
        if not include_deleted:
            graphs = [graph for graph in graphs if graph.get("status") != "deleted"]
        return [dict(graph) for graph in graphs]

    def get_graph_detail(self, graph_id: str):
        return {"graph": self.get_execution_graph(graph_id)}

    def delete_execution_graph(self, graph_id: str, updated_by: str = "") -> bool:
        self.deleted_graphs.append(graph_id)
        self.graphs[graph_id]["status"] = "deleted"
        self.graphs[graph_id]["updated_by"] = updated_by
        return True


class _FakeChatStorage:
    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.updated_sessions: list[dict] = []
        self.deleted_sessions: list[str] = []

    def get_or_create_session(
        self,
        user_id: str,
        project_id: str | None = None,
        agent_type: str | None = None,
    ):
        session = self.sessions.setdefault(
            "sess-1",
            {
                "session_id": "sess-1",
                "user_id": user_id,
                "project_id": project_id,
                "active_graph_id": None,
                "agent_type": agent_type,
            },
        )
        session.update(user_id=user_id, project_id=project_id, agent_type=agent_type)
        return dict(session)

    def create_session(
        self,
        user_id: str,
        project_id: str | None = None,
        title: str | None = None,
        prompt_payload_format: str | None = None,
        context_mode: str | None = None,
        agent_type: str | None = None,
    ):
        session = {
            "session_id": "sess-created",
            "user_id": user_id,
            "project_id": project_id,
            "title": title,
            "prompt_payload_format": prompt_payload_format,
            "context_mode": context_mode,
            "active_graph_id": None,
            "agent_type": agent_type,
        }
        self.sessions[session["session_id"]] = session
        return dict(session)

    def update_session(self, session_id: str, **kwargs):
        session = self.sessions.setdefault(
            session_id,
            {"session_id": session_id, "active_graph_id": None},
        )
        for key, value in kwargs.items():
            if value is not ... and value is not None:
                session[key] = value
        self.updated_sessions.append({"session_id": session_id, **kwargs})
        return True

    def list_sessions(
        self,
        user_id: str,
        project_id: str | None = None,
        limit: int = 100,
        agent_type: str | None = None,
    ):
        return [
            dict(session)
            for session in self.sessions.values()
            if session.get("user_id") == user_id
            and (project_id is None or session.get("project_id") == project_id)
            and (agent_type is None or session.get("agent_type") == agent_type)
        ][:limit]

    def _ensure_session_access(self, session_id: str, user_id: str):
        session = self.sessions[session_id]
        if session.get("user_id") != user_id:
            raise PermissionError("session forbidden")
        return dict(session)

    def list_messages(self, session_id: str, user_id: str, limit: int = 100):
        return [{"session_id": session_id, "user_id": user_id}][-limit:]

    def delete_session(self, session_id: str) -> bool:
        self.deleted_sessions.append(session_id)
        return self.sessions.pop(session_id, None) is not None


def _make_store():
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    store = AgentSessionGraphStore(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        agent_type="requirement_agent",
    )
    return store, chat_storage, graph_service


def test_agent_definition_validates_required_contract_fields():
    definition = AgentDefinition(
        agent_type="requirement_agent",
        container_key="requirement_agent",
        label="Requirement Agent",
    )

    assert definition.max_tool_call_rounds == 6

    with pytest.raises(ValueError, match="agent_type"):
        AgentDefinition(agent_type="", container_key="x", label="x")


class _NamedTools:
    def __init__(self, names: list[str]) -> None:
        self.names = names

    def get_tools_list(self, context=None):
        return [
            {
                "type": "function",
                "function": {
                    "name": name,
                    "parameters": {"type": "object", "properties": {}},
                },
            }
            for name in self.names
        ]


def test_agent_registry_generates_selectable_containers_and_binding_specs():
    registry = create_builtin_agent_registry()

    selectable = registry.selectable_containers()
    assert [item["container_key"] for item in selectable] == [
        "requirement_agent",
        "conflict_detection",
        "requirement_classification_agent",
    ]

    specs = registry.build_runtime_binding_specs(
        definitions=[
            SESSION_CONTROLLER_DEFINITION,
            registry.require_by_container_key("requirement_agent"),
        ],
        tool_executor_resolver=lambda definition: _NamedTools(
            [f"{definition.container_key}_tool"]
        ),
    )

    assert specs[0]["container_key"] == "conductor"
    assert specs[0]["capability_policy_json"]["tool_names"] == ["conductor_tool"]
    assert specs[1]["container_key"] == "requirement_agent"
    assert specs[1]["agent_type"] == "requirement_agent"
    assert specs[1]["capability_policy_json"]["scope"] == "delegated_requirement"
    assert specs[1]["quota_policy_json"]["max_rounds"] == 6


def test_agent_catalog_uses_package_definition_as_single_source():
    registry = create_builtin_agent_registry()

    assert registry.require_by_container_key("requirement_agent") is REQUIREMENT_AGENT_DEFINITION


def test_agent_catalog_drives_new_delegation_and_tool_factory_without_switches():
    tools = _NamedTools(["custom_tool"])
    definition = AgentDefinition(
        agent_type="custom_agent",
        container_key="custom_agent",
        label="Custom Agent",
        tool_executor_factory=lambda: tools,
        delegation=AgentDelegation(
            tool_name="invoke_custom_agent",
            route_key="invoke_custom",
            decision_mode="delegate_custom",
            tool_description="Delegate custom work",
            tool_parameters={
                "type": "object",
                "properties": {"task_description": {"type": "string"}},
                "required": ["task_description"],
            },
            invoke_label="Invoke Custom Agent",
            invoke_phase_label="Delegate custom agent",
            invoke_task_prompt="Delegate the task.",
            runtime_label="Custom Agent Runtime",
            runtime_phase_label="Run custom agent",
            runtime_task_prompt="Execute the delegated task.",
            prompt_builder_kind="custom_delegate",
            runtime_node_key="custom_agent_runtime",
            result_contract="custom_agent",
            call_edge_label="call_custom_agent",
        ),
    )
    registry = AgentRegistry([definition])

    assert registry.get_by_delegation_tool("invoke_custom_agent") is definition
    assert registry.get_by_route_key("invoke_custom") is definition
    assert registry.delegation_tool_to_agent() == {
        "invoke_custom_agent": "custom_agent"
    }
    specs = registry.build_runtime_binding_specs()
    assert specs[0]["capability_policy_json"]["tool_names"] == ["custom_tool"]


def test_hydrate_session_graph_restores_latest_runtime_graph():
    store, chat_storage, graph_service = _make_store()
    chat_storage.sessions["sess-1"] = {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "active_graph_id": "missing",
        "agent_type": "requirement_agent",
    }
    graph_service.graphs["graph-1"] = {
        "graph_id": "graph-1",
        "project_id": "p-1",
        "status": "succeeded",
        "created_at": "2026-01-01T00:00:00Z",
        "meta_json": {"session_id": "sess-1"},
    }

    hydrated = store.hydrate_session_graph(chat_storage.sessions["sess-1"])

    assert hydrated["active_graph_id"] == "graph-1"
    assert chat_storage.sessions["sess-1"]["active_graph_id"] == "graph-1"


def test_create_or_get_session_supports_agent_specific_update_policies():
    chat_storage = _FakeChatStorage()
    graph_service = _FakeExecutionGraphService()
    store = AgentSessionGraphStore(
        chat_storage=chat_storage,
        execution_graph_service=graph_service,
        agent_type="requirement_agent",
        prompt_payload_normalizer=lambda value: str(value).strip().lower(),
        create_or_get_prompt_update_policy="truthy",
        create_or_get_context_update_policy="allowed",
    )

    session = store.create_or_get_session(
        user_id="u-1",
        project_id="p-1",
        prompt_payload_format="",
        context_mode="invalid",
    )

    assert session["session_id"] == "sess-1"
    assert "prompt_payload_format" not in chat_storage.sessions["sess-1"]
    assert "context_mode" not in chat_storage.sessions["sess-1"]

    store.create_or_get_session(
        user_id="u-1",
        project_id="p-1",
        prompt_payload_format=" YAML ",
        context_mode="scratchpad",
    )

    assert chat_storage.sessions["sess-1"]["prompt_payload_format"] == "yaml"
    assert chat_storage.sessions["sess-1"]["context_mode"] == "scratchpad"


def test_resolve_session_graph_target_resumes_suspended_active_graph():
    store, _, graph_service = _make_store()
    graph_service.graphs["graph-1"] = {
        "graph_id": "graph-1",
        "project_id": "p-1",
        "status": "suspended",
        "meta_json": {"session_id": "sess-1"},
    }

    target = store.resolve_session_graph_target(
        session={"session_id": "sess-1", "project_id": "p-1", "active_graph_id": "graph-1"},
        project_id="p-1",
    )

    assert target == {"graph_id": "graph-1", "prev_graph_id": None}


def test_resolve_session_graph_target_chains_completed_graph_as_previous():
    store, _, graph_service = _make_store()
    graph_service.graphs["graph-1"] = {
        "graph_id": "graph-1",
        "project_id": "p-1",
        "status": "succeeded",
        "meta_json": {"session_id": "sess-1"},
    }

    target = store.resolve_session_graph_target(
        session={"session_id": "sess-1", "project_id": "p-1", "active_graph_id": "graph-1"},
        project_id="p-1",
    )

    assert target == {"graph_id": None, "prev_graph_id": "graph-1"}


def test_list_session_graph_chain_orders_by_prev_graph_id():
    store, chat_storage, graph_service = _make_store()
    chat_storage.sessions["sess-1"] = {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "active_graph_id": "graph-2",
        "agent_type": "requirement_agent",
    }
    graph_service.graphs["graph-2"] = {
        "graph_id": "graph-2",
        "project_id": "p-1",
        "status": "succeeded",
        "created_at": "2026-01-02T00:00:00Z",
        "meta_json": {"session_id": "sess-1", "prev_graph_id": "graph-1"},
    }
    graph_service.graphs["graph-1"] = {
        "graph_id": "graph-1",
        "project_id": "p-1",
        "status": "succeeded",
        "created_at": "2026-01-01T00:00:00Z",
        "meta_json": {"session_id": "sess-1", "prev_graph_id": None},
    }

    chain = store.list_session_graph_chain(session_id="sess-1", user_id="u-1")

    assert [item["graph"]["graph_id"] for item in chain["graphs"]] == ["graph-1", "graph-2"]


def test_delete_session_deletes_related_runtime_graphs_after_session_delete():
    store, chat_storage, graph_service = _make_store()
    chat_storage.sessions["sess-1"] = {
        "session_id": "sess-1",
        "user_id": "u-1",
        "project_id": "p-1",
        "active_graph_id": "graph-2",
        "agent_type": "requirement_agent",
    }
    for graph_id in ("graph-1", "graph-2"):
        graph_service.graphs[graph_id] = {
            "graph_id": graph_id,
            "project_id": "p-1",
            "status": "succeeded",
            "meta_json": {"session_id": "sess-1"},
        }

    deleted = store.delete_session(session_id="sess-1", user_id="u-1")

    assert deleted is True
    assert chat_storage.deleted_sessions == ["sess-1"]
    assert graph_service.deleted_graphs == ["graph-1", "graph-2"]
