from datetime import UTC, datetime

import pytest

from backend_business.services.usage_leaderboard_service import (
    MAX_LEADERBOARD_LIMIT,
    UsageLeaderboardService,
    mask_usage_display_name,
)


class _StubUsageRepository:
    def __init__(self):
        self.last_query = None
        self.rows = [
            {
                "user_id": "u-cost",
                "username": "cost_hero",
                "email": "cost@example.com",
                "actual_cost": 12.5,
                "tokens": 90,
                "requests": 3,
            },
            {
                "user_id": "u-token",
                "username": "",
                "email": "token@example.com",
                "actual_cost": 8.0,
                "tokens": 300,
                "requests": 2,
            },
            {
                "user_id": "u-empty",
                "username": None,
                "email": None,
                "actual_cost": 8.0,
                "tokens": 120,
                "requests": 1,
            },
        ]

    def aggregate_user_usage(self, start_at, end_at, limit):
        self.last_query = (start_at, end_at, limit)
        return list(self.rows)


def test_mask_usage_display_name_prefers_username_and_masks_email():
    assert mask_usage_display_name("alice", "alice@example.com", "u-1") == "alice"
    assert mask_usage_display_name("", "alice@example.com", "u-1") == "a***@example.com"
    assert mask_usage_display_name(None, "b@example.com", "u-1") == "b***@example.com"
    assert mask_usage_display_name(None, None, "user-abcdef") == "用户 #cdef"


def test_period_boundaries_are_calculated_in_timezone():
    repo = _StubUsageRepository()
    now = datetime(2026, 5, 23, 15, 30, tzinfo=UTC)
    service = UsageLeaderboardService(repo, now_provider=lambda: now)

    result = service.get_leaderboard("seven_days", "u-token", 200, "Asia/Shanghai")

    start_at, end_at, limit = repo.last_query
    assert start_at == datetime(2026, 5, 16, 16, 0, tzinfo=UTC)
    assert end_at == now
    assert limit == MAX_LEADERBOARD_LIMIT
    assert result["period"] == "seven_days"
    assert result["start_date"] == "2026-05-16T16:00:00+00:00"
    assert result["end_date"] == "2026-05-23T15:30:00+00:00"


@pytest.mark.parametrize(
    ("period", "expected_start"),
    [
        ("day", "2026-05-23T04:00:00+00:00"),
        ("seven_days", "2026-05-17T04:00:00+00:00"),
        ("year", "2026-01-01T05:00:00+00:00"),
        ("all", None),
    ],
)
def test_supported_periods(period, expected_start):
    repo = _StubUsageRepository()
    now = datetime(2026, 5, 23, 15, 30, tzinfo=UTC)
    service = UsageLeaderboardService(repo, now_provider=lambda: now)

    result = service.get_leaderboard(period, "u-token", 50, "America/New_York")

    assert result["period"] == period
    assert result["start_date"] == expected_start


def test_invalid_period_raises_value_error():
    service = UsageLeaderboardService(_StubUsageRepository())

    with pytest.raises(ValueError, match="无效的时间范围"):
        service.get_leaderboard("week", "u-1", 50, "UTC")


def test_rankings_totals_sorting_current_user_and_no_full_email_leak():
    repo = _StubUsageRepository()
    now = datetime(2026, 5, 23, 15, 30, tzinfo=UTC)
    service = UsageLeaderboardService(repo, now_provider=lambda: now)

    result = service.get_leaderboard("day", "u-token", 3, "UTC")

    assert result["total_actual_cost"] == 28.5
    assert result["total_tokens"] == 510
    assert result["total_requests"] == 6

    assert [row["display_name"] for row in result["cost_ranking"]] == [
        "cost_hero",
        "t***@example.com",
        "用户 #mpty",
    ]
    assert [row["display_name"] for row in result["token_ranking"]] == [
        "t***@example.com",
        "用户 #mpty",
        "cost_hero",
    ]
    assert result["token_ranking"][0]["is_current_user"] is True
    assert result["token_ranking"][0]["rank"] == 1
    assert "token@example.com" not in str(result)
