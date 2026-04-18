"""Agent runtime abstractions and in-process fallback runtime."""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass, field
import inspect
import threading
import uuid
from typing import Any, Protocol


@dataclass(frozen=True)
class RunRequest:
    graph_id: str
    subgraph_id: str | None
    container_key: str
    agent_type: str
    input_payload: Any
    memory_scope_ref: str | None = None
    tool_policy_id: str | None = None
    quota_policy_id: str | None = None
    parent_run_id: str | None = None
    resume_token: str | None = None


@dataclass(frozen=True)
class AgentRunResult:
    status: str
    return_payload: Any = None
    memory_delta_ref: str | None = None
    error_code: str | None = None
    error_message: str | None = None
    usage: dict[str, Any] | None = None
    suspend_info: dict[str, Any] | None = None


class AgentRuntime(Protocol):
    def submit(self, run_request: RunRequest) -> str:
        ...

    def stream(self, agent_run_id: str) -> Generator[dict[str, Any], None, None]:
        ...

    def await_result(self, agent_run_id: str) -> AgentRunResult:
        ...

    def resume(self, agent_run_id: str, user_input: Any) -> AgentRunResult:
        ...

    def cancel(self, agent_run_id: str) -> None:
        ...


@dataclass(frozen=True)
class RuntimeBinding:
    runtime_id: str
    runtime: AgentRuntime
    implementation_type: str
    endpoint: str | None = None
    capability_policy: dict[str, Any] = field(default_factory=dict)
    quota_policy: dict[str, Any] = field(default_factory=dict)
    memory_policy: dict[str, Any] = field(default_factory=dict)


@dataclass
class _InMemoryRunState:
    request: RunRequest
    events: list[dict[str, Any]] = field(default_factory=list)
    result: AgentRunResult | None = None
    executed: bool = False
    running: bool = False
    cancelled: bool = False
    cancel_event: threading.Event = field(default_factory=threading.Event)
    completion_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)


class LocalAgentRuntime:
    """In-process runtime that executes the supplied runner closure."""

    def __init__(
        self,
        *,
        runtime_id: str = "local::default",
        execution_graph_service: Any | None = None,
    ) -> None:
        self.runtime_id = runtime_id
        self._service = execution_graph_service
        self._runs: dict[str, _InMemoryRunState] = {}
        self._lock = threading.RLock()

    def submit(self, run_request: RunRequest) -> str:
        run_id = str(uuid.uuid4())
        state = _InMemoryRunState(request=run_request)
        with self._lock:
            self._runs[run_id] = state
        self._persist_create(run_id, run_request)
        return run_id

    def stream(self, agent_run_id: str) -> Generator[dict[str, Any], None, None]:
        state = self._get_state(agent_run_id)
        self._ensure_executed(agent_run_id, state)
        for event in state.events:
            yield event

    def await_result(self, agent_run_id: str) -> AgentRunResult:
        state = self._get_state(agent_run_id)
        self._ensure_executed(agent_run_id, state)
        if state.result is None:
            raise RuntimeError(f"agent_run {agent_run_id} 缺少执行结果")
        return state.result

    def resume(self, agent_run_id: str, user_input: Any) -> AgentRunResult:
        state = self._get_state(agent_run_id)
        payload = state.request.input_payload if isinstance(state.request.input_payload, dict) else {}
        resume_runner = payload.get("resume_runner")
        if not callable(resume_runner):
            raise RuntimeError(f"agent_run {agent_run_id} 不支持 resume")
        with state.lock:
            state.events = []
            state.result = None
            state.executed = False
            state.running = False
            payload["runner"] = lambda: resume_runner(user_input)
            state.cancelled = False
            state.cancel_event = threading.Event()
            state.completion_event = threading.Event()
        self._persist_update(agent_run_id, status="running", started=True)
        self._ensure_executed(agent_run_id, state)
        return self.await_result(agent_run_id)

    def cancel(self, agent_run_id: str) -> None:
        state = self._get_state(agent_run_id)
        with state.lock:
            state.cancelled = True
            state.cancel_event.set()
            state.result = AgentRunResult(
                status="cancelled",
                error_code="cancelled",
                error_message="agent run cancelled",
            )
            state.executed = True
            state.completion_event.set()
        self._persist_update(
            agent_run_id,
            status="cancelled",
            error_code="cancelled",
            error_message="agent run cancelled",
            completed=True,
        )

    def _get_state(self, agent_run_id: str) -> _InMemoryRunState:
        with self._lock:
            state = self._runs.get(agent_run_id)
        if state is None:
            raise KeyError(f"未知 agent_run_id: {agent_run_id}")
        return state

    def _ensure_executed(self, agent_run_id: str, state: _InMemoryRunState) -> None:
        runner: Callable[[], Any] | None = None
        should_wait = False
        with state.lock:
            if state.executed:
                return
            if state.cancelled:
                return
            if state.running:
                should_wait = True
            else:
                state.running = True
                self._bind_runtime_cancel_context(state)
                runner = self._resolve_runner(state.request.input_payload)
        if should_wait:
            state.completion_event.wait()
            return
        if runner is None:
            return

        self._persist_update(agent_run_id, status="running", started=True)
        try:
            events, result = self._run_runner(runner)
        except Exception as exc:
            with state.lock:
                if state.cancelled:
                    state.running = False
                    state.completion_event.set()
                    return
                state.events = []
                state.result = AgentRunResult(
                    status="failed",
                    error_code=exc.__class__.__name__,
                    error_message=str(exc),
                )
                state.executed = True
                state.running = False
                state.completion_event.set()
            self._persist_update(
                agent_run_id,
                status="failed",
                error_code=exc.__class__.__name__,
                error_message=str(exc),
                completed=True,
            )
            return

        with state.lock:
            if state.cancelled:
                state.running = False
                state.completion_event.set()
                return
            state.events = events
            state.result = result
            state.executed = True
            state.running = False
            state.completion_event.set()
        self._persist_result(agent_run_id, result)

    @staticmethod
    def _bind_runtime_cancel_context(state: _InMemoryRunState) -> None:
        payload = (
            state.request.input_payload
            if isinstance(state.request.input_payload, dict)
            else {}
        )
        runtime_context = payload.get("runtime_context")
        if isinstance(runtime_context, dict):
            runtime_context["_runtime_cancel_event"] = state.cancel_event

    @staticmethod
    def _resolve_runner(input_payload: Any) -> Callable[[], Any]:
        if not isinstance(input_payload, dict):
            raise RuntimeError("LocalAgentRuntime 需要 dict 类型 input_payload")
        runner = input_payload.get("runner")
        if not callable(runner):
            raise RuntimeError("LocalAgentRuntime 需要可调用的 runner")
        return runner

    @staticmethod
    def _run_runner(
        runner: Callable[[], Any],
    ) -> tuple[list[dict[str, Any]], AgentRunResult]:
        execution = runner()
        if inspect.isgenerator(execution):
            events: list[dict[str, Any]] = []
            try:
                while True:
                    events.append(next(execution))
            except StopIteration as stop:
                return events, LocalAgentRuntime._normalize_result(stop.value)
        return [], LocalAgentRuntime._normalize_result(execution)

    @staticmethod
    def _normalize_result(value: Any) -> AgentRunResult:
        if isinstance(value, AgentRunResult):
            return value
        return AgentRunResult(status="succeeded", return_payload=value)

    def _persist_create(self, run_id: str, request: RunRequest) -> None:
        if self._service is None or not hasattr(self._service, "create_agent_run"):
            return
        input_payload = request.input_payload if isinstance(request.input_payload, dict) else {}
        input_ref = input_payload.get("input_ref")
        self._service.create_agent_run(
            run_id=run_id,
            graph_id=request.graph_id,
            subgraph_id=request.subgraph_id,
            container_key=request.container_key,
            agent_type=request.agent_type,
            runtime_id=self.runtime_id,
            parent_run_id=request.parent_run_id,
            status="queued",
            input_ref=input_ref,
            resume_token=request.resume_token,
        )

    def _persist_update(
        self,
        run_id: str,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
        started: bool = False,
        completed: bool = False,
    ) -> None:
        if self._service is None or not hasattr(self._service, "update_agent_run"):
            return
        self._service.update_agent_run(
            run_id,
            status=status,
            error_code=error_code,
            error_message=error_message,
            started=started,
            completed=completed,
        )

    def _persist_result(self, run_id: str, result: AgentRunResult) -> None:
        if self._service is None or not hasattr(self._service, "update_agent_run"):
            return
        self._service.update_agent_run(
            run_id,
            status=result.status,
            output_ref=result.return_payload if isinstance(result.return_payload, dict) else None,
            usage_json=result.usage,
            error_code=result.error_code,
            error_message=result.error_message,
            resume_token=(result.suspend_info or {}).get("resume_token") if result.suspend_info else None,
            completed=result.status in {"succeeded", "failed", "timed_out", "cancelled"},
        )


class AgentRuntimeRegistry:
    """Resolves a runtime binding for a given container or agent type."""

    def __init__(
        self,
        *,
        execution_graph_service: Any | None = None,
        runtime_factories: dict[str, Callable[[dict[str, Any]], AgentRuntime]] | None = None,
    ) -> None:
        self._service = execution_graph_service
        self._runtime_factories = runtime_factories or {}
        self._runtime_cache: dict[str, AgentRuntime] = {}

    def resolve(
        self,
        *,
        container_key: str,
        agent_type: str,
        runtime_profile: str | None = None,
    ) -> RuntimeBinding:
        normalized_profile = str(runtime_profile or "default").strip() or "default"
        row = self._load_binding_row(
            container_key=container_key,
            agent_type=agent_type,
            runtime_profile=normalized_profile,
        )
        if row is None:
            runtime_id = f"local::{normalized_profile}"
            runtime = self._runtime_cache.get(runtime_id)
            if runtime is None:
                runtime = LocalAgentRuntime(
                    runtime_id=runtime_id,
                    execution_graph_service=self._service,
                )
                self._runtime_cache[runtime_id] = runtime
            return RuntimeBinding(
                runtime_id=runtime_id,
                runtime=runtime,
                implementation_type="local",
                capability_policy={"mode": "fallback"},
                quota_policy={"runtime_profile": normalized_profile},
                memory_policy={"scope": "container"},
            )

        runtime_id = str(row.get("runtime_id") or f"local::{normalized_profile}")
        runtime = self._runtime_cache.get(runtime_id)
        if runtime is None:
            implementation_type = str(row.get("implementation_type") or "local").strip() or "local"
            if implementation_type == "local":
                runtime = LocalAgentRuntime(
                    runtime_id=runtime_id,
                    execution_graph_service=self._service,
                )
            else:
                factory = self._runtime_factories.get(implementation_type)
                if factory is None:
                    raise RuntimeError(f"未知 runtime implementation_type: {implementation_type}")
                runtime = factory(row)
            self._runtime_cache[runtime_id] = runtime

        return RuntimeBinding(
            runtime_id=runtime_id,
            runtime=runtime,
            implementation_type=str(row.get("implementation_type") or "local"),
            endpoint=row.get("endpoint"),
            capability_policy=dict(row.get("capability_policy_json") or {}),
            quota_policy=dict(row.get("quota_policy_json") or {}),
            memory_policy=dict(row.get("memory_policy_json") or {}),
        )

    def _load_binding_row(
        self,
        *,
        container_key: str,
        agent_type: str,
        runtime_profile: str,
    ) -> dict[str, Any] | None:
        if self._service is None or not hasattr(self._service, "list_agent_runtime_bindings"):
            return None
        candidates = self._service.list_agent_runtime_bindings(
            container_key=container_key,
            agent_type=agent_type,
            runtime_profile=runtime_profile,
            enabled_only=True,
        )
        if candidates:
            return dict(candidates[0])
        candidates = self._service.list_agent_runtime_bindings(
            container_key=container_key,
            runtime_profile=runtime_profile,
            enabled_only=True,
        )
        if candidates:
            return dict(candidates[0])
        candidates = self._service.list_agent_runtime_bindings(
            agent_type=agent_type,
            runtime_profile=runtime_profile,
            enabled_only=True,
        )
        if candidates:
            return dict(candidates[0])
        return None
