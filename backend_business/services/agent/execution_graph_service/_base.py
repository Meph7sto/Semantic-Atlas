"""
执行拓扑图服务 — 基础设施层
提供常量定义、数据库连接管理和 schema 初始化
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

import psycopg2
from psycopg2.extras import RealDictCursor

from backend_business.services.db_service_parts.schema import init_db


# ─── 业务常量 ───────────────────────────────────────────

_ALLOWED_NODE_TYPES = {"start", "llm", "handoff", "invoke", "end"}
_ALLOWED_EDGE_TYPES = {"call", "return", "retry", "seq"}
_ALLOWED_ROLE_TYPES = {"human", "agent", "system"}
_ALLOWED_GRAPH_STATUSES = {"draft", "active", "running", "succeeded", "failed", "suspended"}
_ALLOWED_GRAPH_TYPES = {"execution_topology_template", "agent_runtime_execution"}


# ─── 辅助函数 ───────────────────────────────────────────

def _utc_now_iso() -> str:
    return datetime.utcnow().isoformat(timespec="seconds") + "Z"


# ─── 基础 Mixin ─────────────────────────────────────────

class _BaseMixin:
    """提供数据库连接和 schema 初始化能力。

    所有实体 Mixin 通过继承此类获得 ``self._connect()`` 方法。
    """

    def __init__(self, dsn: str):
        self.dsn = dsn
        self._schema_initialized = False
        self._schema_init_lock = threading.Lock()

    def _connect(self) -> psycopg2.extensions.connection:
        conn = psycopg2.connect(self.dsn)
        try:
            self._init_db_if_needed(conn)
        except Exception:
            conn.close()
            raise
        return conn

    def _init_db_if_needed(self, conn: psycopg2.extensions.connection) -> None:
        if self._schema_initialized:
            return

        with self._schema_init_lock:
            if self._schema_initialized:
                return
            init_db(conn)
            self._schema_initialized = True
