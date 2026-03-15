import json
from typing import Any, Dict, List, Optional

import psycopg2
from psycopg2.extras import RealDictCursor

from backend_business.config import settings

from .models import Edge, Span


class ContextRunRepository:
    def __init__(self, dsn: Optional[str] = None):
        self.dsn = dsn or settings.POSTGRES_DSN

    def _connect(self):
        return psycopg2.connect(self.dsn)

    def load_spans(self, session_id: str) -> List[Span]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT span_id, session_id, start_ms, end_ms, speaker, text
                    FROM spans
                    WHERE session_id = %s
                    ORDER BY COALESCE(start_ms, 0), created_at
                    """,
                    (session_id,),
                )
                rows = cur.fetchall()

        spans: List[Span] = []
        for idx, row in enumerate(rows):
            spans.append(
                Span(
                    span_id=row["span_id"],
                    session_id=row["session_id"],
                    start_ms=row["start_ms"],
                    end_ms=row["end_ms"],
                    speaker=row["speaker"],
                    text=row["text"],
                    order_index=idx,
                )
            )
        return spans

    def create_context_run(self, session_id: str, options: Dict[str, Any]) -> str:
        from uuid import uuid4

        context_run_id = str(uuid4())

        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO context_runs (context_run_id, session_id, options_snapshot, status)
                    VALUES (%s, %s, %s, 'RUNNING')
                    """,
                    (
                        context_run_id,
                        session_id,
                        json.dumps(options, ensure_ascii=False),
                    ),
                )

        return context_run_id

    def save_edges(self, context_run_id: str, edges: List[Edge]) -> int:
        if not edges:
            return 0

        with self._connect() as conn:
            with conn.cursor() as cur:
                for edge in edges:
                    cur.execute(
                        """
                        INSERT INTO span_links
                            (context_run_id, source_span_id, target_span_id, relation_type, strength, note)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (context_run_id, source_span_id, target_span_id, relation_type)
                        DO UPDATE SET strength = GREATEST(span_links.strength, EXCLUDED.strength),
                                      note = EXCLUDED.note
                        """,
                        (
                            context_run_id,
                            edge.source_span_id,
                            edge.target_span_id,
                            edge.relation_type,
                            edge.strength,
                            edge.note,
                        ),
                    )

        return len(edges)

    def save_bundles(self, bundles: List[Dict], bundle_items: List[Dict]) -> int:
        if not bundles:
            return 0

        with self._connect() as conn:
            with conn.cursor() as cur:
                for bundle in bundles:
                    cur.execute(
                        """
                        INSERT INTO bundles
                            (bundle_id, context_run_id, session_id, order_index, status, meta)
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """,
                        (
                            bundle["bundle_id"],
                            bundle["context_run_id"],
                            bundle["session_id"],
                            bundle["order_index"],
                            bundle["status"],
                            json.dumps(bundle.get("meta", {}), ensure_ascii=False),
                        ),
                    )

                for item in bundle_items:
                    cur.execute(
                        """
                        INSERT INTO bundle_items (bundle_id, span_id, span_ref, order_index)
                        VALUES (%s, %s, %s, %s)
                        """,
                        (
                            item["bundle_id"],
                            item["span_id"],
                            item["span_ref"],
                            item["order_index"],
                        ),
                    )

        return len(bundles)

    def update_context_run_status(
        self,
        context_run_id: str,
        status: str,
        stats: Optional[Dict[str, Any]] = None,
    ):
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE context_runs
                    SET status = %s, stats = %s
                    WHERE context_run_id = %s
                    """,
                    (
                        status,
                        json.dumps(stats or {}, ensure_ascii=False),
                        context_run_id,
                    ),
                )
