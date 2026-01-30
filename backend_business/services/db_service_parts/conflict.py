import json
import uuid
from typing import Any, Dict, List, Optional

from psycopg2.extras import RealDictCursor

from backend_business.services.db_service_parts.utils import _utc_now_iso


class ConflictAnalysisMixin:
    def save_conflict_batch(
        self,
        session_id: Optional[str],
        conflicts: List[Dict[str, Any]],
        batch_id: Optional[str] = None,
    ) -> List[int]:
        """
        批量保存冲突检测结果
        conflicts: List[{
            'requirement_a': str,
            'requirement_b': str,
            'is_conflict': bool,
            'raw_response': str,
            'data': dict (可选，完整的响应数据)
        }]
        """
        if not conflicts:
            return []

        record_ids = []
        batch_id = batch_id or uuid.uuid4().hex
        with self._connect() as conn:
            with conn.cursor() as cur:
                for conflict in conflicts:
                    result_json = (
                        conflict.get("data") or conflict.get("raw_response") or {}
                    )
                    if isinstance(result_json, str):
                        try:
                            result_json = json.loads(result_json)
                        except Exception:
                            result_json = {"raw": result_json}

                    cur.execute(
                        """
                        INSERT INTO conflict_analysis (
                            batch_id, session_id, requirement_a, requirement_b,
                            is_conflict, raw_response, result_json, created_at
                        )
                        VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING id
                        """,
                        (
                            batch_id,
                            session_id,
                            conflict.get("requirement_a", ""),
                            conflict.get("requirement_b", ""),
                            bool(conflict.get("is_conflict", False)),
                            conflict.get("raw_response", ""),
                            json.dumps(result_json, ensure_ascii=False),
                            _utc_now_iso(),
                        ),
                    )
                    record_ids.append(int(cur.fetchone()[0]))

        return record_ids

    def get_latest_conflict_batch(self, session_id: str) -> Optional[Dict[str, Any]]:
        with self._connect() as conn:
            with conn.cursor(cursor_factory=RealDictCursor) as cur:
                cur.execute(
                    """
                    SELECT batch_id
                    FROM conflict_analysis
                    WHERE session_id = %s AND batch_id IS NOT NULL
                    ORDER BY created_at DESC
                    LIMIT 1
                    """,
                    (session_id,),
                )
                row = cur.fetchone()
                if not row:
                    return None
                batch_id = row["batch_id"]
                cur.execute(
                    """
                    SELECT requirement_a, requirement_b, is_conflict, raw_response, result_json
                    FROM conflict_analysis
                    WHERE session_id = %s AND batch_id = %s
                    ORDER BY created_at ASC
                    """,
                    (session_id, batch_id),
                )
                rows = cur.fetchall()
        return {"batch_id": batch_id, "items": [dict(r) for r in rows]}
