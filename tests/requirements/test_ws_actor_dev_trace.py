"""WebSocket test for actor dev trace (requires TestClient for WS support).

asyncio.Queue is NOT thread-safe across event loops. TestClient runs the ASGI
app in a separate thread, so we pre-load the queue before the connection starts
to avoid cross-thread ``put_nowait`` -> ``await get()`` notification failures.
"""

import asyncio
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend_business.api.routers import requirement_actor


def _build_ws_app():
    app = FastAPI()
    app.include_router(requirement_actor.router)
    app.include_router(requirement_actor.internals_router)
    return app


def test_actor_dev_trace_ws_streams_connected_and_trace(monkeypatch):
    trace_payload = {"stage": "passivated", "requirement_id": "r-9"}
    unsubscribed: list[asyncio.Queue[dict[str, Any]]] = []

    def _fake_subscribe() -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        q.put_nowait(trace_payload)
        return q

    monkeypatch.setattr(requirement_actor, "subscribe", _fake_subscribe)
    monkeypatch.setattr(requirement_actor, "unsubscribe", lambda q: unsubscribed.append(q))

    with TestClient(_build_ws_app()) as client:
        with client.websocket_connect("/api/v2/_internals/actors/ws") as ws:
            first = ws.receive_json()
            assert first["event"] == "actor_dev_trace"
            assert first["data"]["stage"] == "connected"

            second = ws.receive_json()
            assert second["event"] == "actor_dev_trace"
            assert second["data"]["stage"] == "passivated"
            assert second["data"]["requirement_id"] == "r-9"

    assert len(unsubscribed) == 1
