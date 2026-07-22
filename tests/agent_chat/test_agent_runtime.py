from __future__ import annotations

import os
import sys
import threading

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
from backend_business.services.agent.runtime.state_contract import (
    SCRATCHPAD_STATE_VERSION,
)
from backend_business.services.agent.runtime.tool_capability import (
    ToolCapabilityError,
    ToolCapabilityExecutor,
)


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
        graph = self.graphs.get(graph_id)
        return {
            "graph": graph,
            "containers": [
                {
                    "graph_id": state_graph_id,
                    "container_key": container_key,
                }
                for (state_graph_id, container_key), _row in self.container_states.items()
                if state_graph_id == graph_id
            ],
        }

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


class _FailFirstRunningUpdateService(_FakeExecutionGraphService):
    def __init__(self) -> None:
        super().__init__()
        self.fail_next_running_update = True

    def update_agent_run(self, run_id, **kwargs):
        if kwargs.get("status") == "running" and self.fail_next_running_update:
            self.fail_next_running_update = False
            raise RuntimeError("running persistence unavailable")
        return super().update_agent_run(run_id, **kwargs)


class _LifecycleRecordingService(_FakeExecutionGraphService):
    def __init__(self) -> None:
        super().__init__()
        self.status_updates: dict[str, list[str]] = {}
        self.nonterminal_status_persisted = threading.Event()

    def update_agent_run(self, run_id, **kwargs):
        status = kwargs.get("status")
        row = super().update_agent_run(run_id, **kwargs)
        if status is not None:
            self.status_updates.setdefault(run_id, []).append(status)
            if status in {"cancelling", "timing_out"}:
                self.nonterminal_status_persisted.set()
        return row


class _PausedFinalizationRuntime(LocalAgentRuntime):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.worker_joined = threading.Event()
        self.allow_finalization = threading.Event()

    def _supervise_worker(self, agent_run_id, state, worker_thread) -> None:
        worker_thread.join()
        self.worker_joined.set()
        self.allow_finalization.wait(timeout=5.0)
        super()._supervise_worker(agent_run_id, state, worker_thread)


class _PausedFirstLeaseReleaseRuntime(LocalAgentRuntime):
    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self.release_entered = threading.Event()
        self.allow_release = threading.Event()
        self._paused_first_release = False

    def _release_policy_lease(self, agent_run_id, state) -> None:
        if not self._paused_first_release and state.worker_finished:
            self._paused_first_release = True
            self.release_entered.set()
            self.allow_release.wait(timeout=5.0)
        super()._release_policy_lease(agent_run_id, state)


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
        quota_policy={"policy_id": "quota-default", "timeout_seconds": 5},
        memory_policy={
            "scope": "container",
            "strict_memory_contract": True,
        },
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


def test_local_agent_runtime_releases_quota_when_running_persistence_fails():
    service = _FailFirstRunningUpdateService()
    runtime = LocalAgentRuntime(
        runtime_id="rt-local",
        execution_graph_service=service,
    )
    runner_calls: list[str] = []
    quota_policy = {
        "policy_id": "quota-startup",
        "max_concurrent_runs": 1,
    }

    failed_run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-1",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={"runner": lambda: runner_calls.append("failed-run")},
            quota_policy_id="quota-startup",
            quota_policy=quota_policy,
        )
    )

    assert list(runtime.stream(failed_run_id)) == []
    failed_result = runtime.await_result(failed_run_id)
    failed_state = runtime._get_state(failed_run_id)

    assert failed_result.status == "failed"
    assert failed_result.error_code == "RuntimeError"
    assert failed_result.error_message == "running persistence unavailable"
    assert service.get_agent_run(failed_run_id)["status"] == "failed"
    assert runner_calls == []
    with failed_state.lock:
        assert failed_state.running is False
        assert failed_state.worker_thread is None
        assert failed_state.supervisor_thread is None
        assert failed_state.policy_lease is None

    next_run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-2",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={
                "runner": lambda: AgentRunResult(status="succeeded")
            },
            quota_policy_id="quota-startup",
            quota_policy=quota_policy,
        )
    )
    assert runtime.await_result(next_run_id).status == "succeeded"


def test_local_agent_runtime_recovers_when_supervisor_thread_start_fails(
    monkeypatch,
):
    runtime = LocalAgentRuntime(runtime_id="rt-local")
    original_start = threading.Thread.start
    failed_supervisor_start = False
    runner_calls: list[str] = []
    quota_policy = {
        "policy_id": "quota-startup",
        "max_concurrent_runs": 1,
    }

    def _fail_first_supervisor_start(thread):
        nonlocal failed_supervisor_start
        if (
            thread.name.startswith("run-supervisor-")
            and not thread.name.startswith("run-supervisor-recovery-")
            and not failed_supervisor_start
        ):
            failed_supervisor_start = True
            raise RuntimeError("supervisor thread unavailable")
        return original_start(thread)

    monkeypatch.setattr(threading.Thread, "start", _fail_first_supervisor_start)
    failed_run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-1",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={"runner": lambda: runner_calls.append("started")},
            quota_policy_id="quota-startup",
            quota_policy=quota_policy,
        )
    )

    failed_result = runtime.await_result(failed_run_id)

    assert failed_supervisor_start is True
    assert runner_calls == ["started"]
    assert failed_result.status == "failed"
    assert failed_result.error_message == "supervisor thread unavailable"

    next_run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-2",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={
                "runner": lambda: AgentRunResult(status="succeeded")
            },
            quota_policy_id="quota-startup",
            quota_policy=quota_policy,
        )
    )
    assert runtime.await_result(next_run_id).status == "succeeded"


def test_local_agent_runtime_streams_events_before_runner_completes():
    runtime = LocalAgentRuntime(runtime_id="rt-local")
    runner_release = threading.Event()
    event_observed = threading.Event()
    streamed_events: list[dict] = []

    def _blocking_runner():
        yield {"event": "tool_progress", "data": {"phase": "started"}}
        runner_release.wait(timeout=5.0)
        return AgentRunResult(status="succeeded")

    run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-1",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={"runner": _blocking_runner},
        )
    )

    def _consume_stream() -> None:
        for event in runtime.stream(run_id):
            streamed_events.append(event)
            event_observed.set()

    stream_thread = threading.Thread(target=_consume_stream, daemon=True)
    stream_thread.start()

    assert event_observed.wait(timeout=1.0) is True
    assert streamed_events == [
        {"event": "tool_progress", "data": {"phase": "started"}}
    ]
    assert stream_thread.is_alive() is True

    runner_release.set()
    stream_thread.join(timeout=1.0)
    assert stream_thread.is_alive() is False
    assert runtime.await_result(run_id).status == "succeeded"


def test_local_agent_runtime_enforces_strict_memory_contract():
    service = _FakeExecutionGraphService()
    runtime = LocalAgentRuntime(runtime_id="rt-local", execution_graph_service=service)

    request = RunRequest(
        graph_id="g-1",
        subgraph_id="sg-1",
        container_key="requirement_agent",
        agent_type="requirement_agent",
        input_payload={"runner": lambda: AgentRunResult(status="succeeded")},
        memory_scope_ref="g-1:conductor",
        tool_policy_id="policy-tools",
        quota_policy_id="quota-default",
        quota_policy={"policy_id": "quota-default", "timeout_seconds": 5},
        memory_policy={
            "scope": "container",
            "strict_memory_contract": True,
        },
    )

    run_id = runtime.submit(request)
    result = runtime.await_result(run_id)

    assert result.status == "failed"
    assert result.error_code == "memory_scope_violation"
    persisted = service.get_agent_run(run_id)
    assert persisted["status"] == "failed"
    assert persisted["error_code"] == "memory_scope_violation"


def test_local_agent_runtime_enforces_quota_timeout():
    service = _FakeExecutionGraphService()
    runtime = LocalAgentRuntime(runtime_id="rt-local", execution_graph_service=service)

    def _slow_runner():
        import time

        time.sleep(0.2)
        return AgentRunResult(status="succeeded")

    request = RunRequest(
        graph_id="g-1",
        subgraph_id="sg-1",
        container_key="requirement_agent",
        agent_type="requirement_agent",
        input_payload={"runner": _slow_runner},
        memory_scope_ref="g-1:requirement_agent",
        tool_policy_id="policy-tools",
        quota_policy_id="quota-default",
        quota_policy={"policy_id": "quota-default", "timeout_seconds": 0.05},
        memory_policy={"scope": "container", "strict_memory_contract": True},
    )

    run_id = runtime.submit(request)
    result = runtime.await_result(run_id)

    assert result.status == "timed_out"
    assert result.error_code == "timed_out"
    persisted = service.get_agent_run(run_id)
    assert persisted["status"] == "timed_out"
    assert persisted["error_code"] == "timed_out"


def test_local_agent_runtime_timeout_persists_status_and_holds_quota():
    service = _LifecycleRecordingService()
    runtime = LocalAgentRuntime(
        runtime_id="rt-local",
        execution_graph_service=service,
    )
    runner_started = threading.Event()
    runner_release = threading.Event()
    runtime_context: dict = {}
    first_result: dict[str, AgentRunResult] = {}
    quota_policy = {
        "policy_id": "quota-default",
        "timeout_seconds": 0.05,
        "max_concurrent_runs": 1,
    }

    def _non_cooperative_runner():
        runner_started.set()
        runner_release.wait(timeout=5.0)
        return AgentRunResult(status="succeeded")

    first_run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-1",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={
                "runner": _non_cooperative_runner,
                "runtime_context": runtime_context,
            },
            quota_policy_id="quota-default",
            quota_policy=quota_policy,
        )
    )
    first_await_thread = threading.Thread(
        target=lambda: first_result.setdefault(
            "result", runtime.await_result(first_run_id)
        ),
        daemon=True,
    )
    first_await_thread.start()

    assert runner_started.wait(timeout=1.0) is True
    assert runtime_context["_runtime_cancel_event"].wait(timeout=1.0) is True
    assert service.nonterminal_status_persisted.wait(timeout=1.0) is True
    assert first_await_thread.is_alive() is True
    assert service.get_agent_run(first_run_id)["status"] == "timing_out"
    assert service.status_updates[first_run_id] == ["running", "timing_out"]

    second_run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-2",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={"runner": lambda: AgentRunResult(status="succeeded")},
            quota_policy_id="quota-default",
            quota_policy=quota_policy,
        )
    )
    second_result = runtime.await_result(second_run_id)

    assert second_result.status == "failed"
    assert second_result.error_code == "quota_exceeded"

    runner_release.set()
    first_await_thread.join(timeout=1.0)
    assert first_await_thread.is_alive() is False
    assert first_result["result"].status == "timed_out"
    assert service.get_agent_run(first_run_id)["status"] == "timed_out"
    assert service.status_updates[first_run_id] == [
        "running",
        "timing_out",
        "timed_out",
    ]

    third_run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-3",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={"runner": lambda: AgentRunResult(status="succeeded")},
            quota_policy_id="quota-default",
            quota_policy={**quota_policy, "timeout_seconds": 1},
        )
    )
    assert runtime.await_result(third_run_id).status == "succeeded"


def test_local_agent_runtime_cancel_persists_status_until_worker_exit():
    service = _LifecycleRecordingService()
    runtime = LocalAgentRuntime(
        runtime_id="rt-local",
        execution_graph_service=service,
    )
    runner_started = threading.Event()
    cancel_observed = threading.Event()
    worker_release = threading.Event()
    runtime_context: dict = {}
    result_holder: dict[str, AgentRunResult] = {}

    def _cooperative_runner():
        runner_started.set()
        runtime_context["_runtime_cancel_event"].wait(timeout=5.0)
        cancel_observed.set()
        worker_release.wait(timeout=5.0)
        return AgentRunResult(status="succeeded")

    run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-1",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={
                "runner": _cooperative_runner,
                "runtime_context": runtime_context,
            },
        )
    )
    await_thread = threading.Thread(
        target=lambda: result_holder.setdefault("result", runtime.await_result(run_id)),
        daemon=True,
    )
    await_thread.start()
    assert runner_started.wait(timeout=1.0) is True

    runtime.cancel(run_id)
    assert cancel_observed.wait(timeout=1.0) is True
    assert await_thread.is_alive() is True
    assert service.get_agent_run(run_id)["status"] == "cancelling"
    assert service.status_updates[run_id] == ["running", "cancelling"]

    worker_release.set()
    await_thread.join(timeout=1.0)
    assert await_thread.is_alive() is False
    assert result_holder["result"].status == "cancelled"
    assert service.get_agent_run(run_id)["status"] == "cancelled"
    assert service.status_updates[run_id] == ["running", "cancelling", "cancelled"]


def test_local_agent_runtime_cancel_before_start_does_not_invoke_runner():
    runtime = LocalAgentRuntime(runtime_id="rt-local")
    calls: list[str] = []

    run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-1",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={"runner": lambda: calls.append("runner")},
        )
    )

    runtime.cancel(run_id)

    assert runtime.await_result(run_id).status == "cancelled"
    assert list(runtime.stream(run_id)) == []
    assert calls == []


def test_local_agent_runtime_rejects_termination_after_worker_finishes():
    runtime = _PausedFinalizationRuntime(runtime_id="rt-local")
    result_holder: dict[str, AgentRunResult] = {}
    run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-1",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={"runner": lambda: AgentRunResult(status="succeeded")},
        )
    )
    await_thread = threading.Thread(
        target=lambda: result_holder.setdefault("result", runtime.await_result(run_id)),
        daemon=True,
    )
    await_thread.start()

    assert runtime.worker_joined.wait(timeout=1.0) is True
    state = runtime._get_state(run_id)
    runtime.cancel(run_id)
    runtime._request_timeout(run_id, state, state.supervisor)

    with state.lock:
        assert state.termination_request is None
        assert state.supervisor.cancel_event.is_set() is False

    runtime.allow_finalization.set()
    await_thread.join(timeout=1.0)
    assert await_thread.is_alive() is False
    assert result_holder["result"].status == "succeeded"


def test_local_agent_runtime_resume_waits_for_previous_lease_cleanup():
    runtime = _PausedFirstLeaseReleaseRuntime(runtime_id="rt-local")
    resume_call_entered = threading.Event()
    resumed_runner_started = threading.Event()
    resumed_runner_release = threading.Event()
    initial_result: dict[str, AgentRunResult] = {}
    resume_result: dict[str, AgentRunResult] = {}
    quota_policy = {
        "policy_id": "quota-default",
        "max_concurrent_runs": 1,
        "timeout_seconds": 5,
    }

    def _resume_runner(_user_input):
        resumed_runner_started.set()
        resumed_runner_release.wait(timeout=5.0)
        return AgentRunResult(status="succeeded")

    run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-1",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={
                "runner": lambda: AgentRunResult(status="waiting_user"),
                "resume_runner": _resume_runner,
            },
            quota_policy_id="quota-default",
            quota_policy=quota_policy,
        )
    )
    initial_await_thread = threading.Thread(
        target=lambda: initial_result.setdefault(
            "result", runtime.await_result(run_id)
        ),
        daemon=True,
    )
    initial_await_thread.start()
    assert runtime.release_entered.wait(timeout=1.0) is True

    def _resume() -> None:
        resume_call_entered.set()
        resume_result["result"] = runtime.resume(run_id, {"approved": True})

    resume_thread = threading.Thread(target=_resume, daemon=True)
    resume_thread.start()
    assert resume_call_entered.wait(timeout=1.0) is True
    assert resumed_runner_started.is_set() is False
    assert resume_thread.is_alive() is True

    runtime.allow_release.set()
    assert resumed_runner_started.wait(timeout=1.0) is True
    initial_await_thread.join(timeout=1.0)
    assert initial_await_thread.is_alive() is False
    assert initial_result["result"].status == "waiting_user"

    competing_run_id = runtime.submit(
        RunRequest(
            graph_id="g-1",
            subgraph_id="sg-2",
            container_key="requirement_agent",
            agent_type="requirement_agent",
            input_payload={"runner": lambda: AgentRunResult(status="succeeded")},
            quota_policy_id="quota-default",
            quota_policy=quota_policy,
        )
    )
    competing_result = runtime.await_result(competing_run_id)
    assert competing_result.status == "failed"
    assert competing_result.error_code == "quota_exceeded"

    resumed_runner_release.set()
    resume_thread.join(timeout=1.0)
    assert resume_thread.is_alive() is False
    assert resume_result["result"].status == "succeeded"


def test_local_agent_runtime_enforces_max_concurrent_runs_per_policy():
    service = _FakeExecutionGraphService()
    runtime = LocalAgentRuntime(runtime_id="rt-local", execution_graph_service=service)
    started = []
    release = __import__("threading").Event()

    def _blocking_runner():
        started.append("started")
        release.wait(timeout=1.0)
        return AgentRunResult(status="succeeded")

    request_one = RunRequest(
        graph_id="g-1",
        subgraph_id="sg-1",
        container_key="requirement_agent",
        agent_type="requirement_agent",
        input_payload={"runner": _blocking_runner},
        memory_scope_ref="g-1:requirement_agent",
        tool_policy_id="policy-tools",
        quota_policy_id="quota-default",
        quota_policy={"policy_id": "quota-default", "timeout_seconds": 1, "max_concurrent_runs": 1},
        memory_policy={"scope": "container", "strict_memory_contract": True},
    )
    request_two = RunRequest(
        graph_id="g-1",
        subgraph_id="sg-2",
        container_key="requirement_agent",
        agent_type="requirement_agent",
        input_payload={"runner": lambda: AgentRunResult(status="succeeded")},
        memory_scope_ref="g-1:requirement_agent",
        tool_policy_id="policy-tools",
        quota_policy_id="quota-default",
        quota_policy={"policy_id": "quota-default", "timeout_seconds": 1, "max_concurrent_runs": 1},
        memory_policy={"scope": "container", "strict_memory_contract": True},
    )

    run_id_one = runtime.submit(request_one)
    thread = __import__("threading").Thread(target=lambda: list(runtime.stream(run_id_one)))
    thread.start()
    while not started:
        pass

    run_id_two = runtime.submit(request_two)
    result_two = runtime.await_result(run_id_two)
    release.set()
    thread.join(timeout=1.0)

    assert result_two.status == "failed"
    assert result_two.error_code == "quota_exceeded"
    assert service.get_agent_run(run_id_two)["error_code"] == "quota_exceeded"


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


def test_scratchpad_service_migrates_legacy_graph_meta_snapshot_once():
    service = _FakeExecutionGraphService()
    service.graphs["g-1"]["meta_json"] = {
        "scratchpad_snapshot": [
            {
                "entry_type": "note",
                "content": "legacy only",
                "container_key": "conductor",
            }
        ]
    }
    scratchpad_service = ScratchpadService(execution_graph_service=service)

    restored = scratchpad_service.load("g-1")

    assert any(
        entry.get("entry_type") == "note"
        and entry.get("content") == "legacy only"
        and entry.get("container_key") == "conductor"
        for entry in restored.snapshot_all()
    )
    assert any(
        entry.get("entry_type") == "note"
        and entry.get("content") == "legacy only"
        and entry.get("container_key") == "conductor"
        for entry in service.container_states[("g-1", "conductor")]["state_json"]["scratchpad_snapshot"]
    )
    assert service.graphs["g-1"]["meta_json"]["scratchpad_state_version"] == (
        SCRATCHPAD_STATE_VERSION
    )


def test_scratchpad_service_clears_stale_container_state_entries():
    service = _FakeExecutionGraphService()
    scratchpad_service = ScratchpadService(execution_graph_service=service)

    initial_pad = Scratchpad()
    initial_pad.for_container("requirement_agent").write(
        "note",
        "stale note",
        source_subgraph="worker",
    )
    scratchpad_service.save("g-1", initial_pad, updated_by="tester")

    replacement_pad = Scratchpad()
    replacement_pad.for_container("conductor").write(
        "note",
        "fresh reply",
        source_subgraph="reply",
    )
    scratchpad_service.save("g-1", replacement_pad, updated_by="tester")

    restored = scratchpad_service.load("g-1")
    snapshot = restored.snapshot_all()

    assert not any(
        entry.get("container_key") == "requirement_agent"
        for entry in snapshot
    )
    assert any(
        entry.get("container_key") == "conductor"
        and entry.get("content") == "fresh reply"
        for entry in snapshot
    )
    assert service.container_states[("g-1", "requirement_agent")]["state_json"][
        "scratchpad_snapshot"
    ] == []


class _FakeTools:
    def __init__(self) -> None:
        self.executed: list[str] = []

    def get_tools_list(self, context=None):
        _ = context
        return [
            {"type": "function", "function": {"name": "allowed_tool"}},
            {"type": "function", "function": {"name": "blocked_tool"}},
        ]

    def execute(self, tool_name, arguments, context):
        _ = arguments, context
        self.executed.append(tool_name)
        return {"tool_name": tool_name}


def test_tool_capability_executor_blocks_unauthorized_tool_calls():
    wrapped = ToolCapabilityExecutor(
        tool_executor=_FakeTools(),
        allowed_tool_names={"allowed_tool"},
        policy_id="policy-test",
    )

    assert wrapped.execute("allowed_tool", {}, {}) == {"tool_name": "allowed_tool"}

    try:
        wrapped.execute("blocked_tool", {}, {})
        raise AssertionError("blocked tool should not be allowed")
    except ToolCapabilityError as exc:
        assert exc.tool_name == "blocked_tool"


def test_tool_capability_executor_discovers_allowed_tools_from_delegate():
    wrapped = ToolCapabilityExecutor(tool_executor=_FakeTools())

    tools = wrapped.get_tools_list(context={})

    assert len(tools) == 2
    assert {tool["function"]["name"] for tool in tools} == {
        "allowed_tool",
        "blocked_tool",
    }


def _runtime_runner(*, events, result):
    def _run():
        for event in events:
            yield event
        return result

    return _run()
