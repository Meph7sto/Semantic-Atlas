"""
Auth DB mixin tests for role fallback behavior.
"""

import os
import sys
from datetime import datetime, timezone

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.services.db_service_parts.auth import AuthMixin


class _FakeCursor:
    def __init__(self):
        self.last_query = None
        self.last_params = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def execute(self, query, params):
        self.last_query = query
        self.last_params = params

    def fetchone(self):
        role = self.last_params[4] if self.last_params else "member"
        return (
            "user-1",
            "new-user",
            "新用户",
            role,
            False,
            None,
            None,
            datetime(2026, 2, 25, tzinfo=timezone.utc),
            "pending",
        )


class _FakeConnection:
    def __init__(self, cursor):
        self._cursor = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def cursor(self):
        return self._cursor

    def commit(self):
        self.committed = True


class _FakeAuthService(AuthMixin):
    def __init__(self, conn):
        self._conn = conn

    def get_connection(self):
        return self._conn


def test_create_user_falls_back_to_viewer_when_role_is_none():
    cursor = _FakeCursor()
    conn = _FakeConnection(cursor)
    service = _FakeAuthService(conn)

    user = service.create_user(
        user_id="user-1",
        username="new-user",
        password_hash="hashed",
        display_name="新用户",
        role=None,
        is_active=False,
        registration_status="pending",
    )

    assert cursor.last_params[4] == "viewer"
    assert user["role"] == "viewer"
    assert conn.committed is True
