from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.runtime.agent_runtime import (
    AgentRunResult,
    AgentRuntimeRegistry,
    LocalAgentRuntime,
    RunRequest,
)
from backend_business.services.agent.runtime.scratchpad import Scratchpad
from backend_business.services.agent.runtime.scratchpad_service import ScratchpadService


class _FakeExecutionGraphService:
    def __init__(self) -> None:
        self.graphs: dict[str, dict] = {
            "g-1": {"graph_id": "g-1", "meta_json": {}},
        }
        self.runtime_bindings: list[dict] = []
        self.agent_runs: dict[str, dict] = {}
        self.container_states: dict[tuple[str, str], dict] = {}

    def patch_graph_meta(self, graph_id, meta_patch, status=None, updated_by=""):
        graph = self.graphs.setdefault(graph_id, {"graph_id": graph_id, "meta_json": {}})
        meta = dict(graph.get("meta_json") or {})
        meta.update(meta_patch or {})
        graph["meta_json"] = meta
        if status is not None:
            graph["status"] = status
        return graph

    def get_execution_graph(self, graph_id):
        return self.graphs.get(graph_id)

    def get_graph_detail(self, graph_id):
        return {"graph": self.graphs.get(graph_id)}

    def list_agent_runtime_bindings(
        self,
        *,
        container_key=None,
        agent_type=None,
        runtime_profile=None,
        enabled_only=True,
    ):
        rows = list(self.runtime_bindings)
        if container_key is not None:
            rows = [row for row in rows if row.get("container_key") == container_key]
        if agent_type is not None:
            rows = [row for row in rows if row.get("agent_type") == agent_type]
        if runtime_profile is not None:
            rows = [row for row in rows if row.get("runtime_profile") == runtime_profile]
        if enabled_only:
            rows = [row for row in rows if row.get("enabled", True)]
        return rows

    def create_agent_run(self, **kwargs):
        row = dict(kwargs)
        run_id = row["run_id"]
        self.agent_runs[run_id] = row
        return row

    def update_agent_run(self, run_id, **kwargs):
        row = self.agent_runs[run_id]
        row.update({key: value for key, value in kwargs.items() if value is not None})
        return row

    def get_agent_run(self, run_id):
        return self.agent_runs.get(run_id)

    def upsert_container_state(self, *, graph_id, container_key, state_json, updated_by=""):
        row = {
            "graph_id": graph_id,
            "container_key": container_key,
            "state_json": state_json,
            "updated_by": updated_by,
        }
        self.container_states[(graph_id, container_key)] = row
        return row

    def list_container_states(self, graph_id):
        return [
            row for (state_graph_id, _container_key), row in self.container_states.items()
            if state_graph_id == graph_id
        ]


def test_local_agent_runtime_persists_run_lifecycle():
    service = _FakeExecutionGraphService()
    runtime = LocalAgentRuntime(runtime_id="rt-local", execution_graph_service=service)

    request = RunRequest(
        graph_id="g-1",
        subgraph_id="sg-1",
        container_key="requirement_agent",
        agent_type="requirement_agent",
        input_payload={
            "runner": lambda: _runtime_runner(
                events=[{"event": "tool_result", "data": {"ok": True}}],
                result=AgentRunResult(
                    status="succeeded",
                    return_payload={"reply": "done"},
                    usage={"total_tokens": 99},
                ),
            ),
            "input_ref": {"task": "inspect"},
        },
        memory_scope_ref="g-1:requirement_agent",
        tool_policy_id="policy-tools",
        quota_policy_id="quota-default",
    )

    run_id = runtime.submit(request)
    events = list(runtime.stream(run_id))
    result = runtime.await_result(run_id)

    assert events == [{"event": "tool_result", "data": {"ok": True}}]
    assert result.status == "succeeded"
    persisted = service.get_agent_run(run_id)
    assert persisted["status"] == "succeeded"
    assert persisted["output_ref"] == {"reply": "done"}
    assert persisted["usage_json"] == {"total_tokens": 99}


def test_agent_runtime_registry_falls_back_to_local_runtime():
    service = _FakeExecutionGraphService()
    registry = AgentRuntimeRegistry(execution_graph_service=service)

    binding = registry.resolve(
        container_key="requirement_agent",
        agent_type="requirement_agent",
        runtime_profile="default",
    )

    assert binding.runtime_id == "local::default"
    assert isinstance(binding.runtime, LocalAgentRuntime)
    assert binding.quota_policy["runtime_profile"] == "default"


def test_scratchpad_service_uses_container_state_store_with_graph_meta_fallback():
    service = _FakeExecutionGraphService()
    scratchpad_service = ScratchpadService(execution_graph_service=service)

    pad = Scratchpad()
    requirement_pad = pad.for_container("requirement_agent")
    requirement_pad.write("note", "secret note", source_subgraph="worker")
    conductor_pad = pad.for_container("conductor")
    conductor_pad.write("note", "public reply", source_subgraph="reply")

    scratchpad_service.save_snapshot(
        "g-1",
        pad.snapshot_all(),
        updated_by="tester",
    )

    restored = scratchpad_service.load("g-1")

    assert service.container_states[("g-1", "requirement_agent")]["state_json"]["scratchpad_snapshot"]
    assert service.container_states[("g-1", "conductor")]["state_json"]["scratchpad_snapshot"]
    assert any(
        entry.get("content") == "secret note"
        for entry in restored.snapshot_all()
    )
    assert service.graphs["g-1"]["meta_json"]["scratchpad_snapshot"]


def _runtime_runner(*, events, result):
    def _run():
        for event in events:
            yield event
        return result

    return _run()
