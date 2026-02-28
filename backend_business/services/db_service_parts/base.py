import psycopg2

from backend_business.services.db_service_parts.schema import init_db


class DBServiceBase:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._init_db()

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(self.dsn)

    def _init_db(self) -> None:
        with self._connect() as conn:
            init_db(conn)
