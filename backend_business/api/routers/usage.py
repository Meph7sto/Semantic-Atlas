from fastapi import APIRouter, Depends, Query

from backend_business.api.deps.auth import get_current_user
from backend_business.api.http.errors import ErrorResponse
from backend_business.services.db_service import db_service
from backend_business.services.usage_leaderboard_service import (
    DEFAULT_LEADERBOARD_LIMIT,
    MAX_LEADERBOARD_LIMIT,
    UsageLeaderboardService,
)


router = APIRouter(tags=["usage"])


def _get_usage_leaderboard_service() -> UsageLeaderboardService:
    if db_service is None:
        raise ErrorResponse("数据库服务未初始化", 500)
    return UsageLeaderboardService(db_service)


def _leaderboard_response(
    period: str,
    limit: int,
    timezone: str,
    current_user: dict,
):
    try:
        return _get_usage_leaderboard_service().get_leaderboard(
            period=period,
            current_user_id=current_user["user_id"],
            limit=limit,
            timezone=timezone,
        )
    except ValueError as exc:
        raise ErrorResponse(str(exc), 400)


@router.get("/api/v1/usage/leaderboard")
def get_usage_leaderboard_v1(
    period: str = Query("day", description="day|seven_days|year|all"),
    limit: int = Query(DEFAULT_LEADERBOARD_LIMIT, ge=1),
    timezone: str = Query("UTC"),
    current_user: dict = Depends(get_current_user),
):
    return _leaderboard_response(
        period=period,
        limit=min(limit, MAX_LEADERBOARD_LIMIT),
        timezone=timezone,
        current_user=current_user,
    )


@router.get("/api/v2/usage/leaderboard")
def get_usage_leaderboard_v2(
    period: str = Query("day", description="day|seven_days|year|all"),
    limit: int = Query(DEFAULT_LEADERBOARD_LIMIT, ge=1),
    timezone: str = Query("UTC"),
    current_user: dict = Depends(get_current_user),
):
    return _leaderboard_response(
        period=period,
        limit=min(limit, MAX_LEADERBOARD_LIMIT),
        timezone=timezone,
        current_user=current_user,
    )
