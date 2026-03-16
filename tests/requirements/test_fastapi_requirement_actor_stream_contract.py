"""
FastAPI requirement-actor stream route contract tests.
"""

import time as _time

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError


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
async def fastapi_client():
    app = build_test_app(requirement_actor.router)
    async with async_client(app) as client:
        yield client


async def test_events_stream_returns_sse_and_expected_events(fastapi_client, monkeypatch):
    clock = _Clock()
    monkeypatch.setattr(_time, "time", clock.time)
    monkeypatch.setattr(_time, "sleep", lambda _seconds: None)

    response = await fastapi_client.get("/api/v2/requirement-actor/events/stream/r-1")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "event: connected" in response.text
    assert "event: heartbeat" in response.text
    assert "event: timeout" in response.text

