"""
Unit tests for execution graph schema initialization.
"""

from __future__ import annotations

import os
import sys

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.agent.execution_graph_service import _base as execution_graph_module
from backend_business.services.agent.execution_graph_service import ExecutionGraphService
from backend_business.services.db_service_parts.schemas.execution_schema import init_execution_schema


class _FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


class _RecordingCursor:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def execute(self, sql: str) -> None:
        self.statements.append(sql)


def test_execution_graph_service_initializes_schema_once(monkeypatch):
    init_calls: list[object] = []
    connections: list[_FakeConnection] = []

    def _fake_connect(_dsn: str) -> _FakeConnection:
        conn = _FakeConnection()
        connections.append(conn)
        return conn

    def _fake_init_db(conn: object) -> None:
        init_calls.append(conn)

    monkeypatch.setattr(execution_graph_module.psycopg2, "connect", _fake_connect)
    monkeypatch.setattr(execution_graph_module, "init_db", _fake_init_db)

    service = ExecutionGraphService("postgresql://example")
    first_conn = service._connect()
    second_conn = service._connect()

    assert first_conn is connections[0]
    assert second_conn is connections[1]
    assert init_calls == [connections[0]]
    assert connections[0].closed is False
    assert connections[1].closed is False


def test_execution_graph_service_closes_connection_on_schema_init_failure(monkeypatch):
    connection = _FakeConnection()

    monkeypatch.setattr(execution_graph_module.psycopg2, "connect", lambda _dsn: connection)
    monkeypatch.setattr(
        execution_graph_module,
        "init_db",
        lambda _conn: (_ for _ in ()).throw(RuntimeError("schema init failed")),
    )

    service = ExecutionGraphService("postgresql://example")

    try:
        service._connect()
        raise AssertionError("schema init should fail")
    except RuntimeError as exc:
        assert str(exc) == "schema init failed"

    assert connection.closed is True


def test_execution_schema_uses_generic_status_constraint_rewrite():
    cursor = _RecordingCursor()

    init_execution_schema(cursor)

    status_migration_sql = next(
        statement
        for statement in cursor.statements
        if "ADD CONSTRAINT chk_execution_graphs_status" in statement
    )

    assert "ILIKE '%status%'" in status_migration_sql
    assert "running" in status_migration_sql
    assert "succeeded" in status_migration_sql
    assert "suspended" in status_migration_sql
    assert "status IN (''draft'', ''active'')" not in status_migration_sql


def test_execution_schema_uses_generic_node_type_constraint_rewrite():
    cursor = _RecordingCursor()

    init_execution_schema(cursor)

    node_type_migration_sql = next(
        statement
        for statement in cursor.statements
        if "ADD CONSTRAINT chk_execution_nodes_node_type" in statement
    )

    assert "ILIKE '%node_type%'" in node_type_migration_sql
    assert "conname = 'chk_execution_nodes_node_type'" in node_type_migration_sql
    assert "llm" in node_type_migration_sql
    assert "invoke" in node_type_migration_sql
    assert "UPDATE execution_nodes SET node_type = 'node' WHERE node_type = 'task'" in node_type_migration_sql
    assert "LIKE '%node_type IN (''start'', ''node'', ''decision'', ''handoff'', ''end'')%'" not in node_type_migration_sql


def test_execution_schema_creates_agent_runtime_tables():
    cursor = _RecordingCursor()

    init_execution_schema(cursor)

    joined = "\n".join(cursor.statements)
    assert "CREATE TABLE IF NOT EXISTS agent_runtime_registry" in joined
    assert "CREATE TABLE IF NOT EXISTS agent_runs" in joined
    assert "CREATE TABLE IF NOT EXISTS container_state_store" in joined


def test_execution_schema_agent_run_statuses_cover_runtime_lifecycle():
    cursor = _RecordingCursor()

    init_execution_schema(cursor)

    agent_runs_sql = next(
        statement
        for statement in cursor.statements
        if "CREATE TABLE IF NOT EXISTS agent_runs" in statement
    )
    assert "queued" in agent_runs_sql
    assert "running" in agent_runs_sql
    assert "cancelling" in agent_runs_sql
    assert "timing_out" in agent_runs_sql
    assert "waiting_user" in agent_runs_sql
    assert "succeeded" in agent_runs_sql
    assert "failed" in agent_runs_sql
    assert "timed_out" in agent_runs_sql
    assert "cancelled" in agent_runs_sql

    status_migration_sql = next(
        statement
        for statement in cursor.statements
        if "ADD CONSTRAINT chk_agent_runs_status" in statement
    )
    assert "cancelling" in status_migration_sql
    assert "timing_out" in status_migration_sql
