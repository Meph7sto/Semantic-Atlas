from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Callable, Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


MAX_LEADERBOARD_LIMIT = 50
DEFAULT_LEADERBOARD_LIMIT = 50
SUPPORTED_PERIODS = {"day", "seven_days", "year", "all"}


class UsageLeaderboardRepository(Protocol):
    def aggregate_user_usage(
        self,
        start_at: datetime | None,
        end_at: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        ...


def _utc_now() -> datetime:
    return datetime.now(UTC)


def mask_usage_display_name(
    username: str | None,
    email: str | None,
    user_id: str | None,
) -> str:
    normalized_username = (username or "").strip()
    if normalized_username:
        return normalized_username

    normalized_email = (email or "").strip()
    if "@" in normalized_email:
        local, domain = normalized_email.split("@", 1)
        first = (local[:1] or "*").lower()
        return f"{first}***@{domain.lower()}"

    suffix_source = str(user_id or "----")
    suffix = suffix_source[-4:] if len(suffix_source) >= 4 else suffix_source
    return f"用户 #{suffix}"


class UsageLeaderboardService:
    def __init__(
        self,
        repository: UsageLeaderboardRepository,
        now_provider: Callable[[], datetime] = _utc_now,
    ):
        self.repository = repository
        self.now_provider = now_provider

    def get_leaderboard(
        self,
        period: str,
        current_user_id: str,
        limit: int = DEFAULT_LEADERBOARD_LIMIT,
        timezone: str = "UTC",
    ) -> dict[str, Any]:
        normalized_period = (period or "day").strip()
        if normalized_period not in SUPPORTED_PERIODS:
            raise ValueError("无效的时间范围")

        effective_limit = min(MAX_LEADERBOARD_LIMIT, max(1, int(limit or DEFAULT_LEADERBOARD_LIMIT)))
        start_at, end_at = self._resolve_period_bounds(normalized_period, timezone)
        rows = self.repository.aggregate_user_usage(start_at, end_at, effective_limit)

        totals_row = rows[0] if rows else {}
        total_actual_cost = round(
            float(totals_row.get("total_actual_cost") or 0)
            if "total_actual_cost" in totals_row
            else sum(float(row.get("actual_cost") or 0) for row in rows),
            8,
        )
        total_tokens = (
            int(totals_row.get("total_tokens") or 0)
            if "total_tokens" in totals_row
            else sum(int(row.get("tokens") or 0) for row in rows)
        )
        total_requests = (
            int(totals_row.get("total_requests") or 0)
            if "total_requests" in totals_row
            else sum(int(row.get("requests") or 0) for row in rows)
        )

        return {
            "period": normalized_period,
            "start_date": start_at.isoformat() if start_at is not None else None,
            "end_date": end_at.isoformat() if end_at is not None else None,
            "generated_at": self._normalized_now().isoformat(),
            "total_actual_cost": total_actual_cost,
            "total_tokens": total_tokens,
            "total_requests": total_requests,
            "cost_ranking": self._build_ranking(
                rows,
                current_user_id,
                key=lambda row: (-float(row.get("actual_cost") or 0), -int(row.get("tokens") or 0)),
                limit=effective_limit,
            ),
            "token_ranking": self._build_ranking(
                rows,
                current_user_id,
                key=lambda row: (-int(row.get("tokens") or 0), -float(row.get("actual_cost") or 0)),
                limit=effective_limit,
            ),
        }

    def _resolve_period_bounds(
        self, period: str, timezone: str
    ) -> tuple[datetime | None, datetime | None]:
        now = self._normalized_now()
        if period == "all":
            return None, now

        tz = self._resolve_timezone(timezone)
        local_now = now.astimezone(tz)
        local_today = local_now.replace(hour=0, minute=0, second=0, microsecond=0)

        if period == "day":
            start_local = local_today
        elif period == "seven_days":
            start_local = local_today - timedelta(days=6)
        elif period == "year":
            start_local = local_today.replace(month=1, day=1)
        else:
            raise ValueError("无效的时间范围")

        return start_local.astimezone(UTC), now

    def _normalized_now(self) -> datetime:
        now = self.now_provider()
        if now.tzinfo is None:
            return now.replace(tzinfo=UTC)
        return now.astimezone(UTC)

    @staticmethod
    def _resolve_timezone(timezone: str) -> ZoneInfo:
        try:
            return ZoneInfo((timezone or "UTC").strip() or "UTC")
        except ZoneInfoNotFoundError:
            return ZoneInfo("UTC")

    @staticmethod
    def _build_ranking(
        rows: list[dict[str, Any]],
        current_user_id: str,
        key: Callable[[dict[str, Any]], tuple[float | int, float | int]],
        limit: int,
    ) -> list[dict[str, Any]]:
        ranked_rows = sorted(rows, key=key)[:limit]
        return [
            {
                "rank": index + 1,
                "display_name": mask_usage_display_name(
                    row.get("username"),
                    row.get("email"),
                    row.get("user_id"),
                ),
                "actual_cost": round(float(row.get("actual_cost") or 0), 8),
                "tokens": int(row.get("tokens") or 0),
                "requests": int(row.get("requests") or 0),
                "is_current_user": str(row.get("user_id")) == str(current_user_id),
            }
            for index, row in enumerate(ranked_rows)
        ]
