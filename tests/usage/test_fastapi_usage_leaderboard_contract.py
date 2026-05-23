from datetime import UTC, datetime

import pytest

from backend_business.api.deps.auth import get_current_user
from backend_business.api.routers import usage


class _StubUsageService:
    def __init__(self):
        self.calls = []

    def get_leaderboard(self, period, current_user_id, limit, timezone):
        self.calls.append(
            {
                "period": period,
                "current_user_id": current_user_id,
                "limit": limit,
                "timezone": timezone,
            }
        )
        if period == "bad":
            raise ValueError("无效的时间范围")
        return {
            "period": period,
            "start_date": "2026-05-23T04:00:00+00:00",
            "end_date": "2026-05-23T15:30:00+00:00",
            "generated_at": datetime(2026, 5, 23, 15, 30, tzinfo=UTC).isoformat(),
            "total_actual_cost": 1.25,
            "total_tokens": 100,
            "total_requests": 2,
            "cost_ranking": [
                {
                    "rank": 1,
                    "display_name": "alice",
                    "actual_cost": 1.25,
                    "tokens": 100,
                    "requests": 2,
                    "is_current_user": True,
                }
            ],
            "token_ranking": [],
        }


@pytest.fixture
async def fastapi_client(monkeypatch):
    stub = _StubUsageService()
    monkeypatch.setattr(usage, "_get_usage_leaderboard_service", lambda: stub)

    app = build_test_app(
        usage.router,
        dependency_overrides={
            get_current_user: lambda: {
                "user_id": "member-1",
                "username": "member",
                "role": "member",
            }
        },
    )

    async with async_client(app) as client:
        yield client, stub


async def test_usage_leaderboard_available_to_authenticated_users_on_v1_and_v2(fastapi_client):
    client, stub = fastapi_client

    response = await client.get(
        "/api/v1/usage/leaderboard?period=day&limit=99&timezone=America/New_York"
    )
    assert response.status_code == 200
    data = response.json()
    assert data["period"] == "day"
    assert data["cost_ranking"][0]["is_current_user"] is True
    assert stub.calls[-1] == {
        "period": "day",
        "current_user_id": "member-1",
        "limit": 50,
        "timezone": "America/New_York",
    }

    alias = await client.get("/api/v2/usage/leaderboard?period=all")
    assert alias.status_code == 200
    assert stub.calls[-1]["period"] == "all"


async def test_usage_leaderboard_rejects_invalid_period(fastapi_client):
    client, _ = fastapi_client

    response = await client.get("/api/v1/usage/leaderboard?period=bad")

    assert response.status_code == 400
    assert response.json()["detail"] == "无效的时间范围"
