"""
FastAPI requirement-actor stream route contract tests.
"""

import os
import sys
import time as _time

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.testclient import TestClient

os.environ["SKIP_DB_INIT"] = "1"

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from backend_business.api.http.errors import error_response_handler, validation_error_handler
from backend_business.api.routers import requirement_actor


class _Clock:
    def __init__(self):
        self.values = iter([0.0, 0.0, 1.0, 301.0, 302.0])
        self.last = 302.0

    def time(self):
        try:
            self.last = next(self.values)
        except StopIteration:
            pass
        return self.last


@pytest.fixture
def fastapi_client():
    app = FastAPI()
    app.include_router(requirement_actor.router)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, error_response_handler)
    app.add_exception_handler(Exception, error_response_handler)
    with TestClient(app, raise_server_exceptions=False) as client:
        yield client


def test_events_stream_returns_sse_and_expected_events(fastapi_client, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(_time, "time", clock.time)
    monkeypatch.setattr(_time, "sleep", lambda _seconds: None)

    response = fastapi_client.get("/api/v2/requirement-actor/events/stream/r-1")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: connected" in response.text
    assert "event: heartbeat" in response.text
    assert "event: timeout" in response.text

