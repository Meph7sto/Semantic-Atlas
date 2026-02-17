import psycopg2

from backend_business.services.db_service_parts.schema import init_db


class DBServiceBase:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._init_db()

    def _connect(self) -> psycopg2.extensions.connection:
        return psycopg2.connect(self.dsn)

    def get_connection(self) -> psycopg2.extensions.connection:
        """
        Public connection helper kept for compatibility with mixins
        that expect `get_connection()` as the DB entrypoint.
        """
        return self._connect()

    def _init_db(self) -> None:
        with self._connect() as conn:
            init_db(conn)
