"""Agent runtime abstractions and governed local runtime."""

from __future__ import annotations

from collections.abc import Callable, Generator
from dataclasses import dataclass, field
import inspect
import threading
import uuid
from typing import Any, Protocol

from .state_contract import RUN_STATE_SOURCE_OF_TRUTH


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
    quota_policy: dict[str, Any] | None = None
    memory_policy: dict[str, Any] | None = None
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
    worker_thread: threading.Thread | None = None
    policy_lease: _RuntimePolicyLease | None = None  # type: ignore[name-defined]
    cancel_event: threading.Event = field(default_factory=threading.Event)
    completion_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.RLock = field(default_factory=threading.RLock)


class RuntimePolicyError(RuntimeError):
    """Raised when runtime quota or memory policies are violated."""

    def __init__(self, *, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class _RuntimePolicyLease:
    policy_id: str
    memory_scope_ref: str | None = None


class _RuntimePolicyCoordinator:
    """Tracks active runs and enforces quota / memory contracts."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._active_by_policy: dict[str, set[str]] = {}
        self._active_by_scope: dict[tuple[str, str], set[str]] = {}

    def acquire(self, run_id: str, request: RunRequest) -> _RuntimePolicyLease:
        quota_policy = dict(request.quota_policy or {})
        memory_policy = dict(request.memory_policy or {})
        policy_id = str(
            request.quota_policy_id
            or quota_policy.get("policy_id")
            or request.container_key
            or "default"
        )

        self._validate_memory_contract(request, memory_policy)
        max_concurrent_runs = self._coerce_positive_int(
            quota_policy.get("max_concurrent_runs")
        )
        max_parallel_runs_per_scope = self._coerce_positive_int(
            quota_policy.get("max_parallel_runs_per_scope")
        )

        with self._lock:
            active_for_policy = self._active_by_policy.setdefault(policy_id, set())
            if (
                max_concurrent_runs is not None
                and len(active_for_policy) >= max_concurrent_runs
            ):
                raise RuntimePolicyError(
                    code="quota_exceeded",
                    message=(
                        f"quota policy '{policy_id}' exceeded: "
                        f"{len(active_for_policy)} >= {max_concurrent_runs}"
                    ),
                )

            if request.memory_scope_ref and max_parallel_runs_per_scope is not None:
                scope_key = (policy_id, request.memory_scope_ref)
                active_for_scope = self._active_by_scope.setdefault(scope_key, set())
                if len(active_for_scope) >= max_parallel_runs_per_scope:
                    raise RuntimePolicyError(
                        code="quota_exceeded",
                        message=(
                            f"memory scope '{request.memory_scope_ref}' exceeded "
                            f"parallel limit {max_parallel_runs_per_scope}"
                        ),
                    )
                active_for_scope.add(run_id)

            active_for_policy.add(run_id)
        return _RuntimePolicyLease(
            policy_id=policy_id,
            memory_scope_ref=request.memory_scope_ref,
        )

    def release(self, run_id: str, lease: _RuntimePolicyLease | None) -> None:
        if lease is None:
            return
        with self._lock:
            policy_runs = self._active_by_policy.get(lease.policy_id)
            if policy_runs is not None:
                policy_runs.discard(run_id)
                if not policy_runs:
                    self._active_by_policy.pop(lease.policy_id, None)

            if lease.memory_scope_ref:
                scope_key = (lease.policy_id, lease.memory_scope_ref)
                scope_runs = self._active_by_scope.get(scope_key)
                if scope_runs is not None:
                    scope_runs.discard(run_id)
                    if not scope_runs:
                        self._active_by_scope.pop(scope_key, None)

    @staticmethod
    def _coerce_positive_int(raw_value: Any) -> int | None:
        try:
            value = int(raw_value)
        except (TypeError, ValueError):
            return None
        return value if value > 0 else None

    @staticmethod
    def _validate_memory_contract(
        request: RunRequest,
        memory_policy: dict[str, Any],
    ) -> None:
        strict = bool(memory_policy.get("strict_memory_contract"))
        if not strict:
            return

        scope = str(memory_policy.get("scope") or "container").strip() or "container"
        if scope == "container":
            expected_scope = f"{request.graph_id}:{request.container_key}"
            if request.memory_scope_ref != expected_scope:
                raise RuntimePolicyError(
                    code="memory_scope_violation",
                    message=(
                        f"strict container memory scope requires '{expected_scope}', "
                        f"got '{request.memory_scope_ref}'"
                    ),
                )
        elif scope == "graph":
            expected_prefix = f"{request.graph_id}:"
            if not str(request.memory_scope_ref or "").startswith(expected_prefix):
                raise RuntimePolicyError(
                    code="memory_scope_violation",
                    message=(
                        f"strict graph memory scope requires prefix '{expected_prefix}', "
                        f"got '{request.memory_scope_ref}'"
                    ),
                )


class LocalAgentRuntime:
    """Governed in-process runtime with explicit quota and memory enforcement."""

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
        self._policy_coordinator = _RuntimePolicyCoordinator()

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
            state.worker_thread = None
            self._release_policy_lease(agent_run_id, state)
            state.cancel_event = threading.Event()
            state.completion_event = threading.Event()
        self._ensure_executed(agent_run_id, state)
        return self.await_result(agent_run_id)

    def cancel(self, agent_run_id: str) -> None:
        state = self._get_state(agent_run_id)
        with state.lock:
            terminal = self._mark_terminal_state_locked(
                state,
                status="cancelled",
                error_code="cancelled",
                error_message="agent run cancelled",
            )
        if terminal:
            self._release_policy_lease(agent_run_id, state)
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
        worker_thread: threading.Thread | None = None
        timeout_seconds: float | None = None
        with state.lock:
            if state.executed:
                return
            if state.cancelled:
                return
            worker_thread = state.worker_thread
            if worker_thread is None:
                try:
                    state.policy_lease = self._policy_coordinator.acquire(
                        agent_run_id,
                        state.request,
                    )
                except RuntimePolicyError as exc:
                    self._mark_failed_before_start(
                        agent_run_id=agent_run_id,
                        state=state,
                        error_code=exc.code,
                        error_message=str(exc),
                    )
                    return
                self._bind_runtime_context(state, agent_run_id)
                runner = self._resolve_runner(state.request.input_payload)
                state.running = True
                worker_thread = threading.Thread(
                    target=self._execute_worker,
                    args=(agent_run_id, state, runner),
                    name=f"agent-run-{agent_run_id[:8]}",
                    daemon=True,
                )
                state.worker_thread = worker_thread
                self._persist_update(agent_run_id, status="running", started=True)
                worker_thread.start()
            timeout_seconds = self._resolve_timeout_seconds(state.request)

        completed = (
            state.completion_event.wait(timeout_seconds)
            if timeout_seconds is not None
            else state.completion_event.wait()
        )
        if completed:
            return

        with state.lock:
            timed_out = self._mark_terminal_state_locked(
                state,
                status="timed_out",
                error_code="timed_out",
                error_message="agent run timed out",
            )
        if timed_out:
            self._release_policy_lease(agent_run_id, state)
            self._persist_update(
                agent_run_id,
                status="timed_out",
                error_code="timed_out",
                error_message="agent run timed out",
                completed=True,
            )

    def _execute_worker(
        self,
        agent_run_id: str,
        state: _InMemoryRunState,
        runner: Callable[[], Any],
    ) -> None:
        try:
            events, result = self._run_runner(runner)
            self._validate_result_memory_contract(state.request, result)
        except Exception as exc:
            with state.lock:
                if state.executed:
                    return
                state.events = []
                state.result = AgentRunResult(
                    status="failed",
                    error_code=getattr(exc, "code", exc.__class__.__name__),
                    error_message=str(exc),
                )
                state.executed = True
                state.running = False
                state.completion_event.set()
            self._release_policy_lease(agent_run_id, state)
            self._persist_update(
                agent_run_id,
                status="failed",
                error_code=getattr(exc, "code", exc.__class__.__name__),
                error_message=str(exc),
                completed=True,
            )
            return

        with state.lock:
            if state.executed:
                return
            state.events = events
            state.result = result
            state.executed = True
            state.running = False
            state.completion_event.set()
        self._release_policy_lease(agent_run_id, state)
        self._persist_result(agent_run_id, result)

    def _mark_failed_before_start(
        self,
        *,
        agent_run_id: str,
        state: _InMemoryRunState,
        error_code: str,
        error_message: str,
    ) -> None:
        with state.lock:
            state.events = []
            state.result = AgentRunResult(
                status="failed",
                error_code=error_code,
                error_message=error_message,
            )
            state.executed = True
            state.running = False
            state.completion_event.set()
        self._persist_update(
            agent_run_id,
            status="failed",
            error_code=error_code,
            error_message=error_message,
            completed=True,
        )

    def _release_policy_lease(
        self,
        agent_run_id: str,
        state: _InMemoryRunState,
    ) -> None:
        with state.lock:
            lease = state.policy_lease
            state.policy_lease = None
        self._policy_coordinator.release(agent_run_id, lease)

    def _bind_runtime_context(
        self,
        state: _InMemoryRunState,
        agent_run_id: str,
    ) -> None:
        payload = (
            state.request.input_payload
            if isinstance(state.request.input_payload, dict)
            else {}
        )
        runtime_context = payload.get("runtime_context")
        if isinstance(runtime_context, dict):
            runtime_context["_runtime_cancel_event"] = state.cancel_event
            runtime_context["_agent_run_ref"] = {
                "run_id": agent_run_id,
                "runtime_id": self.runtime_id,
                "container_key": state.request.container_key,
                "agent_type": state.request.agent_type,
                "memory_scope_ref": state.request.memory_scope_ref,
                "source_of_truth": RUN_STATE_SOURCE_OF_TRUTH,
            }
            runtime_context["_runtime_policy"] = {
                "quota_policy_id": state.request.quota_policy_id,
                "quota_policy": dict(state.request.quota_policy or {}),
                "memory_policy": dict(state.request.memory_policy or {}),
            }

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

    @staticmethod
    def _resolve_timeout_seconds(request: RunRequest) -> float | None:
        raw_value = (request.quota_policy or {}).get("timeout_seconds")
        try:
            timeout_seconds = float(raw_value)
        except (TypeError, ValueError):
            return None
        return timeout_seconds if timeout_seconds > 0 else None

    @staticmethod
    def _validate_result_memory_contract(
        request: RunRequest,
        result: AgentRunResult,
    ) -> None:
        strict = bool((request.memory_policy or {}).get("strict_memory_contract"))
        if not strict:
            return
        if result.memory_delta_ref and result.memory_delta_ref != request.memory_scope_ref:
            raise RuntimePolicyError(
                code="memory_scope_violation",
                message=(
                    f"memory delta '{result.memory_delta_ref}' "
                    f"does not match scope '{request.memory_scope_ref}'"
                ),
            )

    @staticmethod
    def _mark_terminal_state_locked(
        state: _InMemoryRunState,
        *,
        status: str,
        error_code: str,
        error_message: str,
    ) -> bool:
        if state.executed:
            return False
        state.cancelled = status == "cancelled"
        state.cancel_event.set()
        state.result = AgentRunResult(
            status=status,
            error_code=error_code,
            error_message=error_message,
        )
        state.executed = True
        state.running = False
        state.completion_event.set()
        return True

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
                quota_policy={
                    "runtime_profile": normalized_profile,
                    "timeout_seconds": 180,
                },
                memory_policy={
                    "scope": "container",
                    "strict_memory_contract": True,
                },
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
