from datetime import datetime
from typing import Any


class UsageMixin:
    """Usage log aggregation queries."""

    def aggregate_user_usage(
        self,
        start_at: datetime | None,
        end_at: datetime | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        where_clauses = []
        params: list[Any] = []

        if start_at is not None:
            where_clauses.append("ul.created_at >= %s")
            params.append(start_at)
        if end_at is not None:
            where_clauses.append("ul.created_at <= %s")
            params.append(end_at)

        where_sql = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        params.extend([limit, limit])

        with self.get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    WITH aggregated AS (
                        SELECT
                            ul.user_id,
                            COALESCE(SUM(ul.actual_cost), 0)::float8 AS actual_cost,
                            COALESCE(SUM(
                                COALESCE(ul.input_tokens, 0)
                                + COALESCE(ul.output_tokens, 0)
                                + COALESCE(ul.cache_creation_tokens, 0)
                                + COALESCE(ul.cache_read_tokens, 0)
                            ), 0)::bigint AS tokens,
                            COUNT(*)::bigint AS requests
                        FROM usage_logs ul
                        {where_sql}
                        GROUP BY ul.user_id
                    ),
                    totals AS (
                        SELECT
                            COALESCE(SUM(actual_cost), 0)::float8 AS total_actual_cost,
                            COALESCE(SUM(tokens), 0)::bigint AS total_tokens,
                            COALESCE(SUM(requests), 0)::bigint AS total_requests
                        FROM aggregated
                    ),
                    ranked AS (
                        SELECT
                            aggregated.*,
                            ROW_NUMBER() OVER (ORDER BY actual_cost DESC, tokens DESC) AS cost_rank,
                            ROW_NUMBER() OVER (ORDER BY tokens DESC, actual_cost DESC) AS token_rank
                        FROM aggregated
                    )
                    SELECT
                        ranked.user_id,
                        au.username,
                        au.email,
                        ranked.actual_cost,
                        ranked.tokens,
                        ranked.requests,
                        totals.total_actual_cost,
                        totals.total_tokens,
                        totals.total_requests
                    FROM ranked
                    CROSS JOIN totals
                    LEFT JOIN auth_users au ON au.user_id = ranked.user_id
                    WHERE ranked.cost_rank <= %s OR ranked.token_rank <= %s
                    """,
                    tuple(params),
                )
                rows = cur.fetchall()

        return [
            {
                "user_id": row[0],
                "username": row[1],
                "email": row[2],
                "actual_cost": float(row[3] or 0),
                "tokens": int(row[4] or 0),
                "requests": int(row[5] or 0),
                "total_actual_cost": float(row[6] or 0),
                "total_tokens": int(row[7] or 0),
                "total_requests": int(row[8] or 0),
            }
            for row in rows
        ]
