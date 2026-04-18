"""Subgraph / Graph state machine definitions and execution exceptions.

This module defines:
- SubgraphStatus: four-state enum for individual subgraph lifecycle
- GraphStatus: five-state enum for graph-level status (derived from subgraphs)
- validate_subgraph_transition(): state transition guard
- derive_graph_status(): graph status derivation from subgraph states
- SuspendSignal / ContainerExecutionError: execution control exceptions
"""

from __future__ import annotations

from enum import Enum
from typing import Sequence


# ---------------------------------------------------------------------------
# Subgraph four-state enum
# ---------------------------------------------------------------------------

class SubgraphStatus(str, Enum):
    """Lifecycle states of an individual subgraph."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


# Legal Subgraph transitions: source → set of allowed targets
_SUBGRAPH_TRANSITIONS: dict[SubgraphStatus, frozenset[SubgraphStatus]] = {
    SubgraphStatus.PENDING: frozenset({SubgraphStatus.RUNNING}),
    SubgraphStatus.RUNNING: frozenset({SubgraphStatus.COMPLETED, SubgraphStatus.FAILED}),
    SubgraphStatus.COMPLETED: frozenset(),
    SubgraphStatus.FAILED: frozenset(),
}


def validate_subgraph_transition(current: SubgraphStatus, target: SubgraphStatus) -> bool:
    """Return True if *current → target* is a legal subgraph transition."""
    return target in _SUBGRAPH_TRANSITIONS.get(current, frozenset())


# ---------------------------------------------------------------------------
# Graph five-state enum (derived, never directly set by SubgraphRunner)
# ---------------------------------------------------------------------------

class GraphStatus(str, Enum):
    """Graph-level status, derived from the collective subgraph states."""

    RUNNING = "running"
    DELEGATING = "delegating"
    SUSPENDED = "suspended"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# Lightweight data carriers used by derive_graph_status
# ---------------------------------------------------------------------------

class SubgraphInfo:
    """Read-only snapshot of a subgraph's status + metadata for derivation.

    Parameters
    ----------
    status : SubgraphStatus
        Current lifecycle status.
    node_type : str
        One of 'llm', 'invoke', 'handoff'.
    container_id : str
        Container this subgraph belongs to.
    is_last_in_container : bool
        Whether this subgraph is the last one in its container.
    """

    __slots__ = ("status", "node_type", "container_id", "is_last_in_container")

    def __init__(
        self,
        *,
        status: SubgraphStatus,
        node_type: str,
        container_id: str,
        is_last_in_container: bool = False,
    ) -> None:
        self.status = status
        self.node_type = node_type
        self.container_id = container_id
        self.is_last_in_container = is_last_in_container


def derive_graph_status(subgraphs: Sequence[SubgraphInfo]) -> GraphStatus:
    """Derive the graph-level status from the collective subgraph states.

    Rules (evaluated in priority order):
    1. Any subgraph FAILED → GraphStatus.FAILED
    2. Any 'handoff' subgraph RUNNING → GraphStatus.SUSPENDED
    3. Any 'invoke' subgraph RUNNING → GraphStatus.DELEGATING
    4. All last-in-container subgraphs COMPLETED → GraphStatus.SUCCEEDED
    5. Otherwise → GraphStatus.RUNNING

    ``DELEGATING`` is a graph-level aggregate state only. It means one or more
    invoke subgraphs are actively delegating work to other containers; it is
    not an additional subgraph lifecycle state and does not imply resumable
    "waiting" semantics outside the running graph.
    """
    if not subgraphs:
        return GraphStatus.SUCCEEDED

    has_running_handoff = False
    has_running_invoke = False
    last_subgraphs: list[SubgraphInfo] = []

    for sg in subgraphs:
        if sg.status == SubgraphStatus.FAILED:
            return GraphStatus.FAILED

        if sg.status == SubgraphStatus.RUNNING:
            if sg.node_type == "handoff":
                has_running_handoff = True
            elif sg.node_type == "invoke":
                has_running_invoke = True

        if sg.is_last_in_container:
            last_subgraphs.append(sg)

    if has_running_handoff:
        return GraphStatus.SUSPENDED

    if has_running_invoke:
        return GraphStatus.DELEGATING

    # All containers' last subgraphs completed → graph succeeded
    if last_subgraphs and all(
        sg.status == SubgraphStatus.COMPLETED for sg in last_subgraphs
    ):
        return GraphStatus.SUCCEEDED

    return GraphStatus.RUNNING


# ---------------------------------------------------------------------------
# Execution control exceptions
# ---------------------------------------------------------------------------

class SuspendSignal(Exception):
    """Raised by a handoff subgraph to suspend the graph execution.

    The graph should transition to SUSPENDED; the caller captures this
    and stores the suspended subgraph_id so that ``resume()`` knows
    where to continue.
    """

    def __init__(self, subgraph_id: str) -> None:
        self.subgraph_id = subgraph_id
        super().__init__(f"Graph suspended at subgraph {subgraph_id}")


class ContainerExecutionError(Exception):
    """Raised when a container encounters an unrecoverable error.

    Attributes
    ----------
    container_id : str
        Container where the error occurred.
    subgraph_id : str
        Specific subgraph that failed.
    cause : Exception
        The original exception.
    """

    def __init__(
        self,
        container_id: str,
        subgraph_id: str,
        cause: Exception,
        *,
        agent_run_id: str | None = None,
        error_code: str | None = None,
    ) -> None:
        self.container_id = container_id
        self.subgraph_id = subgraph_id
        self.cause = cause
        self.agent_run_id = agent_run_id
        self.error_code = error_code
        super().__init__(
            f"Container {container_id} failed at subgraph {subgraph_id}: {cause}"
        )
