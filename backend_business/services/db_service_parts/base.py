import psycopg2
import threading

from backend_business.services.db_service_parts.schema import init_db


class DBServiceBase:
    def __init__(self, dsn: str):
        self.dsn = dsn
        self._schema_initialized = False
        self._schema_init_lock = threading.Lock()

    def _connect(self) -> psycopg2.extensions.connection:
        conn = psycopg2.connect(self.dsn)
        try:
            self._init_db_if_needed(conn)
        except Exception:
            conn.close()
            raise
        return conn

    def get_connection(self) -> psycopg2.extensions.connection:
        """
        Public connection helper kept for compatibility with mixins
        that expect `get_connection()` as the DB entrypoint.
        """
        return self._connect()

    def _init_db_if_needed(self, conn: psycopg2.extensions.connection) -> None:
        if self._schema_initialized:
            return

        with self._schema_init_lock:
            if self._schema_initialized:
                return
            init_db(conn)
            self._schema_initialized = True
