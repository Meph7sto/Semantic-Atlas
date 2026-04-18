"""
Comprehensive unit tests for ExecutionGraphService CRUD operations.

Covers all five entities (Graph, Container, Subgraph, Node, Edge),
aggregated methods, compatibility aliases, and base-layer helpers.

All database interactions are mocked — no real PostgreSQL required.
"""

from __future__ import annotations

import json
import re
import uuid
from contextlib import contextmanager
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch, call

import pytest

from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.agent.execution_graph_service._base import (
    _ALLOWED_EDGE_TYPES,
    _ALLOWED_GRAPH_STATUSES,
    _ALLOWED_GRAPH_TYPES,
    _ALLOWED_NODE_TYPES,
    _ALLOWED_ROLE_TYPES,
    _utc_now_iso,
)


# ═══════════════════════════════════════════════════════════════════
# Helpers / Fixtures
# ═══════════════════════════════════════════════════════════════════

def _make_fake_row(data: Dict[str, Any]):
    """Return a RealDictRow-like object that supports dict() conversion."""
    return data


class _FakeCursor:
    """A minimal cursor mock that supports execute / fetchone / fetchall."""

    def __init__(self, *, fetchone_result=None, fetchall_result=None):
        self._fetchone = fetchone_result
        self._fetchall = fetchall_result or []
        self.executed: List[tuple] = []  # [(sql, params), ...]

    def execute(self, sql: str, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self._fetchone

    def fetchall(self):
        return self._fetchall

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass


class _FakeConnection:
    """A minimal connection that yields a _FakeCursor via cursor()."""

    def __init__(self, cursor: _FakeCursor):
        self._cursor = cursor

    def cursor(self, cursor_factory=None):
        return self._cursor

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def close(self):
        pass


def _build_service(
    *,
    fetchone_result=None,
    fetchall_result=None,
) -> tuple[ExecutionGraphService, _FakeCursor]:
    """Create an ExecutionGraphService with a mocked _connect."""
    cursor = _FakeCursor(
        fetchone_result=fetchone_result,
        fetchall_result=fetchall_result,
    )
    conn = _FakeConnection(cursor)
    svc = ExecutionGraphService.__new__(ExecutionGraphService)
    svc.dsn = "postgresql://test"
    svc._schema_initialized = True
    svc._connect = lambda: conn
    return svc, cursor


def _graph_row(**overrides) -> Dict[str, Any]:
    defaults = {
        "graph_id": str(uuid.uuid4()),
        "project_id": "proj-1",
        "name": "Test Graph",
        "description": "desc",
        "graph_type": "execution_topology_template",
        "version": 1,
        "status": "draft",
        "layout_json": None,
        "meta_json": None,
        "created_by": "tester",
        "updated_by": "",
        "created_at": "2026-01-01T00:00:00+00",
    }
    defaults.update(overrides)
    return defaults


def _container_row(**overrides) -> Dict[str, Any]:
    defaults = {
        "container_id": str(uuid.uuid4()),
        "graph_id": str(uuid.uuid4()),
        "container_key": "c-key",
        "label": "Container",
        "role_type": "agent",
        "config_json": None,
        "order_index": 0,
        "created_at": "2026-01-01T00:00:00+00",
    }
    defaults.update(overrides)
    return defaults


def _subgraph_row(**overrides) -> Dict[str, Any]:
    defaults = {
        "subgraph_id": str(uuid.uuid4()),
        "graph_id": str(uuid.uuid4()),
        "container_id": str(uuid.uuid4()),
        "subgraph_key": "sg-key",
        "label": "Subgraph",
        "task_description": "desc",
        "order_index": 0,
        "config_json": None,
        "created_at": "2026-01-01T00:00:00+00",
    }
    defaults.update(overrides)
    return defaults


def _node_row(**overrides) -> Dict[str, Any]:
    defaults = {
        "node_id": str(uuid.uuid4()),
        "graph_id": str(uuid.uuid4()),
        "container_id": None,
        "subgraph_id": None,
        "node_key": "n-key",
        "label": "Node",
        "node_type": "llm",
        "role_type": "agent",
        "config_json": None,
        "input_schema_json": None,
        "output_schema_json": None,
        "order_index": 0,
        "created_at": "2026-01-01T00:00:00+00",
    }
    defaults.update(overrides)
    return defaults


def _edge_row(**overrides) -> Dict[str, Any]:
    defaults = {
        "edge_id": str(uuid.uuid4()),
        "graph_id": str(uuid.uuid4()),
        "source_node_id": str(uuid.uuid4()),
        "target_node_id": str(uuid.uuid4()),
        "edge_type": "call",
        "label": None,
        "condition_expr": None,
        "config_json": None,
        "order_index": 0,
        "created_at": "2026-01-01T00:00:00+00",
    }
    defaults.update(overrides)
    return defaults


def _runtime_binding_row(**overrides) -> Dict[str, Any]:
    defaults = {
        "runtime_id": str(uuid.uuid4()),
        "container_key": "requirement_agent",
        "agent_type": "requirement_agent",
        "runtime_profile": "default",
        "implementation_type": "local",
        "endpoint": None,
        "enabled": True,
        "capability_policy_json": {"tools": ["read_requirement"]},
        "quota_policy_json": {"max_parallel_runs": 2},
        "memory_policy_json": {"scope": "container"},
        "created_at": "2026-01-01T00:00:00+00",
        "updated_at": "2026-01-01T00:00:00+00",
    }
    defaults.update(overrides)
    return defaults


def _agent_run_row(**overrides) -> Dict[str, Any]:
    defaults = {
        "run_id": str(uuid.uuid4()),
        "graph_id": str(uuid.uuid4()),
        "subgraph_id": str(uuid.uuid4()),
        "container_key": "requirement_agent",
        "agent_type": "requirement_agent",
        "runtime_id": str(uuid.uuid4()),
        "parent_run_id": None,
        "status": "queued",
        "input_ref": {"task": "inspect"},
        "output_ref": None,
        "usage_json": None,
        "error_code": None,
        "error_message": None,
        "resume_token": None,
        "created_at": "2026-01-01T00:00:00+00",
        "updated_at": "2026-01-01T00:00:00+00",
        "started_at": None,
        "completed_at": None,
    }
    defaults.update(overrides)
    return defaults


def _container_state_row(**overrides) -> Dict[str, Any]:
    defaults = {
        "graph_id": str(uuid.uuid4()),
        "container_key": "requirement_agent",
        "state_json": {"scratchpad_snapshot": [{"content": "secret"}]},
        "updated_by": "tester",
        "created_at": "2026-01-01T00:00:00+00",
        "updated_at": "2026-01-01T00:00:00+00",
    }
    defaults.update(overrides)
    return defaults


# ═══════════════════════════════════════════════════════════════════
#  1. _base.py — Helpers & Constants
# ═══════════════════════════════════════════════════════════════════

class TestBaseHelpers:
    """Tests for _base.py utility functions and constants."""

    def test_utc_now_iso_format(self):
        ts = _utc_now_iso()
        assert ts.endswith("Z")
        # Should look like "2026-03-18T07:06:36Z"
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z", ts)

    def test_allowed_node_types_complete(self):
        assert _ALLOWED_NODE_TYPES == {"start", "llm", "handoff", "invoke", "end"}

    def test_allowed_edge_types_complete(self):
        assert _ALLOWED_EDGE_TYPES == {"call", "return", "retry", "seq"}

    def test_allowed_role_types_complete(self):
        assert _ALLOWED_ROLE_TYPES == {"human", "agent", "system"}

    def test_allowed_graph_statuses_complete(self):
        assert _ALLOWED_GRAPH_STATUSES == {"draft", "active", "running", "succeeded", "failed", "suspended"}

    def test_allowed_graph_types_complete(self):
        assert _ALLOWED_GRAPH_TYPES == {"execution_topology_template", "agent_runtime_execution"}


# ═══════════════════════════════════════════════════════════════════
#  1b. Runtime Registry / Agent Runs / Container State
# ═══════════════════════════════════════════════════════════════════

class TestRuntimeStateCRUD:

    def test_create_agent_runtime_binding(self):
        row = _runtime_binding_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.create_agent_runtime_binding(
            container_key="requirement_agent",
            agent_type="requirement_agent",
            runtime_profile="default",
            implementation_type="local",
            capability_policy_json={"tools": ["read_requirement"]},
            quota_policy_json={"max_parallel_runs": 2},
            memory_policy_json={"scope": "container"},
        )

        assert result == row
        sql, params = cur.executed[0]
        assert "INSERT INTO agent_runtime_registry" in sql
        assert "requirement_agent" in params

    def test_list_agent_runtime_bindings_filters_enabled(self):
        rows = [_runtime_binding_row()]
        svc, cur = _build_service(fetchall_result=rows)

        result = svc.list_agent_runtime_bindings(
            container_key="requirement_agent",
            enabled_only=True,
        )

        assert result == rows
        sql, params = cur.executed[0]
        assert "FROM agent_runtime_registry" in sql
        assert "enabled = TRUE" in sql
        assert "requirement_agent" in params

    def test_ensure_agent_runtime_binding_uses_upsert_semantics(self):
        row = _runtime_binding_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.ensure_agent_runtime_binding(
            container_key="requirement_agent",
            agent_type="requirement_agent",
            runtime_profile="default",
            implementation_type="local",
            capability_policy_json={"tool_names": ["search_requirements"]},
            quota_policy_json={"max_parallel_runs": 2},
            memory_policy_json={"scope": "container"},
        )

        assert result == row
        sql, params = cur.executed[0]
        assert "INSERT INTO agent_runtime_registry" in sql
        assert "ON CONFLICT" in sql
        assert "DO UPDATE SET" in sql
        assert "requirement_agent" in params

    def test_create_agent_run(self):
        row = _agent_run_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.create_agent_run(
            graph_id=row["graph_id"],
            subgraph_id=row["subgraph_id"],
            container_key=row["container_key"],
            agent_type=row["agent_type"],
            runtime_id=row["runtime_id"],
            status="queued",
            input_ref={"task": "inspect"},
        )

        assert result == row
        sql, params = cur.executed[0]
        assert "INSERT INTO agent_runs" in sql
        assert "queued" in params

    def test_update_agent_run(self):
        row = _agent_run_row(status="succeeded", output_ref={"reply": "done"})
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_agent_run(
            row["run_id"],
            status="succeeded",
            output_ref={"reply": "done"},
            usage_json={"total_tokens": 123},
        )

        assert result == row
        sql, _params = cur.executed[0]
        assert "UPDATE agent_runs SET" in sql
        assert "output_ref = %s" in sql
        assert "usage_json = %s" in sql

    def test_upsert_and_get_container_state(self):
        row = _container_state_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.upsert_container_state(
            graph_id=row["graph_id"],
            container_key=row["container_key"],
            state_json=row["state_json"],
            updated_by="tester",
        )

        assert result == row
        sql, _params = cur.executed[0]
        assert "INSERT INTO container_state_store" in sql
        assert "ON CONFLICT (graph_id, container_key)" in sql

    def test_list_container_states(self):
        rows = [_container_state_row(container_key="requirement_agent")]
        svc, cur = _build_service(fetchall_result=rows)

        result = svc.list_container_states(rows[0]["graph_id"])

        assert result == rows
        sql, params = cur.executed[0]
        assert "FROM container_state_store" in sql
        assert rows[0]["graph_id"] in params


# ═══════════════════════════════════════════════════════════════════
#  2. Graph CRUD
# ═══════════════════════════════════════════════════════════════════

class TestGraphCRUD:

    def test_create_execution_graph(self):
        row = _graph_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.create_execution_graph("proj-1", "My Graph", "desc", "user-a")

        assert result == row
        assert len(cur.executed) == 1
        sql = cur.executed[0][0]
        assert "INSERT INTO execution_graphs" in sql
        assert "'execution_topology_template'" in sql

    def test_create_runtime_graph(self):
        row = _graph_row(graph_type="agent_runtime_execution", status="running")
        svc, cur = _build_service(fetchone_result=row)

        result = svc.create_runtime_graph(
            project_id="proj-1",
            name="Runtime",
            status="running",
            meta_json={"session_id": "s1"},
            layout_json={"x": 1},
        )

        assert result == row
        sql = cur.executed[0][0]
        assert "'agent_runtime_execution'" in sql
        # meta_json & layout_json should be serialized via json.dumps
        params = cur.executed[0][1]
        assert json.dumps({"x": 1}) in [p for p in params if isinstance(p, str)]
        assert json.dumps({"session_id": "s1"}) in [p for p in params if isinstance(p, str)]

    def test_create_runtime_graph_invalid_status(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="status"):
            svc.create_runtime_graph("proj-1", "G", status="invalid_status")

    def test_list_execution_graphs(self):
        rows = [_graph_row(name="A"), _graph_row(name="B")]
        svc, cur = _build_service(fetchall_result=rows)

        result = svc.list_execution_graphs("proj-1")

        assert result == rows
        sql = cur.executed[0][0]
        assert "is_deleted = FALSE" in sql

    def test_list_execution_graphs_include_deleted(self):
        rows = [_graph_row()]
        svc, cur = _build_service(fetchall_result=rows)

        result = svc.list_execution_graphs("proj-1", include_deleted=True)

        assert result == rows
        sql = cur.executed[0][0]
        assert "is_deleted" not in sql

    def test_list_execution_graphs_invalid_type(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="graph_type"):
            svc.list_execution_graphs("proj-1", graph_types=["bad_type"])

    def test_get_execution_graph(self):
        row = _graph_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.get_execution_graph(row["graph_id"])

        assert result == row
        sql = cur.executed[0][0]
        assert "is_deleted = FALSE" in sql

    def test_get_execution_graph_include_deleted(self):
        row = _graph_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.get_execution_graph(row["graph_id"], include_deleted=True)

        assert result == row
        sql = cur.executed[0][0]
        assert "is_deleted" not in sql

    def test_get_execution_graph_not_found(self):
        svc, _ = _build_service(fetchone_result=None)
        assert svc.get_execution_graph("nonexistent") is None

    def test_update_execution_graph(self):
        row = _graph_row(name="Updated", status="active")
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_execution_graph(
            row["graph_id"], name="Updated", status="active", updated_by="u"
        )

        assert result == row
        sql = cur.executed[0][0]
        assert "UPDATE execution_graphs SET" in sql
        assert "name = %s" in sql
        assert "status = %s" in sql

    def test_update_execution_graph_invalid_status(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="status"):
            svc.update_execution_graph("g1", status="nope")

    def test_update_execution_graph_not_found(self):
        svc, _ = _build_service(fetchone_result=None)
        with pytest.raises(ValueError, match="图不存在"):
            svc.update_execution_graph("g1", name="X")

    def test_update_execution_graph_no_fields(self):
        """When no fields are provided, should fall back to get_execution_graph."""
        row = _graph_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_execution_graph(row["graph_id"])

        assert result == row
        # Should have executed a SELECT, not an UPDATE
        sql = cur.executed[0][0]
        assert "SELECT" in sql

    def test_update_execution_graph_with_layout_and_meta(self):
        row = _graph_row(layout_json={"pos": [1, 2]}, meta_json={"k": "v"})
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_execution_graph(
            row["graph_id"],
            layout_json={"pos": [1, 2]},
            meta_json={"k": "v"},
        )

        assert result == row
        sql = cur.executed[0][0]
        assert "layout_json = %s" in sql
        assert "meta_json = %s" in sql

    def test_delete_execution_graph(self):
        svc, cur = _build_service(fetchone_result=("g1",))

        assert svc.delete_execution_graph("g1", updated_by="u") is True
        sql = cur.executed[0][0]
        assert "is_deleted = TRUE" in sql

    def test_delete_execution_graph_already_deleted(self):
        svc, _ = _build_service(fetchone_result=None)
        assert svc.delete_execution_graph("g-gone") is False

    def test_list_runtime_graphs_by_session_empty_session_id(self):
        svc, _ = _build_service()
        assert svc.list_runtime_graphs_by_session("") == []

    def test_list_runtime_graphs_by_session(self):
        rows = [_graph_row(graph_type="agent_runtime_execution")]
        svc, cur = _build_service(fetchall_result=rows)

        result = svc.list_runtime_graphs_by_session("sess-1")

        assert result == rows
        sql = cur.executed[0][0]
        assert "agent_runtime_execution" in sql
        assert "session_id" in sql

    def test_list_runtime_graphs_by_session_with_project_id(self):
        rows = [_graph_row()]
        svc, cur = _build_service(fetchall_result=rows)

        result = svc.list_runtime_graphs_by_session("sess-1", project_id="proj-1")

        assert result == rows
        sql = cur.executed[0][0]
        assert "project_id = %s" in sql
        params = cur.executed[0][1]
        assert "proj-1" in params

    def test_list_runtime_graphs_by_session_include_deleted(self):
        svc, cur = _build_service(fetchall_result=[])

        svc.list_runtime_graphs_by_session("sess-1", include_deleted=True)

        sql = cur.executed[0][0]
        assert "is_deleted" not in sql

    def test_get_latest_runtime_graph_by_session(self):
        row = _graph_row()
        svc, _ = _build_service(fetchall_result=[row])

        result = svc.get_latest_runtime_graph_by_session("sess-1")
        assert result == row

    def test_get_latest_runtime_graph_by_session_none(self):
        svc, _ = _build_service(fetchall_result=[])

        result = svc.get_latest_runtime_graph_by_session("sess-x")
        assert result is None


# ═══════════════════════════════════════════════════════════════════
#  3. Container CRUD
# ═══════════════════════════════════════════════════════════════════

class TestContainerCRUD:

    def test_create_container(self):
        row = _container_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.create_container(
            graph_id="g1",
            container_key="ck",
            label="Cont",
            role_type="agent",
            config_json={"model": "gpt-4"},
            order_index=1,
            created_by="u",
        )

        assert result == row
        sql = cur.executed[0][0]
        assert "INSERT INTO execution_containers" in sql

    def test_create_container_invalid_role_type(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="role_type"):
            svc.create_container("g1", "ck", "L", role_type="invalid")

    def test_list_containers(self):
        rows = [_container_row(), _container_row()]
        svc, cur = _build_service(fetchall_result=rows)

        result = svc.list_containers("g1")

        assert result == rows
        sql = cur.executed[0][0]
        assert "is_deleted = FALSE" in sql

    def test_list_containers_include_deleted(self):
        svc, cur = _build_service(fetchall_result=[])

        svc.list_containers("g1", include_deleted=True)

        sql = cur.executed[0][0]
        assert "is_deleted" not in sql

    def test_get_container(self):
        row = _container_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.get_container(row["container_id"])

        assert result == row
        sql = cur.executed[0][0]
        assert "is_deleted = FALSE" in sql

    def test_get_container_include_deleted(self):
        row = _container_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.get_container(row["container_id"], include_deleted=True)

        assert result == row
        sql = cur.executed[0][0]
        assert "is_deleted" not in sql

    def test_get_container_not_found(self):
        svc, _ = _build_service(fetchone_result=None)
        assert svc.get_container("nope") is None

    def test_update_container(self):
        row = _container_row(label="New Label", role_type="human")
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_container(
            row["container_id"], label="New Label", role_type="human", order_index=5
        )

        assert result == row
        sql = cur.executed[0][0]
        assert "UPDATE execution_containers SET" in sql
        assert "label = %s" in sql
        assert "role_type = %s" in sql
        assert "order_index = %s" in sql

    def test_update_container_invalid_role_type(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="role_type"):
            svc.update_container("c1", role_type="bad")

    def test_update_container_not_found(self):
        svc, _ = _build_service(fetchone_result=None)
        with pytest.raises(ValueError, match="容器不存在"):
            svc.update_container("c1", label="X")

    def test_update_container_no_fields(self):
        row = _container_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_container(row["container_id"])

        assert result == row
        sql = cur.executed[0][0]
        assert "SELECT" in sql

    def test_update_container_config_json(self):
        row = _container_row(config_json={"model": "gpt-4o"})
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_container(row["container_id"], config_json={"model": "gpt-4o"})

        assert result == row
        sql = cur.executed[0][0]
        assert "config_json = %s" in sql

    def test_delete_container(self):
        svc, cur = _build_service(fetchone_result=("c1",))

        assert svc.delete_container("c1", updated_by="u") is True
        # Should execute 2 statements: clear nodes' container_id + soft delete
        assert len(cur.executed) == 2
        assert "execution_nodes" in cur.executed[0][0]
        assert "container_id = NULL" in cur.executed[0][0]
        assert "is_deleted = TRUE" in cur.executed[1][0]

    def test_delete_container_already_deleted(self):
        svc, _ = _build_service(fetchone_result=None)
        assert svc.delete_container("c-gone") is False


# ═══════════════════════════════════════════════════════════════════
#  4. Subgraph CRUD
# ═══════════════════════════════════════════════════════════════════

class _MultiStepCursor(_FakeCursor):
    """A cursor that returns different results on successive fetchone calls."""

    def __init__(self, fetchone_results: list, fetchall_result=None):
        super().__init__(fetchall_result=fetchall_result)
        self._results = list(fetchone_results)
        self._call_idx = 0

    def fetchone(self):
        if self._call_idx < len(self._results):
            r = self._results[self._call_idx]
            self._call_idx += 1
            return r
        return None


class TestSubgraphCRUD:

    def test_create_subgraph(self):
        container_check = {"container_id": "c1"}
        sg_row = _subgraph_row()
        cursor = _MultiStepCursor([container_check, sg_row])
        conn = _FakeConnection(cursor)
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc._connect = lambda: conn

        result = svc.create_subgraph(
            graph_id="g1",
            container_id="c1",
            subgraph_key="sk",
            label="SG",
            task_description="do stuff",
            config_json={"retry": 3},
        )

        assert result == sg_row
        # First execute: container verification; Second: INSERT
        assert len(cursor.executed) == 2
        assert "execution_containers" in cursor.executed[0][0]
        assert "INSERT INTO execution_subgraphs" in cursor.executed[1][0]

    def test_create_subgraph_container_not_belong(self):
        cursor = _MultiStepCursor([None])  # container check returns None
        conn = _FakeConnection(cursor)
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc._connect = lambda: conn

        with pytest.raises(ValueError, match="容器不存在"):
            svc.create_subgraph("g1", "c-bad", "sk", "L", "desc")

    def test_list_subgraphs(self):
        rows = [_subgraph_row()]
        svc, cur = _build_service(fetchall_result=rows)

        result = svc.list_subgraphs("g1")

        assert result == rows
        sql = cur.executed[0][0]
        assert "is_deleted = FALSE" in sql

    def test_list_subgraphs_include_deleted(self):
        svc, cur = _build_service(fetchall_result=[])

        svc.list_subgraphs("g1", include_deleted=True)

        sql = cur.executed[0][0]
        assert "is_deleted" not in sql

    def test_get_subgraph(self):
        row = _subgraph_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.get_subgraph(row["subgraph_id"])

        assert result == row

    def test_get_subgraph_include_deleted(self):
        row = _subgraph_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.get_subgraph(row["subgraph_id"], include_deleted=True)

        assert result == row
        sql = cur.executed[0][0]
        assert "is_deleted" not in sql

    def test_get_subgraph_not_found(self):
        svc, _ = _build_service(fetchone_result=None)
        assert svc.get_subgraph("nope") is None

    def test_update_subgraph(self):
        row = _subgraph_row(label="New")
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_subgraph(
            row["subgraph_id"], label="New", task_description="updated", order_index=2
        )

        assert result == row
        sql = cur.executed[0][0]
        assert "UPDATE execution_subgraphs SET" in sql
        assert "label = %s" in sql
        assert "task_description = %s" in sql

    def test_update_subgraph_config_json(self):
        row = _subgraph_row(config_json={"key": "val"})
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_subgraph(row["subgraph_id"], config_json={"key": "val"})

        assert result == row
        sql = cur.executed[0][0]
        assert "config_json = %s" in sql

    def test_update_subgraph_not_found(self):
        svc, _ = _build_service(fetchone_result=None)
        with pytest.raises(ValueError, match="子图不存在"):
            svc.update_subgraph("sg1", label="X")

    def test_update_subgraph_no_fields(self):
        row = _subgraph_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_subgraph(row["subgraph_id"])

        assert result == row
        sql = cur.executed[0][0]
        assert "SELECT" in sql

    def test_delete_subgraph(self):
        svc, cur = _build_service(fetchone_result=("sg1",))

        assert svc.delete_subgraph("sg1", updated_by="u") is True
        # Should clear nodes' subgraph_id + soft delete
        assert len(cur.executed) == 2
        assert "subgraph_id = NULL" in cur.executed[0][0]
        assert "is_deleted = TRUE" in cur.executed[1][0]

    def test_delete_subgraph_already_deleted(self):
        svc, _ = _build_service(fetchone_result=None)
        assert svc.delete_subgraph("sg-gone") is False


# ═══════════════════════════════════════════════════════════════════
#  5. Node CRUD
# ═══════════════════════════════════════════════════════════════════

class TestNodeCRUD:

    def test_create_node_minimal(self):
        """Create a node without container_id or subgraph_id."""
        row = _node_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.create_node(
            graph_id="g1",
            node_key="nk",
            label="N",
            node_type="llm",
            role_type="agent",
        )

        assert result == row
        sql = cur.executed[0][0]
        assert "INSERT INTO execution_nodes" in sql

    def test_create_node_with_container_and_subgraph(self):
        """Container and subgraph must be verified before INSERT."""
        container_check = {"container_id": "c1"}
        subgraph_check = {"subgraph_id": "sg1"}
        node_row = _node_row(container_id="c1", subgraph_id="sg1")

        cursor = _MultiStepCursor([container_check, subgraph_check, node_row])
        conn = _FakeConnection(cursor)
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc._connect = lambda: conn

        result = svc.create_node(
            graph_id="g1",
            node_key="nk",
            label="N",
            node_type="start",
            role_type="human",
            container_id="c1",
            subgraph_id="sg1",
        )

        assert result == node_row
        # exec order: container check, subgraph check, INSERT
        assert len(cursor.executed) == 3

    def test_create_node_invalid_node_type(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="node_type"):
            svc.create_node("g1", "nk", "N", node_type="unknown", role_type="agent")

    def test_create_node_invalid_role_type(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="role_type"):
            svc.create_node("g1", "nk", "N", node_type="llm", role_type="robot")

    def test_create_node_container_not_belong(self):
        cursor = _MultiStepCursor([None])  # container check fails
        conn = _FakeConnection(cursor)
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc._connect = lambda: conn

        with pytest.raises(ValueError, match="容器不存在"):
            svc.create_node(
                "g1", "nk", "N", node_type="llm", role_type="agent", container_id="bad-c"
            )

    def test_create_node_subgraph_not_belong(self):
        # Container check passes but subgraph check fails
        cursor = _MultiStepCursor([None])
        conn = _FakeConnection(cursor)
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc._connect = lambda: conn

        with pytest.raises(ValueError, match="子图不存在"):
            svc.create_node(
                "g1", "nk", "N", node_type="llm", role_type="agent", subgraph_id="bad-sg"
            )

    def test_create_node_with_schemas(self):
        """input_schema_json and output_schema_json should be serialized."""
        row = _node_row(
            input_schema_json=[{"field": "a"}],
            output_schema_json=[{"field": "b"}],
        )
        svc, cur = _build_service(fetchone_result=row)

        result = svc.create_node(
            graph_id="g1",
            node_key="nk",
            label="N",
            node_type="llm",
            role_type="agent",
            input_schema_json=[{"field": "a"}],
            output_schema_json=[{"field": "b"}],
        )

        assert result == row
        params = cur.executed[0][1]
        assert json.dumps([{"field": "a"}]) in [p for p in params if isinstance(p, str)]

    def test_list_nodes(self):
        rows = [_node_row(), _node_row()]
        svc, cur = _build_service(fetchall_result=rows)

        result = svc.list_nodes("g1")

        assert result == rows
        sql = cur.executed[0][0]
        assert "is_deleted = FALSE" in sql

    def test_list_nodes_include_deleted(self):
        svc, cur = _build_service(fetchall_result=[])

        svc.list_nodes("g1", include_deleted=True)

        sql = cur.executed[0][0]
        assert "is_deleted" not in sql

    def test_get_node(self):
        row = _node_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.get_node(row["node_id"])

        assert result == row
        sql = cur.executed[0][0]
        assert "is_deleted = FALSE" in sql

    def test_get_node_include_deleted(self):
        row = _node_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.get_node(row["node_id"], include_deleted=True)

        assert result == row
        sql = cur.executed[0][0]
        assert "is_deleted" not in sql

    def test_get_node_not_found(self):
        svc, _ = _build_service(fetchone_result=None)
        assert svc.get_node("nope") is None

    def test_update_node_basic_fields(self):
        row = _node_row(label="New", node_type="invoke")
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_node(
            row["node_id"], label="New", node_type="invoke", role_type="system"
        )

        assert result == row
        sql = cur.executed[0][0]
        assert "UPDATE execution_nodes SET" in sql
        assert "label = %s" in sql
        assert "node_type = %s" in sql
        assert "role_type = %s" in sql

    def test_update_node_invalid_node_type(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="node_type"):
            svc.update_node("n1", node_type="bad")

    def test_update_node_invalid_role_type(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="role_type"):
            svc.update_node("n1", role_type="bad")

    def test_update_node_not_found(self):
        svc, _ = _build_service(fetchone_result=None)
        with pytest.raises(ValueError, match="节点不存在"):
            svc.update_node("n1", label="X")

    def test_update_node_no_fields(self):
        row = _node_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_node(row["node_id"])

        assert result == row
        sql = cur.executed[0][0]
        assert "SELECT" in sql

    def test_update_node_schemas(self):
        row = _node_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_node(
            row["node_id"],
            input_schema_json=[{"f": 1}],
            output_schema_json=[{"f": 2}],
        )

        assert result == row
        sql = cur.executed[0][0]
        assert "input_schema_json = %s" in sql
        assert "output_schema_json = %s" in sql

    def test_update_node_with_container_validation(self):
        """When updating container_id, should verify container belongs to same graph."""
        node = _node_row(graph_id="g1")
        container = _container_row(graph_id="g1")

        # get_node returns node, get_container returns container, then UPDATE returns node
        cursor = _MultiStepCursor([node, container, node])
        conn = _FakeConnection(cursor)
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc._connect = lambda: conn

        # We also need to patch get_node and get_container since they use _connect internally
        svc.get_node = lambda nid, **kw: node
        svc.get_container = lambda cid, **kw: container

        result = svc.update_node(node["node_id"], container_id=container["container_id"])
        assert result == node

    def test_delete_node(self):
        svc, cur = _build_service(fetchone_result=("n1",))

        assert svc.delete_node("n1", updated_by="u") is True
        sql = cur.executed[0][0]
        assert "is_deleted = TRUE" in sql

    def test_delete_node_already_deleted(self):
        svc, _ = _build_service(fetchone_result=None)
        assert svc.delete_node("n-gone") is False


# ═══════════════════════════════════════════════════════════════════
#  6. Edge CRUD
# ═══════════════════════════════════════════════════════════════════

class TestEdgeCRUD:

    def _build_edge_service(self, *, edge_row=None):
        """Helper that sets up cursor responses for create_edge validations."""
        source = {"node_id": "src"}
        target = {"node_id": "tgt"}
        source_graph = {"node_id": "src"}
        target_graph = {"node_id": "tgt"}
        final_row = edge_row or _edge_row()

        cursor = _MultiStepCursor(
            [source, target, source_graph, target_graph, final_row]
        )
        conn = _FakeConnection(cursor)
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc._connect = lambda: conn
        return svc, cursor

    def test_create_edge(self):
        row = _edge_row()
        svc, cur = self._build_edge_service(edge_row=row)

        result = svc.create_edge(
            graph_id="g1",
            source_node_id="src",
            target_node_id="tgt",
            edge_type="call",
            label="next",
            condition_expr="x > 0",
            config_json={"timeout": 30},
        )

        assert result == row
        # 5 executes: source check, target check, source graph check, target graph check, INSERT
        assert len(cur.executed) == 5
        insert_sql = cur.executed[4][0]
        assert "INSERT INTO execution_edges" in insert_sql

    def test_create_edge_self_loop(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="自环"):
            svc.create_edge("g1", "n1", "n1", "call")

    def test_create_edge_invalid_type(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="edge_type"):
            svc.create_edge("g1", "n1", "n2", "invalid_type")

    def test_create_edge_source_not_exist(self):
        cursor = _MultiStepCursor([None])  # source check fails
        conn = _FakeConnection(cursor)
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc._connect = lambda: conn

        with pytest.raises(ValueError, match="源节点不存在"):
            svc.create_edge("g1", "bad-src", "tgt", "call")

    def test_create_edge_target_not_exist(self):
        cursor = _MultiStepCursor([{"node_id": "src"}, None])
        conn = _FakeConnection(cursor)
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc._connect = lambda: conn

        with pytest.raises(ValueError, match="目标节点不存在"):
            svc.create_edge("g1", "src", "bad-tgt", "call")

    def test_create_edge_source_not_in_graph(self):
        cursor = _MultiStepCursor([{"node_id": "src"}, {"node_id": "tgt"}, None])
        conn = _FakeConnection(cursor)
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc._connect = lambda: conn

        with pytest.raises(ValueError, match="源节点不属于当前图"):
            svc.create_edge("g1", "src", "tgt", "call")

    def test_create_edge_target_not_in_graph(self):
        cursor = _MultiStepCursor(
            [{"node_id": "src"}, {"node_id": "tgt"}, {"node_id": "src"}, None]
        )
        conn = _FakeConnection(cursor)
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc._connect = lambda: conn

        with pytest.raises(ValueError, match="目标节点不属于当前图"):
            svc.create_edge("g1", "src", "tgt", "call")

    def test_list_edges(self):
        rows = [_edge_row(), _edge_row()]
        svc, cur = _build_service(fetchall_result=rows)

        result = svc.list_edges("g1")

        assert result == rows
        sql = cur.executed[0][0]
        assert "is_deleted = FALSE" in sql

    def test_list_edges_include_deleted(self):
        svc, cur = _build_service(fetchall_result=[])

        svc.list_edges("g1", include_deleted=True)

        sql = cur.executed[0][0]
        assert "is_deleted" not in sql

    def test_get_edge(self):
        row = _edge_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.get_edge(row["edge_id"])

        assert result == row
        sql = cur.executed[0][0]
        assert "is_deleted = FALSE" in sql

    def test_get_edge_include_deleted(self):
        row = _edge_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.get_edge(row["edge_id"], include_deleted=True)

        assert result == row
        sql = cur.executed[0][0]
        assert "is_deleted" not in sql

    def test_get_edge_not_found(self):
        svc, _ = _build_service(fetchone_result=None)
        assert svc.get_edge("nope") is None

    def test_update_edge(self):
        row = _edge_row(label="Updated", edge_type="return")
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_edge(
            row["edge_id"],
            label="Updated",
            edge_type="return",
            condition_expr="y == 1",
            config_json={"k": "v"},
            order_index=3,
        )

        assert result == row
        sql = cur.executed[0][0]
        assert "UPDATE execution_edges SET" in sql
        assert "label = %s" in sql
        assert "edge_type = %s" in sql
        assert "condition_expr = %s" in sql
        assert "config_json = %s" in sql
        assert "order_index = %s" in sql

    def test_update_edge_invalid_type(self):
        svc, _ = _build_service()
        with pytest.raises(ValueError, match="edge_type"):
            svc.update_edge("e1", edge_type="bad")

    def test_update_edge_not_found(self):
        svc, _ = _build_service(fetchone_result=None)
        with pytest.raises(ValueError, match="边不存在"):
            svc.update_edge("e1", label="X")

    def test_update_edge_no_fields(self):
        row = _edge_row()
        svc, cur = _build_service(fetchone_result=row)

        result = svc.update_edge(row["edge_id"])

        assert result == row
        sql = cur.executed[0][0]
        assert "SELECT" in sql

    def test_delete_edge(self):
        svc, cur = _build_service(fetchone_result=("e1",))

        assert svc.delete_edge("e1", updated_by="u") is True
        sql = cur.executed[0][0]
        assert "is_deleted = TRUE" in sql

    def test_delete_edge_already_deleted(self):
        svc, _ = _build_service(fetchone_result=None)
        assert svc.delete_edge("e-gone") is False


# ═══════════════════════════════════════════════════════════════════
#  7. Aggregated / Compatibility Methods (__init__.py)
# ═══════════════════════════════════════════════════════════════════

class TestAggregatedMethods:

    def test_get_graph_detail(self):
        graph = _graph_row()
        containers = [_container_row()]
        subgraphs = [_subgraph_row()]
        nodes = [_node_row()]
        edges = [_edge_row()]

        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc.get_execution_graph = lambda gid, include_deleted=False: graph
        svc.list_containers = lambda gid, include_deleted=False: containers
        svc.list_subgraphs = lambda gid, include_deleted=False: subgraphs
        svc.list_nodes = lambda gid, include_deleted=False: nodes
        svc.list_edges = lambda gid, include_deleted=False: edges

        result = svc.get_graph_detail("g1")

        assert result["graph"] == graph
        assert result["containers"] == containers
        assert result["subgraphs"] == subgraphs
        assert result["nodes"] == nodes
        assert result["edges"] == edges

    def test_get_graph_detail_not_found(self):
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc.get_execution_graph = lambda gid, include_deleted=False: None

        result = svc.get_graph_detail("nonexistent")

        assert result["graph"] is None
        assert result["containers"] == []
        assert result["subgraphs"] == []
        assert result["nodes"] == []
        assert result["edges"] == []

    def test_patch_graph_meta(self):
        existing = _graph_row(meta_json={"a": 1, "b": 2})
        updated = _graph_row(meta_json={"a": 1, "b": 2, "c": 3})

        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc.get_execution_graph = lambda gid, **kw: existing
        svc.update_execution_graph = lambda **kw: updated

        result = svc.patch_graph_meta("g1", {"c": 3}, status="active", updated_by="u")

        assert result == updated

    def test_patch_graph_meta_merges_correctly(self):
        """Ensure meta_patch merges into existing meta without losing keys."""
        existing = _graph_row(meta_json={"x": 10, "y": 20})

        captured_kwargs = {}

        def fake_update(**kw):
            captured_kwargs.update(kw)
            return _graph_row(meta_json={"x": 10, "y": 20, "z": 30})

        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc.get_execution_graph = lambda gid, **kw: existing
        svc.update_execution_graph = fake_update

        svc.patch_graph_meta("g1", {"z": 30})

        assert captured_kwargs["meta_json"] == {"x": 10, "y": 20, "z": 30}

    def test_patch_graph_meta_with_none_existing_meta(self):
        """When meta_json is None, patch should still work."""
        existing = _graph_row(meta_json=None)

        captured_kwargs = {}

        def fake_update(**kw):
            captured_kwargs.update(kw)
            return _graph_row(meta_json={"new": True})

        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc.get_execution_graph = lambda gid, **kw: existing
        svc.update_execution_graph = fake_update

        svc.patch_graph_meta("g1", {"new": True})

        assert captured_kwargs["meta_json"] == {"new": True}

    def test_patch_graph_meta_not_found(self):
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc.get_execution_graph = lambda gid, **kw: None

        with pytest.raises(ValueError, match="图不存在"):
            svc.patch_graph_meta("g-bad", {"k": "v"})


class TestCompatibilityMethods:

    def test_list_execution_containers(self):
        containers = [_container_row()]
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc.list_containers = lambda graph_id, include_deleted=False: containers

        result = svc.list_execution_containers("g1")
        assert result == containers

    def test_list_execution_nodes(self):
        nodes = [_node_row()]
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc.list_nodes = lambda graph_id, include_deleted=False: nodes

        result = svc.list_execution_nodes("g1")
        assert result == nodes

    def test_list_execution_edges(self):
        edges = [_edge_row()]
        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc.list_edges = lambda graph_id, include_deleted=False: edges

        result = svc.list_execution_edges("g1")
        assert result == edges

    def test_list_execution_containers_include_deleted(self):
        called_with = {}

        def mock_list(graph_id, include_deleted=False):
            called_with["include_deleted"] = include_deleted
            return []

        svc = ExecutionGraphService.__new__(ExecutionGraphService)
        svc.dsn = "postgresql://test"
        svc._schema_initialized = True
        svc.list_containers = mock_list

        svc.list_execution_containers("g1", include_deleted=True)
        assert called_with["include_deleted"] is True
