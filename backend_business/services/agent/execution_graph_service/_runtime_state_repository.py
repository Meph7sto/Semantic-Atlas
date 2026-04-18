"""
Execution graph runtime-state repositories.

Provides CRUD helpers for:
- agent_runtime_registry
- agent_runs
- container_state_store
"""

from __future__ import annotations

import json
import uuid
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor


_ALLOWED_AGENT_RUN_STATUSES = {
    "queued",
    "running",
    "waiting_user",
    "succeeded",
    "failed",
    "timed_out",
    "cancelled",
}


class _RuntimeStateMixin:
    """Runtime registry, run journal, and container state CRUD."""

    def ensure_agent_runtime_binding(
        self,
        *,
        container_key: str | None = None,
        agent_type: str | None = None,
        runtime_profile: str = "default",
        implementation_type: str = "local",
        endpoint: str | None = None,
        enabled: bool = True,
        capability_policy_json: Dict[str, Any] | None = None,
        quota_policy_json: Dict[str, Any] | None = None,
        memory_policy_json: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        runtime_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO agent_runtime_registry(
                        runtime_id, container_key, agent_type, runtime_profile,
                        implementation_type, endpoint, enabled,
                        capability_policy_json, quota_policy_json, memory_policy_json,
                        created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT ((COALESCE(container_key, '')), (COALESCE(agent_type, '')), runtime_profile)
                    DO UPDATE SET
                        implementation_type = EXCLUDED.implementation_type,
                        endpoint = EXCLUDED.endpoint,
                        enabled = EXCLUDED.enabled,
                        capability_policy_json = EXCLUDED.capability_policy_json,
                        quota_policy_json = EXCLUDED.quota_policy_json,
                        memory_policy_json = EXCLUDED.memory_policy_json,
                        updated_at = NOW()
                    RETURNING runtime_id, container_key, agent_type, runtime_profile,
                              implementation_type, endpoint, enabled,
                              capability_policy_json, quota_policy_json, memory_policy_json,
                              created_at::text AS created_at,
                              updated_at::text AS updated_at
                    """,
                    (
                        runtime_id,
                        container_key,
                        agent_type,
                        runtime_profile,
                        implementation_type,
                        endpoint,
                        enabled,
                        json.dumps(capability_policy_json) if capability_policy_json is not None else None,
                        json.dumps(quota_policy_json) if quota_policy_json is not None else None,
                        json.dumps(memory_policy_json) if memory_policy_json is not None else None,
                    ),
                )
                return dict(cur.fetchone())

    def create_agent_runtime_binding(
        self,
        *,
        container_key: str | None = None,
        agent_type: str | None = None,
        runtime_profile: str = "default",
        implementation_type: str = "local",
        endpoint: str | None = None,
        enabled: bool = True,
        capability_policy_json: Dict[str, Any] | None = None,
        quota_policy_json: Dict[str, Any] | None = None,
        memory_policy_json: Dict[str, Any] | None = None,
    ) -> Dict[str, Any]:
        runtime_id = str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO agent_runtime_registry(
                        runtime_id, container_key, agent_type, runtime_profile,
                        implementation_type, endpoint, enabled,
                        capability_policy_json, quota_policy_json, memory_policy_json,
                        created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW())
                    RETURNING runtime_id, container_key, agent_type, runtime_profile,
                              implementation_type, endpoint, enabled,
                              capability_policy_json, quota_policy_json, memory_policy_json,
                              created_at::text AS created_at,
                              updated_at::text AS updated_at
                    """,
                    (
                        runtime_id,
                        container_key,
                        agent_type,
                        runtime_profile,
                        implementation_type,
                        endpoint,
                        enabled,
                        json.dumps(capability_policy_json) if capability_policy_json is not None else None,
                        json.dumps(quota_policy_json) if quota_policy_json is not None else None,
                        json.dumps(memory_policy_json) if memory_policy_json is not None else None,
                    ),
                )
                return dict(cur.fetchone())

    def list_agent_runtime_bindings(
        self,
        *,
        container_key: str | None = None,
        agent_type: str | None = None,
        runtime_profile: str | None = None,
        enabled_only: bool = True,
    ) -> List[Dict[str, Any]]:
        where_clauses = ["1 = 1"]
        params: List[Any] = []
        if container_key is not None:
            where_clauses.append("container_key = %s")
            params.append(container_key)
        if agent_type is not None:
            where_clauses.append("agent_type = %s")
            params.append(agent_type)
        if runtime_profile is not None:
            where_clauses.append("runtime_profile = %s")
            params.append(runtime_profile)
        if enabled_only:
            where_clauses.append("enabled = TRUE")

        sql = f"""
            SELECT runtime_id, container_key, agent_type, runtime_profile,
                   implementation_type, endpoint, enabled,
                   capability_policy_json, quota_policy_json, memory_policy_json,
                   created_at::text AS created_at,
                   updated_at::text AS updated_at
            FROM agent_runtime_registry
            WHERE {' AND '.join(where_clauses)}
            ORDER BY updated_at DESC, created_at DESC
        """
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, params)
                return [dict(row) for row in cur.fetchall()]

    def create_agent_run(
        self,
        *,
        graph_id: str,
        subgraph_id: str | None,
        container_key: str,
        agent_type: str,
        runtime_id: str,
        status: str = "queued",
        input_ref: Dict[str, Any] | None = None,
        output_ref: Dict[str, Any] | None = None,
        usage_json: Dict[str, Any] | None = None,
        parent_run_id: str | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        resume_token: str | None = None,
        run_id: str | None = None,
    ) -> Dict[str, Any]:
        if status not in _ALLOWED_AGENT_RUN_STATUSES:
            raise ValueError(
                "status 必须是: " + ", ".join(sorted(_ALLOWED_AGENT_RUN_STATUSES))
            )

        normalized_run_id = run_id or str(uuid.uuid4())
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO agent_runs(
                        run_id, graph_id, subgraph_id, container_key, agent_type,
                        runtime_id, parent_run_id, status, input_ref, output_ref,
                        usage_json, error_code, error_message, resume_token,
                        created_at, updated_at, started_at, completed_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW(), NOW(), NULL, NULL)
                    RETURNING run_id, graph_id, subgraph_id, container_key, agent_type,
                              runtime_id, parent_run_id, status, input_ref, output_ref,
                              usage_json, error_code, error_message, resume_token,
                              created_at::text AS created_at,
                              updated_at::text AS updated_at,
                              started_at::text AS started_at,
                              completed_at::text AS completed_at
                    """,
                    (
                        normalized_run_id,
                        graph_id,
                        subgraph_id,
                        container_key,
                        agent_type,
                        runtime_id,
                        parent_run_id,
                        status,
                        json.dumps(input_ref) if input_ref is not None else None,
                        json.dumps(output_ref) if output_ref is not None else None,
                        json.dumps(usage_json) if usage_json is not None else None,
                        error_code,
                        error_message,
                        resume_token,
                    ),
                )
                return dict(cur.fetchone())

    def get_agent_run(self, run_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT run_id, graph_id, subgraph_id, container_key, agent_type,
                           runtime_id, parent_run_id, status, input_ref, output_ref,
                           usage_json, error_code, error_message, resume_token,
                           created_at::text AS created_at,
                           updated_at::text AS updated_at,
                           started_at::text AS started_at,
                           completed_at::text AS completed_at
                    FROM agent_runs
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def update_agent_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        output_ref: Dict[str, Any] | None = None,
        usage_json: Dict[str, Any] | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
        resume_token: str | None = None,
        started: bool = False,
        completed: bool = False,
    ) -> Dict[str, Any]:
        fields: List[str] = []
        values: List[Any] = []
        if status is not None:
            if status not in _ALLOWED_AGENT_RUN_STATUSES:
                raise ValueError(
                    "status 必须是: " + ", ".join(sorted(_ALLOWED_AGENT_RUN_STATUSES))
                )
            fields.append("status = %s")
            values.append(status)
        if output_ref is not None:
            fields.append("output_ref = %s")
            values.append(json.dumps(output_ref))
        if usage_json is not None:
            fields.append("usage_json = %s")
            values.append(json.dumps(usage_json))
        if error_code is not None:
            fields.append("error_code = %s")
            values.append(error_code)
        if error_message is not None:
            fields.append("error_message = %s")
            values.append(error_message)
        if resume_token is not None:
            fields.append("resume_token = %s")
            values.append(resume_token)
        if started:
            fields.append("started_at = COALESCE(started_at, NOW())")
        if completed:
            fields.append("completed_at = NOW()")

        if not fields:
            return self.get_agent_run(run_id)

        fields.append("updated_at = NOW()")
        sql = (
            f"UPDATE agent_runs SET {', '.join(fields)} WHERE run_id = %s "
            "RETURNING run_id, graph_id, subgraph_id, container_key, agent_type, "
            "runtime_id, parent_run_id, status, input_ref, output_ref, usage_json, "
            "error_code, error_message, resume_token, "
            "created_at::text AS created_at, updated_at::text AS updated_at, "
            "started_at::text AS started_at, completed_at::text AS completed_at"
        )
        values.append(run_id)
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(sql, values)
                row = cur.fetchone()
                if not row:
                    raise ValueError("agent_run 不存在")
                return dict(row)

    def get_container_state(
        self,
        graph_id: str,
        container_key: str,
    ) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT graph_id, container_key, state_json, updated_by,
                           created_at::text AS created_at,
                           updated_at::text AS updated_at
                    FROM container_state_store
                    WHERE graph_id = %s AND container_key = %s
                    """,
                    (graph_id, container_key),
                )
                row = cur.fetchone()
                return dict(row) if row else None

    def list_container_states(self, graph_id: str) -> List[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT graph_id, container_key, state_json, updated_by,
                           created_at::text AS created_at,
                           updated_at::text AS updated_at
                    FROM container_state_store
                    WHERE graph_id = %s
                    ORDER BY container_key
                    """,
                    (graph_id,),
                )
                return [dict(row) for row in cur.fetchall()]

    def upsert_container_state(
        self,
        *,
        graph_id: str,
        container_key: str,
        state_json: Dict[str, Any],
        updated_by: str = "",
    ) -> Dict[str, Any]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    INSERT INTO container_state_store(
                        graph_id, container_key, state_json, updated_by, created_at, updated_at
                    )
                    VALUES (%s, %s, %s, %s, NOW(), NOW())
                    ON CONFLICT (graph_id, container_key)
                    DO UPDATE SET
                        state_json = EXCLUDED.state_json,
                        updated_by = EXCLUDED.updated_by,
                        updated_at = NOW()
                    RETURNING graph_id, container_key, state_json, updated_by,
                              created_at::text AS created_at,
                              updated_at::text AS updated_at
                    """,
                    (
                        graph_id,
                        container_key,
                        json.dumps(state_json),
                        updated_by,
                    ),
                )
                return dict(cur.fetchone())
