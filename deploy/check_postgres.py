"""Read-only database readiness check used before starting the business backend."""

import sys
from pathlib import Path

import psycopg2

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend_business.config import settings


def main() -> int:
    connection = None
    try:
        connection = psycopg2.connect(settings.POSTGRES_DSN, connect_timeout=5)
        with connection, connection.cursor() as cursor:
            cursor.execute("SELECT 1")
    except psycopg2.Error:
        print(
            "[start] PostgreSQL readiness check failed. Check Docker Desktop, "
            "the postgres container, and the configured database connection. "
            "Business backend startup aborted.",
            file=sys.stderr,
        )
        return 1
    finally:
        if connection is not None:
            connection.close()
    print("[start] PostgreSQL connection and query succeeded.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
