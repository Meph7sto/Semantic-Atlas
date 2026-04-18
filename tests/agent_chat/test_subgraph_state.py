"""Tests for subgraph / graph state machine and execution exceptions.

Coverage:
- SubgraphStatus legal transitions (full matrix)
- Illegal transitions rejected
- GraphStatus derivation under various subgraph combinations
- SuspendSignal and ContainerExecutionError attribute fidelity
"""

from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

import pytest

from backend_business.services.agent.execution.subgraph_state import (
    ContainerExecutionError,
    GraphStatus,
    SubgraphInfo,
    SubgraphStatus,
    SuspendSignal,
    derive_graph_status,
    validate_subgraph_transition,
)


# ========================================================================
# 1. SubgraphStatus transition validation
# ========================================================================


class TestSubgraphTransitions:
    """Every legal and illegal transition is explicitly asserted."""

    # ---- legal transitions ----

    def test_pending_to_running(self):
        assert validate_subgraph_transition(SubgraphStatus.PENDING, SubgraphStatus.RUNNING) is True

    def test_running_to_completed(self):
        assert validate_subgraph_transition(SubgraphStatus.RUNNING, SubgraphStatus.COMPLETED) is True

    def test_running_to_failed(self):
        assert validate_subgraph_transition(SubgraphStatus.RUNNING, SubgraphStatus.FAILED) is True

    # ---- illegal transitions ----

    @pytest.mark.parametrize(
        "current, target",
        [
            (SubgraphStatus.PENDING, SubgraphStatus.COMPLETED),
            (SubgraphStatus.PENDING, SubgraphStatus.FAILED),
            (SubgraphStatus.PENDING, SubgraphStatus.PENDING),
            (SubgraphStatus.RUNNING, SubgraphStatus.PENDING),
            (SubgraphStatus.RUNNING, SubgraphStatus.RUNNING),
            (SubgraphStatus.COMPLETED, SubgraphStatus.PENDING),
            (SubgraphStatus.COMPLETED, SubgraphStatus.RUNNING),
            (SubgraphStatus.COMPLETED, SubgraphStatus.COMPLETED),
            (SubgraphStatus.COMPLETED, SubgraphStatus.FAILED),
            (SubgraphStatus.FAILED, SubgraphStatus.PENDING),
            (SubgraphStatus.FAILED, SubgraphStatus.RUNNING),
            (SubgraphStatus.FAILED, SubgraphStatus.COMPLETED),
            (SubgraphStatus.FAILED, SubgraphStatus.FAILED),
        ],
    )
    def test_illegal_transitions_rejected(self, current, target):
        assert validate_subgraph_transition(current, target) is False


# ========================================================================
# 2. GraphStatus derivation
# ========================================================================


def _sg(
    status: SubgraphStatus,
    node_type: str = "llm",
    container_id: str = "c1",
    is_last: bool = False,
) -> SubgraphInfo:
    """Shorthand factory."""
    return SubgraphInfo(
        status=status,
        node_type=node_type,
        container_id=container_id,
        is_last_in_container=is_last,
    )


class TestDeriveGraphStatus:

    def test_empty_subgraphs_means_succeeded(self):
        assert derive_graph_status([]) == GraphStatus.SUCCEEDED

    def test_all_last_subgraphs_completed_single_container(self):
        sgs = [
            _sg(SubgraphStatus.COMPLETED, is_last=False),
            _sg(SubgraphStatus.COMPLETED, is_last=True),
        ]
        assert derive_graph_status(sgs) == GraphStatus.SUCCEEDED

    def test_all_last_subgraphs_completed_multi_container(self):
        sgs = [
            _sg(SubgraphStatus.COMPLETED, container_id="c1", is_last=True),
            _sg(SubgraphStatus.COMPLETED, container_id="c2", is_last=True),
        ]
        assert derive_graph_status(sgs) == GraphStatus.SUCCEEDED

    def test_any_subgraph_failed_means_graph_failed(self):
        sgs = [
            _sg(SubgraphStatus.COMPLETED, is_last=True),
            _sg(SubgraphStatus.FAILED),
        ]
        assert derive_graph_status(sgs) == GraphStatus.FAILED

    def test_handoff_running_means_suspended(self):
        """A running handoff subgraph → graph is Suspended."""
        sgs = [
            _sg(SubgraphStatus.COMPLETED),
            _sg(SubgraphStatus.RUNNING, node_type="handoff"),
        ]
        assert derive_graph_status(sgs) == GraphStatus.SUSPENDED

    def test_invoke_running_means_delegating(self):
        """A running invoke subgraph → graph is in graph-level Delegating state."""
        sgs = [
            _sg(SubgraphStatus.COMPLETED),
            _sg(SubgraphStatus.RUNNING, node_type="invoke"),
        ]
        assert derive_graph_status(sgs) == GraphStatus.DELEGATING

    def test_failed_takes_precedence_over_suspended(self):
        """FAILED should win over SUSPENDED in priority."""
        sgs = [
            _sg(SubgraphStatus.FAILED),
            _sg(SubgraphStatus.RUNNING, node_type="handoff"),
        ]
        assert derive_graph_status(sgs) == GraphStatus.FAILED

    def test_suspended_takes_precedence_over_delegating(self):
        """SUSPENDED should win over DELEGATING in priority."""
        sgs = [
            _sg(SubgraphStatus.RUNNING, node_type="handoff"),
            _sg(SubgraphStatus.RUNNING, node_type="invoke"),
        ]
        assert derive_graph_status(sgs) == GraphStatus.SUSPENDED

    def test_some_pending_means_running(self):
        """When some subgraphs are pending and none are failed/suspended, graph is RUNNING."""
        sgs = [
            _sg(SubgraphStatus.COMPLETED),
            _sg(SubgraphStatus.PENDING),
        ]
        assert derive_graph_status(sgs) == GraphStatus.RUNNING

    def test_llm_running_means_graph_running(self):
        """An llm subgraph running normally → graph is RUNNING."""
        sgs = [
            _sg(SubgraphStatus.COMPLETED),
            _sg(SubgraphStatus.RUNNING, node_type="llm"),
        ]
        assert derive_graph_status(sgs) == GraphStatus.RUNNING

    def test_no_last_subgraphs_marked_means_running(self):
        """If no subgraph is marked as last-in-container, graph stays RUNNING."""
        sgs = [
            _sg(SubgraphStatus.COMPLETED, is_last=False),
            _sg(SubgraphStatus.COMPLETED, is_last=False),
        ]
        assert derive_graph_status(sgs) == GraphStatus.RUNNING

    def test_partial_last_subgraphs_completed(self):
        """Only some containers' last subgraph completed → still RUNNING."""
        sgs = [
            _sg(SubgraphStatus.COMPLETED, container_id="c1", is_last=True),
            _sg(SubgraphStatus.PENDING, container_id="c2", is_last=True),
        ]
        assert derive_graph_status(sgs) == GraphStatus.RUNNING


# ========================================================================
# 3. Exception classes
# ========================================================================


class TestSuspendSignal:

    def test_stores_subgraph_id(self):
        sig = SuspendSignal("sg-42")
        assert sig.subgraph_id == "sg-42"

    def test_message_contains_subgraph_id(self):
        sig = SuspendSignal("sg-42")
        assert "sg-42" in str(sig)

    def test_is_exception(self):
        assert issubclass(SuspendSignal, Exception)


class TestContainerExecutionError:

    def test_stores_attributes(self):
        cause = RuntimeError("boom")
        err = ContainerExecutionError("c-1", "sg-5", cause)
        assert err.container_id == "c-1"
        assert err.subgraph_id == "sg-5"
        assert err.cause is cause

    def test_message_contains_ids(self):
        cause = ValueError("bad input")
        err = ContainerExecutionError("c-1", "sg-5", cause)
        msg = str(err)
        assert "c-1" in msg
        assert "sg-5" in msg
        assert "bad input" in msg

    def test_is_exception(self):
        assert issubclass(ContainerExecutionError, Exception)
